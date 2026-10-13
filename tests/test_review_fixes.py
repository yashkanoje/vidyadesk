"""Regression tests for the findings of the whole-branch review of M1."""
import threading
from datetime import datetime, timedelta, timezone

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from sqlalchemy import func, select

from helpers import ScriptedModel, make_institute, make_lead, run_turn
from leadagent.agent.graph import LIMIT, LIMIT_REPLY, build_graph, get_checkpointer, message_text, thread_config
from leadagent.channels import deliver
from leadagent.channels.base import IncomingMsg
from leadagent.cli import set_owner
from leadagent.crypto import decrypt
from leadagent.jobs.digest import digest_text
from leadagent.jobs.nudge import run_nudges
from leadagent.locks import lock_for
from leadagent.pipeline import process
from leadagent.store import repo
from leadagent.store.db import session_scope
from leadagent.store.models import Lead

NOON_IST = datetime(2026, 10, 14, 6, 30, tzinfo=timezone.utc)  # 12:00 in Asia/Kolkata


def lead_count() -> int:
    with session_scope() as fresh:
        return fresh.scalar(select(func.count()).select_from(Lead))


def fill(session, lead, total):
    """Log user messages until the lead has `total` of them in the last 24 hours."""
    have = repo.user_messages_last_24h(session, lead.id, datetime.now(timezone.utc))
    for i in range(have, total):
        repo.log_message(session, lead, "user", "x", f"tg:{lead.id}-{i}")
    session.commit()


def empty_graph():
    model = ScriptedModel()
    return build_graph(model, get_checkpointer()), model


# 1. The daily summary names every new lead, not only hot ones.


def test_summary_names_every_new_lead(session):
    institute = make_institute(session)
    lead = make_lead(
        session, institute, "1", created_at=NOON_IST - timedelta(hours=2), name="Meera", student_class="10",
        course="JEE Foundation", phone="98610", interest="warm",
    )
    assert f"#{lead.id} Meera · Class 10 · JEE Foundation · 98610" in digest_text(session, institute, NOON_IST)


# 2. Telegram sends /start before the owner can be registered, which made the owner a lead.


def test_setting_the_owner_removes_the_lead_their_first_message_created(session, sent):
    institute = make_institute(session, owner_chat_id=None)
    graph = build_graph(ScriptedModel(AIMessage("Welcome!")), get_checkpointer())
    process(IncomingMsg(institute.id, "telegram", "4242", "tg:1", "/start"), graph=graph)
    lead_id = session.scalars(select(Lead)).one().id
    session.rollback()

    set_owner(session, "bright", "4242")
    session.commit()

    assert lead_count() == 0
    assert graph.get_state(thread_config(institute.id, lead_id)).values == {}


def test_setting_the_owner_leaves_other_leads_alone(session):
    institute = make_institute(session, owner_chat_id=None)
    make_lead(session, institute, "555")
    make_lead(session, institute, "4242", channel="whatsapp")
    set_owner(session, "bright", "4242")
    session.commit()
    assert lead_count() == 2


# 3 and 4. The message limit: one notice, one alert, then silence, and it caps relays and canned replies too.


def test_limit_notice_goes_out_once_and_the_stage_is_left_alone(session, sent):
    lead = make_lead(session, make_institute(session), stage="collecting")
    graph, model = empty_graph()

    fill(session, lead, LIMIT + 1)
    first = run_turn(graph, lead, "x")
    assert (first["route"], first["reply"]) == ("canned", LIMIT_REPLY)
    assert len(sent) == 1 and f"#{lead.id}" in sent[0][3]
    assert "/resume" not in sent[0][3]  # resuming does nothing about the limit, so the alert must not suggest it

    fill(session, lead, LIMIT + 2)
    second = run_turn(graph, lead, "x")
    assert (second["route"], second["reply"]) == ("canned", "")
    assert len(sent) == 1

    session.refresh(lead)
    assert lead.stage == "collecting"  # so replies start again by themselves once the 24 hours have passed
    assert model.calls == []


def test_limit_also_caps_relays_to_the_owner_and_please_type_replies(session, sent):
    institute = make_institute(session)
    handed_off = make_lead(session, institute, "1", stage="handed_off")
    sends_stickers = make_lead(session, institute, "2", stage="collecting")
    fill(session, handed_off, LIMIT + 2)
    fill(session, sends_stickers, LIMIT + 2)
    graph, _ = empty_graph()
    assert run_turn(graph, handed_off, "hello?")["reply"] == ""
    assert run_turn(graph, sends_stickers, "[non-text message]", kind="other")["reply"] == ""
    assert sent == []


# 5. A detail longer than its column used to fail the whole turn and lose the other details.


def test_an_overlong_detail_is_cut_to_fit_and_the_rest_is_saved(session):
    lead = make_lead(session, make_institute(session), stage="collecting")
    repo.save_lead_fields(
        session, lead, name="Ravi", phone="+91 98765 43210 (WhatsApp), +91 91234 56780 (call)", course="x" * 500,
        notes="n" * 5000,
    )
    session.commit()
    session.refresh(lead)
    assert lead.name == "Ravi"
    assert lead.phone == "+91 98765 43210 (WhatsApp), +91 "
    assert len(lead.course) == 200
    assert len(lead.notes) == 5000


# 6. Tool calls in one model message ran in parallel threads and raced.


def save_then_handoff():
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "save_lead", "args": {"name": "Rahul", "student_class": "11", "course": "JEE"}, "id": "c1", "type": "tool_call"},
            {"name": "handoff", "args": {"reason": "asked for a person"}, "id": "c2", "type": "tool_call"},
        ],
    )


def test_tool_calls_in_one_message_run_in_order(session, sent):
    institute = make_institute(session)
    for attempt in range(6):  # the race did not lose every time
        lead = make_lead(session, institute, str(attempt), stage="collecting")
        graph = build_graph(ScriptedModel(save_then_handoff(), AIMessage("Our team will contact you.")), get_checkpointer())
        run_turn(graph, lead, "I am Rahul, class 11, JEE. Let me talk to sir.")
        session.refresh(lead)
        assert lead.stage == "handed_off"
        assert "Rahul · Class 11 · JEE" in sent[-1][3]


def test_bad_arguments_and_unknown_tools_are_reported_back_to_the_model(session):
    lead = make_lead(session, make_institute(session), stage="collecting")
    bad = AIMessage(
        content="",
        tool_calls=[
            {"name": "set_interest", "args": {"level": "boiling", "reason": "x"}, "id": "c1", "type": "tool_call"},
            {"name": "refund", "args": {}, "id": "c2", "type": "tool_call"},
        ],
    )
    model = ScriptedModel(bad, AIMessage("Let me check with the team."))
    result = run_turn(build_graph(model, get_checkpointer()), lead, "hi")
    reported = [m for m in model.calls[1] if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in reported] == ["c1", "c2"]
    assert all(m.content.startswith("Error") for m in reported)
    assert message_text(result["messages"][-1]) == "Let me check with the team."
    session.refresh(lead)
    assert lead.interest is None


def test_the_real_claude_binding_builds_and_asks_for_one_tool_call_at_a_time(monkeypatch):
    # Every other graph test uses a scripted model. This one builds the real binding (no API call is made),
    # because a mistake there would fail on every real message.
    from leadagent.agent import graph as graph_module

    captured = {}
    monkeypatch.setattr(graph_module, "build_graph", lambda model, checkpointer: captured.setdefault("model", model))
    graph_module.get_graph.cache_clear()
    try:
        graph_module.get_graph()
    finally:
        graph_module.get_graph.cache_clear()
    assert captured["model"].kwargs["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert {tool["name"] for tool in captured["model"].kwargs["tools"]} == {"save_lead", "set_interest", "handoff"}


def test_the_eval_runner_binds_claude_the_same_way():
    from evals.run import make_model

    model, cache_prompt = make_model("anthropic")
    assert cache_prompt is True
    assert model.kwargs["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}


# 7. /delete during a reply left the conversation in the chat-state tables.


def test_delete_waits_for_a_reply_in_progress(session, sent):
    institute = make_institute(session)
    lead = make_lead(session, institute, "555", stage="collecting")
    graph, _ = empty_graph()
    command = IncomingMsg(institute.id, "telegram", "999", "tg:9", f"/delete {lead.id}")

    reply_in_progress = lock_for(lead.id)
    reply_in_progress.acquire()
    worker = threading.Thread(target=process, args=(command,), kwargs={"graph": graph}, daemon=True)
    worker.start()
    worker.join(timeout=1.0)
    deleted_early = lead_count() == 0
    reply_in_progress.release()
    worker.join(timeout=10)

    assert not worker.is_alive()
    assert not deleted_early, "the lead was deleted while a reply was still being written"
    assert lead_count() == 0


# 8. Failures the owner was not told about.


def test_deliver_reports_failure_for_any_send_error(session, monkeypatch):
    institute = make_institute(session)

    def broken_send(institute, user_id, text, client=None):
        raise ValueError("the stored token cannot be decrypted")

    monkeypatch.setattr("leadagent.channels.telegram.send", broken_send)
    waits = []
    assert deliver(institute, "telegram", "555", "hi", sleep=waits.append) is False
    assert waits == []  # retrying cannot help with an error that is not a network or HTTP error


# 9. The nudge was sent to a lead that stopped being due after the list was built.


class HandsOffWhileWriting:
    """Stands in for the nudge-writing model. While the first nudge is written, another lead is handed off."""

    def __init__(self, institute_id, lead_id):
        self.institute_id, self.lead_id = institute_id, lead_id

    def invoke(self, messages, config=None):
        with session_scope() as other:
            repo.hand_off(other, repo.get_lead(other, self.institute_id, self.lead_id), "asked for a person")
        return AIMessage("Still interested?")


def test_a_lead_that_stops_being_due_is_not_nudged(session, sent):
    institute = make_institute(session)
    quiet = {"stage": "collecting", "last_user_msg_at": NOON_IST - timedelta(hours=3)}
    make_lead(session, institute, "1", **quiet)
    second = make_lead(session, institute, "2", **quiet)
    graph, _ = empty_graph()
    assert run_nudges(now=NOON_IST, model=HandsOffWhileWriting(institute.id, second.id), graph=graph) == 1
    assert [s[2] for s in sent] == ["1"]
    session.refresh(second)
    assert second.nudged_at is None


# 10. Attaching a WhatsApp number to an existing institute, and replacing its short-lived token.


def test_set_whatsapp_attaches_a_number_and_replaces_the_token(session):
    from leadagent.cli import set_whatsapp

    institute = make_institute(session)
    set_whatsapp(session, "bright", "PN1", "token-one")
    set_whatsapp(session, "bright", "PN1", " token-two\n")
    assert institute.whatsapp_phone_number_id == "PN1"
    assert decrypt(institute.whatsapp_token_enc) == "token-two"


def test_set_whatsapp_refuses_a_number_another_institute_uses_and_an_empty_token(session):
    from leadagent.cli import set_whatsapp

    make_institute(session, "one", whatsapp_phone_number_id="PN1")
    make_institute(session, "two")
    with pytest.raises(ValueError, match="already"):
        set_whatsapp(session, "two", "PN1", "token")
    with pytest.raises(ValueError, match="token"):
        set_whatsapp(session, "two", "PN2", "  ")

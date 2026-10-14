from datetime import timedelta

from langchain_core.messages import AIMessage
from sqlalchemy import func, select

from helpers import ScriptedModel, make_institute, make_lead, tool_call
from leadagent.agent.graph import (
    NONTEXT_REPLY,
    WAITING_REPLY,
    WAITING_REPLY_EVERY,
    build_graph,
    get_checkpointer,
    thread_config,
)
from leadagent.channels.base import IncomingMsg
from leadagent.commands import HELP
from leadagent.pipeline import FALLBACK, MAX_CHARS, process
from leadagent.store import repo
from leadagent.store.models import Lead, Message


def graph_with(*replies):
    model = ScriptedModel(*replies)
    return build_graph(model, get_checkpointer()), model


def tg(institute, text, user_id="555", msg_id="tg:1"):
    return IncomingMsg(institute.id, "telegram", user_id, msg_id, text)


def the_lead(session):
    return session.scalars(select(Lead)).one()


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_a_message_is_answered_and_logged(session, sent):
    institute = make_institute(session)
    graph, _ = graph_with(AIMessage("Hello! How can I help?"))
    process(tg(institute, "hi"), graph=graph)
    lead = the_lead(session)
    assert sent == [("telegram", institute.id, "555", "Hello! How can I help?")]
    assert lead.stage == "collecting" and lead.last_user_msg_at is not None
    assert [(m.role, m.text) for m in repo.recent_messages(session, lead.id, 10)] == [
        ("user", "hi"),
        ("assistant", "Hello! How can I help?"),
    ]


def test_a_resent_webhook_is_answered_once(session, sent):
    institute = make_institute(session)
    graph, model = graph_with(AIMessage("Hello!"))
    process(tg(institute, "hi"), graph=graph)
    process(tg(institute, "hi"), graph=graph)
    assert len(sent) == 1
    assert len(model.calls) == 1


def test_long_text_is_cut_by_characters_not_bytes(session, sent):
    institute = make_institute(session)
    graph, model = graph_with(AIMessage("ok"))
    process(tg(institute, "ଓ" * 1500), graph=graph)
    assert len(model.calls[0][-1].content) == MAX_CHARS
    assert len(repo.recent_messages(session, the_lead(session).id, 10)[0].text) == MAX_CHARS


def test_whitespace_only_text_gets_the_please_type_reply(session, sent):
    institute = make_institute(session)
    graph, model = graph_with()
    process(tg(institute, "   \n "), graph=graph)
    assert sent == [("telegram", institute.id, "555", NONTEXT_REPLY)]
    assert model.calls == []


def test_a_photo_gets_the_please_type_reply(session, sent):
    institute = make_institute(session)
    graph, _ = graph_with()
    process(tg(institute, None), graph=graph)
    assert sent[0][3] == NONTEXT_REPLY


def test_start_is_treated_as_a_greeting(session, sent):
    institute = make_institute(session)
    graph, model = graph_with(AIMessage("Welcome!"))
    process(tg(institute, "/start"), graph=graph)
    assert model.calls[0][-1].content == "Hello"


def test_a_model_failure_sends_the_fallback_and_alerts_the_owner(session, sent):
    institute = make_institute(session)
    graph, _ = graph_with(RuntimeError("API down"))
    process(tg(institute, "hi"), graph=graph)
    lead = the_lead(session)
    assert ("telegram", institute.id, "555", FALLBACK) in sent
    owner_alerts = [s for s in sent if s[2] == "999"]
    assert len(owner_alerts) == 1 and f"#{lead.id}" in owner_alerts[0][3]
    assert repo.recent_messages(session, lead.id, 10)[0].text == "hi"  # the user's message was kept


def test_an_empty_model_reply_sends_the_fallback_and_alerts_the_owner(session, sent):
    institute = make_institute(session)
    graph, _ = graph_with(AIMessage(""))
    process(tg(institute, "hi"), graph=graph)
    lead = the_lead(session)
    assert ("telegram", institute.id, "555", FALLBACK) in sent
    owner_alerts = [s for s in sent if s[2] == "999"]
    assert len(owner_alerts) == 1 and f"#{lead.id}" in owner_alerts[0][3]


def test_a_failed_delivery_alerts_the_owner(session, sent, monkeypatch):
    institute = make_institute(session)
    graph, _ = graph_with(AIMessage("Hello!"))
    monkeypatch.setattr("leadagent.pipeline.deliver", lambda *args, **kwargs: False)
    process(tg(institute, "hi"), graph=graph)
    assert len(sent) == 1 and sent[0][2] == "999" and "Could not deliver" in sent[0][3]


def test_messages_to_an_inactive_institute_are_dropped(session, sent):
    institute = make_institute(session, active=False)
    graph, model = graph_with()
    process(tg(institute, "hi"), graph=graph)
    assert sent == [] and count(session, Lead) == 0


def test_a_handed_off_lead_is_acknowledged_once_then_only_relayed(session, sent):
    institute = make_institute(session)
    graph, _ = graph_with(tool_call("handoff", reason="asked for a person"), AIMessage("Our team will contact you."))
    process(tg(institute, "talk to sir", msg_id="tg:1"), graph=graph)
    sent.clear()
    process(tg(institute, "hello?", msg_id="tg:2"), graph=graph)
    assert [(s[2], s[3]) for s in sent][1:] == [("555", WAITING_REPLY)]
    assert sent[0][2] == "999"  # forwarded to the owner first
    sent.clear()
    process(tg(institute, "anyone?", msg_id="tg:3"), graph=graph)
    assert [s[2] for s in sent] == ["999"]  # acknowledged already: only the relay


def test_the_waiting_reply_is_repeated_after_the_waiting_window(session, sent):
    institute = make_institute(session)
    lead = make_lead(session, institute, "555", stage="handed_off")
    repo.log_message(session, lead, "assistant", WAITING_REPLY)
    session.commit()
    old = session.scalars(select(Message).where(Message.role == "assistant")).one()
    old.created_at = old.created_at - WAITING_REPLY_EVERY - timedelta(minutes=1)
    session.commit()
    process(tg(institute, "still there?", msg_id="tg:4"), graph=graph_with()[0])
    assert ("555", WAITING_REPLY) in [(s[2], s[3]) for s in sent]


# Owner commands


def test_whoami_answers_anyone_and_creates_no_lead(session, sent):
    institute = make_institute(session)
    process(tg(institute, "/whoami", user_id="4242"), graph=graph_with()[0])
    assert sent == [("telegram", institute.id, "4242", "Your chat ID is 4242")]
    assert count(session, Lead) == 0


def test_the_owner_never_becomes_a_lead(session, sent):
    institute = make_institute(session)
    process(tg(institute, "hi, is this working?", user_id="999"), graph=graph_with()[0])
    assert sent == [("telegram", institute.id, "999", HELP)]
    assert count(session, Lead) == 0


def test_a_students_command_is_ordinary_text(session, sent):
    institute = make_institute(session)
    lead = make_lead(session, institute, "777", stage="handed_off")
    graph, model = graph_with(AIMessage("I can't do that."))
    process(tg(institute, f"/resume {lead.id}", user_id="555"), graph=graph)
    session.refresh(lead)
    assert lead.stage == "handed_off"
    assert model.calls[0][-1].content == f"/resume {lead.id}"


def test_owner_resumes_a_lead(session, sent):
    institute = make_institute(session)
    lead = make_lead(session, institute, "555", stage="handed_off", name="Rahul", handoff_reason="x")
    process(tg(institute, f"/resume {lead.id}", user_id="999"), graph=graph_with()[0])
    session.refresh(lead)
    assert lead.stage == "collecting"
    assert sent == [("telegram", institute.id, "999", f"Assistant switched back on for lead {lead.id}.")]


def test_owner_cannot_touch_another_institutes_lead(session, sent):
    mine = make_institute(session, "mine", owner_chat_id="999")
    theirs = make_institute(session, "theirs", owner_chat_id="888")
    lead = make_lead(session, theirs, "555", stage="handed_off")
    process(tg(mine, f"/resume {lead.id}", user_id="999"), graph=graph_with()[0])
    process(tg(mine, f"/delete {lead.id}", user_id="999", msg_id="tg:2"), graph=graph_with()[0])
    session.refresh(lead)
    assert lead.stage == "handed_off"
    assert [s[3] for s in sent] == [f"No lead {lead.id} for this institute."] * 2


def test_owner_deletes_a_lead_with_messages_and_chat_state(session, sent):
    institute = make_institute(session)
    graph, _ = graph_with(AIMessage("Hello!"))
    process(tg(institute, "hi"), graph=graph)
    lead_id = the_lead(session).id
    session.rollback()
    process(tg(institute, f"/delete {lead_id}", user_id="999", msg_id="tg:9"), graph=graph)
    assert count(session, Lead) == 0 and count(session, Message) == 0
    assert graph.get_state(thread_config(institute.id, lead_id)).values == {}
    assert sent[-1][3] == f"Lead {lead_id} and its messages are deleted."


def test_bad_owner_commands_get_help(session, sent):
    institute = make_institute(session)
    for i, text in enumerate(["/resume", "/resume abc", "/delete 1 2", "/resume 99999999999999999999"]):
        process(tg(institute, text, user_id="999", msg_id=f"tg:{i}"), graph=graph_with()[0])
    assert [s[3] for s in sent] == [HELP] * 4

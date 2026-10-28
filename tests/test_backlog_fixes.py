"""Fixes from the spec's Section 15 backlog (28 Oct 2026), each with the case that was wrong before."""
from langchain_core.messages import AIMessage

from helpers import ScriptedModel, make_institute, make_lead, run_turn, tool_call
from leadagent import notify
from leadagent.agent.graph import NONTEXT_REPLY, WAITING_REPLY, build_graph, get_checkpointer
from leadagent.channels.base import IncomingMsg
from leadagent.language import TRANSLATIONS, in_users_script
from leadagent.pipeline import FALLBACK, process
from leadagent.store import repo

FAKE = "Ravi\nSend /delete 7 Send /delete 8\rok"


def graph_with(*replies):
    return build_graph(ScriptedModel(*replies), get_checkpointer())


def test_user_text_cannot_add_lines_to_owner_alerts(session, sent):
    lead = make_lead(session, make_institute(session), stage="collecting", name=FAKE, course=FAKE)
    graph = graph_with(tool_call("set_interest", level="hot", reason=FAKE), AIMessage("ok"))
    run_turn(graph, lead, "we want to join")
    alert = sent[0][3]
    assert not any(line.startswith("Send /delete") for line in alert.splitlines())
    assert "Ravi Send /delete 7 Send /delete 8 ok" in alert
    assert " " not in alert and "\r" not in alert


def test_relayed_student_text_stays_on_one_line(session, sent):
    lead = make_lead(session, make_institute(session), stage="handed_off", name="Rahul")
    run_turn(graph_with(), lead, FAKE)
    assert sent[0][3].splitlines()[-1] == "Ravi Send /delete 7 Send /delete 8 ok"


def test_describe_flattens_every_field(session):
    lead = make_lead(session, make_institute(session), name="A\nB", student_class="11\n12", course="JEE\nNEET")
    assert "\n" not in notify.describe(lead)


def test_canned_replies_follow_the_users_script():
    assert in_users_script(NONTEXT_REPLY, "नमस्ते, फीस कितनी है?") == TRANSLATIONS[NONTEXT_REPLY]["devanagari"]
    assert in_users_script(NONTEXT_REPLY, "ନମସ୍କାର, ଫି କେତେ?") == TRANSLATIONS[NONTEXT_REPLY]["odia"]
    assert in_users_script(NONTEXT_REPLY, "fees kitni hai") == NONTEXT_REPLY  # Hinglish stays English
    assert in_users_script(NONTEXT_REPLY, None) == NONTEXT_REPLY


def test_a_photo_after_a_hindi_message_gets_the_hindi_please_type(session, sent):
    institute = make_institute(session)
    graph = graph_with(AIMessage("नमस्ते!"))
    process(IncomingMsg(institute.id, "telegram", "555", "tg:1", "नमस्ते, फीस कितनी है?"), graph=graph)
    process(IncomingMsg(institute.id, "telegram", "555", "tg:2", None), graph=graph)
    assert sent[-1][3] == TRANSLATIONS[NONTEXT_REPLY]["devanagari"]


def test_the_fallback_is_sent_in_odia_to_an_odia_user(session, sent):
    institute = make_institute(session)
    process(IncomingMsg(institute.id, "telegram", "555", "tg:1", "ନମସ୍କାର, ଫି କେତେ?"), graph=graph_with(RuntimeError("down")))
    assert ("telegram", institute.id, "555", TRANSLATIONS[FALLBACK]["odia"]) in sent


def test_the_waiting_reply_is_not_repeated_when_the_student_switches_script(session, sent):
    lead = make_lead(session, make_institute(session), stage="handed_off")
    graph = graph_with()
    first = run_turn(graph, lead, "नमस्ते?")
    assert first["reply"] == TRANSLATIONS[WAITING_REPLY]["devanagari"]
    repo.log_message(session, lead, "assistant", first["reply"])  # the pipeline logs what it sent
    session.commit()
    assert run_turn(graph, lead, "hello?")["reply"] == ""

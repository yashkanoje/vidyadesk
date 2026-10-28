"""Fixes from the spec's Section 15 backlog (28 Oct 2026), each with the case that was wrong before."""
import pytest
import yaml
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from helpers import FACTS, ScriptedModel, make_institute, make_lead, make_user, run_turn, tool_call
from leadagent import notify
from leadagent.agent.graph import NONTEXT_REPLY, WAITING_REPLY, build_graph, get_checkpointer
from leadagent.app import app
from leadagent.channels.base import IncomingMsg
from leadagent.cli import add_institute
from leadagent.dashboard.routes import _cell
from leadagent.facts import parse_facts
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


# --- dashboard and command fixes ---


@pytest.fixture
def owner(session):
    institute = make_institute(session, "bright")
    make_user(session, institute=institute)
    client = TestClient(app)
    client.post("/dash/login", data={"email": "owner@bright.test", "password": "correct horse 1"})
    return client, institute


@pytest.mark.parametrize("path", ["/dash/bright/leads/99999999999", "/dash/bright/leads/0"])
def test_an_out_of_range_lead_number_is_a_404(owner, path):
    client, _ = owner
    assert client.get(path).status_code == 404
    assert client.post(path + "/close").status_code == 404


def test_a_huge_days_filter_does_not_crash(owner):
    client, _ = owner
    assert client.get("/dash/bright/leads?days=999999999").status_code == 200
    assert client.get("/dash/bright/leads.csv?days=999999999").status_code == 200


def test_an_out_of_range_document_number_is_a_404(owner):
    client, _ = owner
    assert client.post("/dash/bright/documents/99999999999/delete").status_code == 404


@pytest.mark.parametrize("stage", ["new", "collecting", "closed"])
def test_resume_only_switches_back_a_handed_off_lead(owner, session, stage):
    client, institute = owner
    lead = make_lead(session, institute, "1", stage=stage)
    page = client.post(f"/dash/bright/leads/{lead.id}/resume").text
    session.refresh(lead)
    assert lead.stage == stage and "nothing changed" in page


def test_telegram_resume_of_a_closed_lead_changes_nothing(session, sent):
    institute = make_institute(session)
    lead = make_lead(session, institute, "555", stage="closed")
    process(IncomingMsg(institute.id, "telegram", "999", "tg:1", f"/resume {lead.id}"), graph=graph_with())
    session.refresh(lead)
    assert lead.stage == "closed"
    assert sent[-1][3] == f"Lead {lead.id} is not waiting for you, so nothing changed."


def test_csv_guards_tab_and_carriage_return_but_not_plain_phone_numbers():
    assert _cell("\t=1+1") == "'\t=1+1"
    assert _cell("\r=1+1") == "'\r=1+1"
    assert _cell("+919876543210", phone=True) == "+919876543210"
    assert _cell("+91-98765-43210", phone=True) == "'+91-98765-43210"  # Excel would calculate this one
    assert _cell("=cmd", phone=True) == "'=cmd"


@pytest.mark.parametrize("field", ["name", "telegram_token"])
def test_an_institute_needs_a_name_and_a_token(session, field):
    values = {"name": "Vidya", "telegram_token": "123:ABC", field: "  "}
    with pytest.raises(ValueError):
        add_institute(session, slug="vidya", facts=parse_facts(FACTS), **values)


def test_two_admins_adding_the_same_slug_get_a_message_not_a_500(session, monkeypatch):
    make_user(session, email="admin@lead.test", role="admin")
    make_institute(session, "vidya")
    client = TestClient(app)
    client.post("/dash/login", data={"email": "admin@lead.test", "password": "correct horse 1"})
    monkeypatch.setattr(repo, "institute_by_slug", lambda session, slug: None)  # both checks ran before either insert
    form = {"slug": "vidya", "name": "Vidya", "telegram_token": "1:A", "timezone": "Asia/Kolkata",
            "facts_yaml": yaml.safe_dump(FACTS, allow_unicode=True)}
    response = client.post("/dash/admin/institutes", data=form)
    assert response.status_code == 400 and "already exists" in response.text

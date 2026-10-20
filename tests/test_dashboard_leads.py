import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import func, select

from helpers import ScriptedModel, make_institute, make_lead, make_user, run_turn
from leadagent.agent.graph import build_graph, get_checkpointer, thread_config
from leadagent.app import app
from leadagent.store import repo
from leadagent.store.models import Lead, Message


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def two_institutes(session):
    mine = make_institute(session, "bright")
    theirs = make_institute(session, "other")
    make_user(session, institute=mine)
    return mine, theirs


def login(client, email="owner@bright.test"):
    client.post("/dash/login", data={"email": email, "password": "correct horse 1"})


def test_the_leads_page_lists_this_institutes_leads_only(client, session, two_institutes):
    mine, theirs = two_institutes
    make_lead(session, mine, "1", name="Rahul")
    make_lead(session, theirs, "2", name="Secret Student")
    login(client)
    page = client.get("/dash/bright/leads")
    assert page.status_code == 200
    assert "Rahul" in page.text and "Secret Student" not in page.text


def test_filters_by_stage_and_interest(client, session, two_institutes):
    mine, _ = two_institutes
    make_lead(session, mine, "1", name="Waiting One", stage="handed_off")
    make_lead(session, mine, "2", name="Hot One", stage="collecting", interest="hot")
    login(client)
    assert "Hot One" not in client.get("/dash/bright/leads?stage=handed_off").text
    assert "Waiting One" not in client.get("/dash/bright/leads?interest=hot").text
    assert "Waiting One" in client.get("/dash/bright/leads?stage=nonsense").text  # an unknown filter is ignored


def test_html_in_student_text_is_shown_as_text(client, session, two_institutes):
    mine, _ = two_institutes
    lead = make_lead(session, mine, "1", name="<script>alert(1)</script>")
    repo.log_message(session, lead, "user", "<img src=x onerror=alert(2)>")
    session.commit()
    login(client)
    for page in (client.get("/dash/bright/leads"), client.get(f"/dash/bright/leads/{lead.id}")):
        assert "<script>alert(1)</script>" not in page.text
        assert "&lt;script&gt;" in page.text
    assert "<img src=x" not in client.get(f"/dash/bright/leads/{lead.id}").text


def test_the_detail_page_shows_the_transcript_in_order(client, session, two_institutes):
    mine, _ = two_institutes
    lead = make_lead(session, mine, "1", name="Rahul")
    for role, text in (("user", "JEE fee?"), ("assistant", "68,000 rupees a year."), ("user", "Thanks")):
        repo.log_message(session, lead, role, text)
    session.commit()
    login(client)
    text = client.get(f"/dash/bright/leads/{lead.id}").text
    assert text.index("JEE fee?") < text.index("68,000 rupees a year.") < text.index("Thanks")


def test_csv_export_has_the_leads_and_neutralises_formulas(client, session, two_institutes):
    mine, theirs = two_institutes
    make_lead(session, mine, "1", name="=HYPERLINK(\"http://evil\")", course="JEE")
    make_lead(session, theirs, "2", name="Secret Student")
    login(client)
    response = client.get("/dash/bright/leads.csv")
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.startswith("﻿")  # so Excel reads Odia and Hindi names correctly
    assert "'=HYPERLINK" in response.text and "Secret Student" not in response.text


def test_resume_and_close(client, session, two_institutes):
    mine, _ = two_institutes
    lead = make_lead(session, mine, "1", stage="handed_off", name="Rahul")
    login(client)
    assert client.post(f"/dash/bright/leads/{lead.id}/resume", follow_redirects=False).status_code == 303
    session.refresh(lead)
    assert lead.stage == "collecting"
    client.post(f"/dash/bright/leads/{lead.id}/close")
    session.refresh(lead)
    assert lead.stage == "closed"


def test_delete_removes_the_lead_its_messages_and_its_chat_state(client, session, two_institutes):
    mine, _ = two_institutes
    lead = make_lead(session, mine, "1", stage="collecting")
    graph = build_graph(ScriptedModel(AIMessage("Hello!")), get_checkpointer())
    run_turn(graph, lead, "hi")
    repo.log_message(session, lead, "user", "hi")
    session.commit()
    login(client)
    response = client.post(f"/dash/bright/leads/{lead.id}/delete", follow_redirects=False)
    assert response.headers["location"] == "/dash/bright/leads"
    assert session.scalar(select(func.count()).select_from(Lead)) == 0
    assert session.scalar(select(func.count()).select_from(Message)) == 0
    assert graph.get_state(thread_config(mine.id, lead.id)).values == {}


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/dash/other/leads"),
        ("get", "/dash/other/leads.csv"),
        ("get", "/dash/other/leads/{theirs}"),
        ("get", "/dash/bright/leads/{theirs}"),
        ("post", "/dash/other/leads/{theirs}/delete"),
        ("post", "/dash/bright/leads/{theirs}/delete"),
        ("post", "/dash/bright/leads/{theirs}/resume"),
        ("post", "/dash/bright/leads/{theirs}/close"),
        ("post", "/dash/bright/leads/{mine}/explode"),
    ],
)
def test_an_owner_gets_404_for_anything_not_theirs(client, session, two_institutes, method, path):
    mine, theirs = two_institutes
    my_lead = make_lead(session, mine, "1", stage="handed_off")
    their_lead = make_lead(session, theirs, "2", stage="handed_off")
    login(client)
    response = getattr(client, method)(path.format(mine=my_lead.id, theirs=their_lead.id), follow_redirects=False)
    assert response.status_code == 404
    session.refresh(their_lead)
    assert their_lead.stage == "handed_off"


def test_the_admin_sees_every_institute(client, session, two_institutes):
    _, theirs = two_institutes
    make_lead(session, theirs, "2", name="Other Student")
    make_user(session, email="admin@lead.test", role="admin")
    login(client, email="admin@lead.test")
    assert "Other Student" in client.get("/dash/other/leads").text


def test_transcript_is_shown_as_chat_bubbles(client, session, two_institutes):
    mine, _ = two_institutes
    lead = make_lead(session, mine, "1", name="Rahul")
    for role, text in (("user", "Fee?"), ("assistant", "68,000 a year."), ("owner", "Come at 5 pm.")):
        repo.log_message(session, lead, role, text)
    session.commit()
    login(client)
    page = client.get(f"/dash/bright/leads/{lead.id}").text
    positions = [page.index(f'class="bubble {role}"') for role in ("user", "assistant", "owner")]
    assert positions == sorted(positions)


def test_lead_page_actions_are_post_forms(client, session, two_institutes):
    mine, _ = two_institutes
    lead = make_lead(session, mine, "1", stage="handed_off")
    login(client)
    page = client.get(f"/dash/bright/leads/{lead.id}").text
    for action in ("resume", "close", "delete"):
        assert f'method="post" action="/dash/bright/leads/{lead.id}/{action}"' in page
    assert "return confirm(" in page


def test_the_lead_page_shows_the_whole_name(client, session, two_institutes):
    mine, _ = two_institutes
    lead = make_lead(session, mine, "1", name="Sneha Raghavendran Venkatasubramanian Iyer")
    login(client)
    assert '<h1 class="lead-name">Sneha Raghavendran Venkatasubramanian Iyer</h1>' in client.get(f"/dash/bright/leads/{lead.id}").text

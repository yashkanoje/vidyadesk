import pytest
from fastapi.testclient import TestClient

from helpers import make_institute, make_lead, make_user
from leadagent.app import app


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
    return client.post("/dash/login", data={"email": email, "password": "correct horse 1"}, follow_redirects=False)


def test_owner_login_lands_on_home(client, two_institutes):
    assert login(client).headers["location"] == "/dash/bright/home"
    assert client.get("/dash", follow_redirects=False).headers["location"] == "/dash/bright/home"


def test_home_shows_numbers_and_needs_you(client, session, two_institutes):
    mine, _ = two_institutes
    make_lead(session, mine, "1", name="Aman Kumar", stage="handed_off", handoff_reason="wants to talk to sir")
    login(client)
    page = client.get("/dash/bright/home").text
    needs_you = page[page.index("Needs you"):page.index("Latest leads")]
    assert "Aman Kumar" in needs_you and "Waiting" in needs_you and "wants to talk to sir" in needs_you


def test_home_shows_only_this_institute(client, session, two_institutes):
    _, theirs = two_institutes
    make_lead(session, theirs, "2", name="Secret Student", stage="handed_off")
    login(client)
    assert "Secret Student" not in client.get("/dash/bright/home").text


def test_home_of_another_institute_is_404(client, two_institutes):
    login(client)
    assert client.get("/dash/other/home").status_code == 404


def test_home_escapes_student_names(client, session, two_institutes):
    mine, _ = two_institutes
    make_lead(session, mine, "1", name="<script>alert(1)</script>")
    login(client)
    page = client.get("/dash/bright/home").text
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page


def test_nameless_lead_says_name_not_given_never_none(client, session, two_institutes):
    mine, _ = two_institutes
    make_lead(session, mine, "1", stage="handed_off")
    login(client)
    page = client.get("/dash/bright/home").text
    assert "Name not given" in page
    assert ">None<" not in page and " None " not in page and "None ·" not in page


def test_empty_institute_shows_empty_states(client, two_institutes):
    login(client)
    page = client.get("/dash/bright/home").text
    assert "Nothing waiting. The assistant is handling every enquiry." in page
    assert "No enquiries yet." in page


def test_admin_can_open_an_institute_home(client, session, two_institutes):
    make_user(session, email="admin@lead.test", role="admin")
    login(client, "admin@lead.test")
    assert client.get("/dash/other/home").status_code == 200

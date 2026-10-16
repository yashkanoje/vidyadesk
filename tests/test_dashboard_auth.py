import pytest
from fastapi.testclient import TestClient

from helpers import make_institute, make_user
from leadagent.app import app


@pytest.fixture
def client():
    return TestClient(app)  # not a context manager: start-up (scheduler, model warm-up) does not run


def login(client, email="owner@bright.test", password="correct horse 1"):
    return client.post("/dash/login", data={"email": email, "password": password}, follow_redirects=False)


def test_the_login_page_renders(client):
    response = client.get("/dash/login")
    assert response.status_code == 200
    assert 'name="password"' in response.text and 'name="viewport"' in response.text


@pytest.mark.parametrize("path", ["/dash", "/dash/bright/leads", "/dash/admin/institutes"])
def test_pages_need_a_login(client, session, path):
    make_institute(session)
    response = client.get(path, follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, "/dash/login")


def test_an_owner_logs_in_to_their_leads(client, session):
    make_user(session, institute=make_institute(session))
    response = login(client)
    assert (response.status_code, response.headers["location"]) == (303, "/dash/bright/leads")
    assert client.get("/dash", follow_redirects=False).headers["location"] == "/dash/bright/leads"


def test_the_admin_logs_in_to_the_institute_list(client, session):
    make_user(session, email="admin@lead.test", role="admin")
    assert login(client, email="admin@lead.test").headers["location"] == "/dash/admin/institutes"


def test_email_case_and_spaces_do_not_matter(client, session):
    make_user(session, institute=make_institute(session))
    assert login(client, email="  OWNER@Bright.test ").status_code == 303


def test_a_wrong_password_and_an_unknown_email_get_the_same_answer(client, session):
    make_user(session, institute=make_institute(session))
    wrong = login(client, password="not the password")
    unknown = login(client, email="nobody@bright.test")
    assert wrong.status_code == unknown.status_code == 401
    assert "Wrong email or password" in wrong.text and "Wrong email or password" in unknown.text


def test_five_failures_block_even_the_right_password(client, session):
    make_user(session, institute=make_institute(session))
    for _ in range(5):
        assert login(client, password="not the password").status_code == 401
    blocked = login(client)
    assert blocked.status_code == 429 and "Too many failed attempts" in blocked.text


def test_logging_out_ends_the_session(client, session):
    make_user(session, institute=make_institute(session))
    login(client)
    assert client.post("/dash/logout", follow_redirects=False).headers["location"] == "/dash/login"
    assert client.get("/dash/bright/leads", follow_redirects=False).status_code == 303


def test_the_session_cookie_is_httponly_and_strict(client, session):
    make_user(session, institute=make_institute(session))
    cookie = login(client).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_a_deleted_user_is_logged_out(client, session):
    user = make_user(session, institute=make_institute(session))
    login(client)
    session.delete(user)
    session.commit()
    assert client.get("/dash", follow_redirects=False).headers["location"] == "/dash/login"


def test_an_owner_cannot_open_the_admin_pages(client, session):
    make_user(session, institute=make_institute(session))
    login(client)
    assert client.get("/dash/admin/institutes").status_code == 404

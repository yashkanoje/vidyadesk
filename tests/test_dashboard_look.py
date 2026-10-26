from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from helpers import make_institute, make_user
from leadagent.app import app
from leadagent.dashboard.routes import initials


@pytest.fixture
def client():
    return TestClient(app)


def login(client, email):
    client.post("/dash/login", data={"email": email, "password": "correct horse 1"})


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Rahul Sharma", "RS"),
        ("priya", "P"),
        ("Aman Kumar Singh", "AS"),
        (None, "?"),
        ("   ", "?"),
        ("ପ୍ରିୟା ମହାନ୍ତି", "ପମ"),
    ],
)
def test_initials(name, expected):
    assert initials(name) == expected


def test_login_page_is_branded(client):
    page = client.get("/dash/login").text
    assert "VidyaDesk" in page and "<title>" in page and 'name="viewport"' in page


def test_owner_navigation_has_every_tab_and_no_admin_tab(client, session):
    make_user(session, institute=make_institute(session))
    login(client, "owner@bright.test")
    page = client.get("/dash/bright/leads").text
    for href in ("/dash/bright/home", "/dash/bright/leads", "/dash/bright/documents", "/dash/bright/facts", "/dash/bright/stats"):
        assert f'href="{href}"' in page
    assert "/dash/admin/institutes" not in page


def test_admin_navigation_has_institutes(client, session):
    make_user(session, email="admin@lead.test", role="admin")
    login(client, "admin@lead.test")
    assert 'href="/dash/admin/institutes"' in client.get("/dash/admin/institutes").text


def stylesheet():
    return (Path(__file__).resolve().parents[1] / "leadagent" / "dashboard" / "templates" / "vidyadesk.css").read_text(encoding="utf-8")


def test_home_content_stays_hidden_while_the_intro_plays():
    # The intro fades out over the real page; the page must not show through before its build-up starts.
    css = stylesheet()
    assert ".intro-play main .stat" in css and ".intro-play main .row" in css


def test_error_banners_wrap_long_words():
    css = stylesheet()
    error_rule = css[css.index("\n.error {"):]  # the error rule itself, not the shared .flash/.error one
    assert "overflow-wrap: anywhere" in error_rule[: error_rule.index("}")]

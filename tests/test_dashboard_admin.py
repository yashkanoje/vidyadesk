import pytest
import yaml
from fastapi.testclient import TestClient

from helpers import FACTS, make_institute, make_user
from leadagent.app import app
from leadagent.crypto import decrypt
from leadagent.store import repo


@pytest.fixture
def client(session):
    make_user(session, email="admin@lead.test", role="admin")
    test_client = TestClient(app)
    test_client.post("/dash/login", data={"email": "admin@lead.test", "password": "correct horse 1"})
    return test_client


def new_institute(slug="vidya", facts=None, token="123:ABC"):
    return {
        "slug": slug, "name": "Vidya", "timezone": "Asia/Kolkata", "telegram_token": token,
        "facts_yaml": facts if facts is not None else yaml.safe_dump(FACTS, allow_unicode=True),
    }


def test_the_admin_sees_every_institute(client, session):
    make_institute(session, "bright")
    make_institute(session, "other", active=False)
    page = client.get("/dash/admin/institutes").text
    assert "bright" in page and "other" in page


def test_the_admin_adds_an_institute(client, session):
    page = client.post("/dash/admin/institutes", data=new_institute())
    assert "Added vidya" in page.text
    institute = repo.institute_by_slug(session, "vidya")
    assert decrypt(institute.telegram_bot_token_enc) == "123:ABC"
    assert institute.facts == FACTS


@pytest.mark.parametrize(
    "form, message",
    [
        (new_institute(slug="admin"), "reserved"),
        (new_institute(slug="Bad Slug"), "slug must be"),
        (new_institute(facts="institute_name: X"), "Invalid institute facts"),
        (new_institute(facts="courses: [unclosed"), "not valid YAML"),
    ],
)
def test_bad_institutes_are_refused(client, session, form, message):
    page = client.post("/dash/admin/institutes", data=form)
    assert page.status_code == 400 and message in page.text
    assert repo.institute_by_slug(session, form["slug"]) is None


def test_the_admin_can_switch_an_institute_off_and_on(client, session):
    make_institute(session, "bright")
    client.post("/dash/admin/institutes/bright/active")
    session.expire_all()
    assert repo.institute_by_slug(session, "bright").active is False
    client.post("/dash/admin/institutes/bright/active")
    session.expire_all()
    assert repo.institute_by_slug(session, "bright").active is True


def test_the_token_is_never_shown_again(client, session):
    client.post("/dash/admin/institutes", data=new_institute(token="999:SECRET"))
    assert "999:SECRET" not in client.get("/dash/admin/institutes").text


def test_owners_cannot_use_the_admin_actions(session):
    make_user(session, institute=make_institute(session, "bright"))
    owner = TestClient(app)
    owner.post("/dash/login", data={"email": "owner@bright.test", "password": "correct horse 1"})
    assert owner.post("/dash/admin/institutes", data=new_institute()).status_code == 404
    assert owner.post("/dash/admin/institutes/bright/active").status_code == 404
    assert repo.institute_by_slug(session, "bright").active is True

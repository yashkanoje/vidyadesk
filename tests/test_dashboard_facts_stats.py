import copy

import pytest
import yaml
from fastapi.testclient import TestClient

from helpers import FACTS, make_institute, make_lead, make_user
from leadagent.app import app
from leadagent.store.models import utcnow


@pytest.fixture
def client(session):
    make_user(session, institute=make_institute(session, "bright"))
    make_institute(session, "other")
    test_client = TestClient(app)
    test_client.post("/dash/login", data={"email": "owner@bright.test", "password": "correct horse 1"})
    return test_client


def test_the_facts_page_shows_the_current_facts(client):
    assert "₹68,000 per year" in client.get("/dash/bright/facts").text


def test_valid_facts_are_saved(client, session):
    changed = copy.deepcopy(FACTS)
    changed["courses"][0]["fee"] = "₹70,000 per year"
    page = client.post("/dash/bright/facts", data={"facts_yaml": yaml.safe_dump(changed, allow_unicode=True)})
    assert "Facts saved" in page.text
    from leadagent.store import repo

    session.expire_all()
    assert repo.institute_by_slug(session, "bright").facts["courses"][0]["fee"] == "₹70,000 per year"


@pytest.mark.parametrize("text, message", [("courses: [unclosed", "not valid YAML"), ("institute_name: X", "Invalid institute facts")])
def test_invalid_facts_are_refused_and_the_text_is_kept(client, session, text, message):
    page = client.post("/dash/bright/facts", data={"facts_yaml": text})
    assert page.status_code == 400
    assert message in page.text and text.split(":")[0] in page.text
    from leadagent.store import repo

    session.expire_all()
    assert repo.institute_by_slug(session, "bright").facts == FACTS


def test_stats_show_counts(client, session):
    from leadagent.store import repo

    bright = repo.institute_by_slug(session, "bright")
    make_lead(session, bright, "1", interest="hot", created_at=utcnow())
    make_lead(session, bright, "2", stage="handed_off", created_at=utcnow())
    page = client.get("/dash/bright/stats").text
    assert "2 leads" in page and "50% hot" in page and "1 waiting" in page


@pytest.mark.parametrize("method, path", [("get", "/dash/other/facts"), ("post", "/dash/other/facts"), ("get", "/dash/other/stats")])
def test_another_institutes_facts_and_stats_are_out_of_reach(client, method, path):
    response = client.post(path, data={"facts_yaml": "x"}) if method == "post" else client.get(path)
    assert response.status_code == 404


def test_stats_bars_scale_to_the_busiest_day(client, session):
    from datetime import timedelta

    from leadagent.store import repo

    bright = repo.institute_by_slug(session, "bright")
    for i in range(8):
        make_lead(session, bright, f"t{i}", created_at=utcnow())
    for i in range(4):
        make_lead(session, bright, f"y{i}", created_at=utcnow() - timedelta(days=1))
    page = client.get("/dash/bright/stats").text
    assert "width: 100%" in page and "width: 50%" in page

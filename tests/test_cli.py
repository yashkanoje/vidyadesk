import copy
from pathlib import Path

import pytest
from sqlalchemy import func, select

from helpers import FACTS
from leadagent.cli import add_institute, set_facts, set_owner
from leadagent.crypto import decrypt
from leadagent.facts import FactsError, load_facts_file, parse_facts
from leadagent.store.models import Institute

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def add(session, **overrides):
    values = {"slug": "bright", "name": "BrightPath Classes", "facts": parse_facts(FACTS), "telegram_token": "123:ABC"}
    values.update(overrides)
    return add_institute(session, **values)


def test_sample_institutes_are_valid():
    assert len(load_facts_file(EXAMPLES / "brightpath.yaml").courses) == 3
    assert len(load_facts_file(EXAMPLES / "vidya.yaml").courses) == 2


def test_add_institute_stores_encrypted_tokens_and_a_random_secret(session):
    institute = add(session, whatsapp_number_id="PN1", whatsapp_token="wa-secret")
    assert institute.telegram_bot_token_enc != "123:ABC"
    assert decrypt(institute.telegram_bot_token_enc) == "123:ABC"
    assert decrypt(institute.whatsapp_token_enc) == "wa-secret"
    assert len(institute.telegram_secret) >= 32
    assert institute.facts["courses"][0]["fee"] == "₹68,000 per year"
    other = add(session, slug="other")
    assert other.telegram_secret != institute.telegram_secret


@pytest.mark.parametrize("slug", ["Bright", "bright path", "", "a" * 65, "x/y"])
def test_bad_slugs_are_rejected(session, slug):
    with pytest.raises(ValueError):
        add(session, slug=slug)


def test_duplicate_slug_is_rejected(session):
    add(session)
    with pytest.raises(ValueError, match="already exists"):
        add(session)


def test_unknown_timezone_is_rejected(session):
    with pytest.raises(ValueError, match="timezone"):
        add(session, timezone="Asia/Rourkela")


def test_whatsapp_number_needs_a_token(session):
    with pytest.raises(ValueError, match="token"):
        add(session, whatsapp_number_id="PN1")


def test_set_facts_replaces_valid_facts_only(session):
    add(session)
    session.commit()
    changed = copy.deepcopy(FACTS)
    changed["courses"][0]["fee"] = "₹70,000 per year"
    set_facts(session, "bright", parse_facts(changed))
    assert session.scalars(select(Institute)).one().facts["courses"][0]["fee"] == "₹70,000 per year"
    with pytest.raises(FactsError):
        parse_facts({"institute_name": "x"})


def test_set_owner_and_unknown_slug(session):
    add(session)
    assert set_owner(session, "bright", "4242").owner_telegram_chat_id == "4242"
    with pytest.raises(ValueError, match="No institute"):
        set_owner(session, "nobody", "1")
    assert session.scalar(select(func.count()).select_from(Institute)) == 1

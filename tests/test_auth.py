import pytest
from sqlalchemy import select

from helpers import FACTS, make_institute
from leadagent.auth import LoginThrottle, PasswordError, dummy_hash, hash_password, password_matches
from leadagent.cli import add_institute, add_user, set_password
from leadagent.facts import parse_facts
from leadagent.store import repo
from leadagent.store.models import User


def test_a_hashed_password_matches_only_itself():
    hashed = hash_password("correct horse 1", rounds=4)
    assert hashed != "correct horse 1"
    assert password_matches("correct horse 1", hashed)
    assert not password_matches("correct horse 2", hashed)
    assert not password_matches("anything", "not-a-bcrypt-hash")


@pytest.mark.parametrize("password", ["short", "x" * 73, "ओ" * 30])
def test_too_short_or_too_long_passwords_are_refused(password):
    with pytest.raises(PasswordError):
        hash_password(password, rounds=4)


def test_the_dummy_hash_matches_no_password():
    assert not password_matches("correct horse 1", dummy_hash())


def test_the_throttle_blocks_after_five_failures_and_forgets_after_the_window():
    now = [0.0]
    throttle = LoginThrottle(limit=5, window=900, clock=lambda: now[0])
    for _ in range(5):
        assert not throttle.blocked("a@b")
        throttle.failed("a@b")
    assert throttle.blocked("a@b")
    assert not throttle.blocked("other@b")
    now[0] = 901
    assert not throttle.blocked("a@b")


def test_checking_an_unseen_key_stores_nothing():
    throttle = LoginThrottle()
    assert not throttle.blocked("never@failed")
    assert len(throttle._failures) == 0


def test_stale_keys_are_pruned_when_the_table_is_full():
    now = [0.0]
    throttle = LoginThrottle(window=900, max_keys=2, clock=lambda: now[0])
    for key in ("a@b", "c@d", "e@f"):
        throttle.failed(key)
    now[0] = 901
    throttle.failed("g@h")
    assert list(throttle._failures) == ["g@h"]


def test_a_successful_login_clears_the_failures():
    throttle = LoginThrottle(limit=2, window=900, clock=lambda: 0.0)
    throttle.failed("a@b")
    throttle.succeeded("a@b")
    throttle.failed("a@b")
    assert not throttle.blocked("a@b")


def test_add_user_stores_a_lowercase_email_and_a_hash(session):
    make_institute(session)
    user = add_user(session, email=" Owner@Bright.TEST ", password="correct horse 1", role="owner", slug="bright")
    session.commit()
    assert user.email == "owner@bright.test"
    assert password_matches("correct horse 1", user.password_hash)
    assert repo.user_by_email(session, "OWNER@bright.test").id == user.id


def test_add_user_checks_role_institute_and_duplicates(session):
    make_institute(session)
    with pytest.raises(ValueError, match="role"):
        add_user(session, email="x@y.z", password="correct horse 1", role="boss", slug="bright")
    with pytest.raises(ValueError, match="needs an institute"):
        add_user(session, email="x@y.z", password="correct horse 1", role="owner")
    with pytest.raises(ValueError, match="No institute"):
        add_user(session, email="x@y.z", password="correct horse 1", role="owner", slug="nobody")
    admin = add_user(session, email="admin@y.z", password="correct horse 1", role="admin")
    assert admin.institute_id is None
    with pytest.raises(ValueError, match="already"):
        add_user(session, email="ADMIN@y.z", password="correct horse 1", role="admin")


def test_set_password_replaces_the_hash(session):
    add_user(session, email="admin@y.z", password="correct horse 1", role="admin")
    set_password(session, "admin@y.z", "battery staple 2")
    user = session.scalars(select(User)).one()
    assert password_matches("battery staple 2", user.password_hash)
    with pytest.raises(ValueError, match="No user"):
        set_password(session, "nobody@y.z", "battery staple 2")


@pytest.mark.parametrize("slug", ["admin", "login", "logout"])
def test_dashboard_route_names_cannot_be_institute_slugs(session, slug):
    with pytest.raises(ValueError, match="reserved"):
        add_institute(session, slug=slug, name="X", facts=parse_facts(FACTS), telegram_token="1:A")

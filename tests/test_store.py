from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from helpers import make_institute, make_lead
from leadagent.store import repo
from leadagent.store.models import Lead, Message

NOON_IST = datetime(2026, 10, 14, 6, 30, tzinfo=timezone.utc)  # 12:00 in Asia/Kolkata
NIGHT_IST = datetime(2026, 10, 14, 20, 0, tzinfo=timezone.utc)  # 01:30 in Asia/Kolkata


def test_get_or_create_lead_is_idempotent(session):
    institute = make_institute(session)
    first = repo.get_or_create_lead(session, institute.id, "telegram", "111")
    second = repo.get_or_create_lead(session, institute.id, "telegram", "111")
    assert first.id == second.id
    assert first.stage == "new"
    assert first.phone is None


def test_whatsapp_lead_starts_with_its_phone_number(session):
    institute = make_institute(session)
    lead = repo.get_or_create_lead(session, institute.id, "whatsapp", "919861012345")
    assert lead.phone == "919861012345"


def test_partial_updates_merge_and_qualify(session):
    institute = make_institute(session)
    lead = make_lead(session, institute, stage="collecting")
    repo.save_lead_fields(session, lead, name=" Rahul Das ")
    assert (lead.name, lead.stage) == ("Rahul Das", "collecting")
    repo.save_lead_fields(session, lead, student_class="11", course="JEE")
    assert (lead.name, lead.student_class, lead.course) == ("Rahul Das", "11", "JEE")
    assert lead.stage == "qualified"


def test_empty_fields_do_not_erase_saved_ones(session):
    institute = make_institute(session)
    lead = make_lead(session, institute, name="Rahul")
    repo.save_lead_fields(session, lead, name="", course="NEET")
    assert (lead.name, lead.course) == ("Rahul", "NEET")


def test_saving_does_not_reopen_a_handed_off_lead(session):
    institute = make_institute(session)
    lead = make_lead(session, institute, stage="handed_off")
    repo.save_lead_fields(session, lead, name="A", student_class="11", course="JEE")
    assert lead.stage == "handed_off"


def test_duplicate_incoming_message_is_rejected(session):
    institute = make_institute(session)
    lead = make_lead(session, institute)
    assert repo.log_message(session, lead, "user", "hi", "tg:1") is True
    assert repo.log_message(session, lead, "user", "hi", "tg:1") is False
    assert session.scalar(select(func.count()).select_from(Message)) == 1


def test_same_message_id_is_allowed_in_another_institute(session):
    one = make_lead(session, make_institute(session, "one"))
    two = make_lead(session, make_institute(session, "two"))
    assert repo.log_message(session, one, "user", "hi", "tg:1") is True
    assert repo.log_message(session, two, "user", "hi", "tg:1") is True


def test_assistant_messages_never_count_as_duplicates(session):
    lead = make_lead(session, make_institute(session))
    assert repo.log_message(session, lead, "assistant", "hello") is True
    assert repo.log_message(session, lead, "assistant", "hello") is True


def test_touch_moves_new_to_collecting(session):
    lead = make_lead(session, make_institute(session))
    repo.touch_user_message(session, lead, NOON_IST)
    assert lead.stage == "collecting"
    assert lead.last_user_msg_at == NOON_IST


def test_message_count_covers_only_recent_user_messages(session):
    lead = make_lead(session, make_institute(session))
    for role, hours_ago in (("user", 1), ("user", 23), ("user", 25), ("assistant", 1)):
        session.add(
            Message(
                institute_id=lead.institute_id,
                lead_id=lead.id,
                role=role,
                text="x",
                created_at=NOON_IST - timedelta(hours=hours_ago),
            )
        )
    session.commit()
    assert repo.user_messages_last_24h(session, lead.id, NOON_IST) == 2


def test_recent_messages_are_oldest_first_and_limited(session):
    lead = make_lead(session, make_institute(session))
    for i in range(5):
        repo.log_message(session, lead, "user", f"m{i}")
    session.commit()
    assert [m.text for m in repo.recent_messages(session, lead.id, 3)] == ["m2", "m3", "m4"]


@pytest.mark.parametrize(
    "fields, hours_quiet, now, expected",
    [
        ({"stage": "collecting"}, 3, NOON_IST, True),
        ({"stage": "qualified", "interest": "warm"}, 3, NOON_IST, True),
        ({"stage": "collecting"}, 1, NOON_IST, False),  # too soon
        ({"stage": "collecting"}, 21, NOON_IST, False),  # too late
        ({"stage": "collecting", "nudged_at": NOON_IST}, 3, NOON_IST, False),  # already nudged
        ({"stage": "collecting", "interest": "cold"}, 3, NOON_IST, False),
        ({"stage": "new"}, 3, NOON_IST, False),
        ({"stage": "handed_off"}, 3, NOON_IST, False),
        ({"stage": "closed"}, 3, NOON_IST, False),
        ({"stage": "collecting"}, 3, NIGHT_IST, False),  # 01:30 local time
    ],
)
def test_due_nudges_rules(session, fields, hours_quiet, now, expected):
    institute = make_institute(session)
    lead = make_lead(session, institute, last_user_msg_at=now - timedelta(hours=hours_quiet), **fields)
    assert (lead.id in [due.id for due in repo.due_nudges(session, now)]) is expected


def test_no_nudges_for_an_inactive_institute(session):
    institute = make_institute(session, active=False)
    make_lead(session, institute, stage="collecting", last_user_msg_at=NOON_IST - timedelta(hours=3))
    assert repo.due_nudges(session, NOON_IST) == []


def test_get_lead_is_scoped_to_the_institute(session):
    one = make_institute(session, "one")
    two = make_institute(session, "two")
    lead = make_lead(session, one)
    assert repo.get_lead(session, one.id, lead.id).id == lead.id
    assert repo.get_lead(session, two.id, lead.id) is None


def test_deleting_a_lead_removes_its_messages(session):
    lead = make_lead(session, make_institute(session))
    repo.log_message(session, lead, "user", "hi", "tg:1")
    repo.delete_lead(session, lead)
    session.commit()
    assert session.scalar(select(func.count()).select_from(Lead)) == 0
    assert session.scalar(select(func.count()).select_from(Message)) == 0


def test_resume_returns_to_the_right_stage(session):
    institute = make_institute(session)
    complete = make_lead(
        session, institute, "1", stage="handed_off", name="A", student_class="11", course="JEE", handoff_reason="x"
    )
    partial = make_lead(session, institute, "2", stage="handed_off", name="B")
    repo.resume(session, complete)
    repo.resume(session, partial)
    assert (complete.stage, complete.handoff_reason) == ("qualified", None)
    assert partial.stage == "collecting"


def test_digest_leads_groups(session):
    institute = make_institute(session)
    other = make_institute(session, "other")
    new = make_lead(session, institute, "1", created_at=NOON_IST - timedelta(hours=2))
    old = make_lead(session, institute, "2", created_at=NOON_IST - timedelta(days=3))
    hot = make_lead(
        session,
        institute,
        "3",
        created_at=NOON_IST - timedelta(days=3),
        interest="hot",
        last_user_msg_at=NOON_IST - timedelta(hours=5),
    )
    waiting = make_lead(session, institute, "4", created_at=NOON_IST - timedelta(days=3), stage="handed_off")
    make_lead(session, other, "5", created_at=NOON_IST - timedelta(hours=2), interest="hot", stage="handed_off")
    new_leads, hot_leads, waiting_leads = repo.digest_leads(session, institute.id, NOON_IST)
    assert [lead.id for lead in new_leads] == [new.id]
    assert [lead.id for lead in hot_leads] == [hot.id]
    assert [lead.id for lead in waiting_leads] == [waiting.id]
    assert old.id not in [lead.id for lead in new_leads]


def test_leads_for_filters_and_orders_newest_first(session):
    institute = make_institute(session)
    other = make_institute(session, "other")
    old = make_lead(session, institute, "1", stage="handed_off", created_at=NOON_IST - timedelta(days=10))
    new = make_lead(session, institute, "2", stage="collecting", interest="hot", created_at=NOON_IST)
    make_lead(session, other, "3")
    assert [l.id for l in repo.leads_for(session, institute.id)] == [new.id, old.id]
    assert [l.id for l in repo.leads_for(session, institute.id, stage="handed_off")] == [old.id]
    assert [l.id for l in repo.leads_for(session, institute.id, interest="hot")] == [new.id]
    assert [l.id for l in repo.leads_for(session, institute.id, since=NOON_IST - timedelta(days=1))] == [new.id]


def test_lead_stats_count_per_local_day(session):
    institute = make_institute(session)
    make_lead(session, institute, "1", interest="hot", created_at=NOON_IST)
    make_lead(session, institute, "2", created_at=NOON_IST - timedelta(days=1))
    make_lead(session, institute, "3", stage="handed_off", created_at=NOON_IST - timedelta(days=30))
    stats = repo.lead_stats(session, institute.id, "Asia/Kolkata", NOON_IST, days=14)
    assert len(stats["per_day"]) == 14
    assert [count for _, count in stats["per_day"]][-2:] == [1, 1]
    assert (stats["total"], stats["hot"], stats["hot_share"], stats["waiting"]) == (2, 1, 50, 1)

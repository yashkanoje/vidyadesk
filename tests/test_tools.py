from helpers import make_institute, make_lead
from leadagent import notify
from leadagent.agent.tools import TOOLS, handoff, save_lead, set_interest


def cfg(lead):
    return {"configurable": {"institute_id": lead.institute_id, "lead_id": lead.id}}


def test_tool_schemas_do_not_expose_ids():
    for tool in TOOLS:
        assert "lead_id" not in tool.args
        assert "institute_id" not in tool.args
        assert "config" not in tool.args


def test_save_lead_writes_and_reports_what_is_missing(session):
    lead = make_lead(session, make_institute(session))
    result = save_lead.invoke({"name": "Rahul"}, cfg(lead))
    session.refresh(lead)
    assert lead.name == "Rahul"
    assert "class" in result and "course" in result
    result = save_lead.invoke({"student_class": "11", "course": "JEE"}, cfg(lead))
    session.refresh(lead)
    assert lead.stage == "qualified"
    assert "All details captured" in result


def test_hot_interest_alerts_the_owner_once(session, sent):
    lead = make_lead(session, make_institute(session), name="Rahul")
    set_interest.invoke({"level": "hot", "reason": "asked the admission date"}, cfg(lead))
    set_interest.invoke({"level": "hot", "reason": "asked again"}, cfg(lead))
    session.refresh(lead)
    assert lead.interest == "hot"
    assert len(sent) == 1
    channel, _, user_id, text = sent[0]
    assert (channel, user_id) == ("telegram", "999")
    assert f"#{lead.id}" in text and "Rahul" in text and "asked the admission date" in text


def test_warm_interest_does_not_alert(session, sent):
    lead = make_lead(session, make_institute(session))
    set_interest.invoke({"level": "warm", "reason": "asked fees"}, cfg(lead))
    assert sent == []


def test_handoff_sets_the_stage_and_alerts(session, sent):
    lead = make_lead(session, make_institute(session), stage="collecting")
    result = handoff.invoke({"reason": "asked for a person"}, cfg(lead))
    session.refresh(lead)
    assert (lead.stage, lead.handoff_reason) == ("handed_off", "asked for a person")
    assert f"/resume {lead.id}" in sent[0][3]
    assert "team will contact" in result


def test_tools_use_the_configured_lead_whatever_the_model_passes(session):
    institute = make_institute(session)
    mine = make_lead(session, institute, "1")
    other = make_lead(session, institute, "2", name="Someone Else")
    try:
        save_lead.invoke({"name": "Attacker", "lead_id": other.id, "institute_id": 999}, cfg(mine))
    except Exception:
        pass  # rejecting the extra arguments is also acceptable
    session.refresh(other)
    assert other.name == "Someone Else"


def test_tool_refuses_a_lead_from_another_institute(session):
    one = make_institute(session, "one")
    two = make_institute(session, "two")
    lead = make_lead(session, one)
    result = save_lead.invoke({"name": "X"}, {"configurable": {"institute_id": two.id, "lead_id": lead.id}})
    session.refresh(lead)
    assert lead.name is None
    assert "no longer exists" in result


def test_alert_without_an_owner_chat_is_dropped(session, sent):
    institute = make_institute(session, owner_chat_id=None)
    notify.alert(institute, "hello")
    assert sent == []


def test_describe_shows_what_is_known(session):
    institute = make_institute(session)
    full = make_lead(session, institute, "1", name="Rahul", student_class="11", course="JEE", phone="98610")
    empty = make_lead(session, institute, "2")
    assert notify.describe(full) == "Rahul · Class 11 · JEE · 98610"
    assert notify.describe(empty) == "Name not given · Class ? · Course ? · telegram user 2"

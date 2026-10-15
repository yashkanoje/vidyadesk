from datetime import datetime, timedelta, timezone

from langchain_core.messages import AIMessage

from helpers import ScriptedModel, make_institute, make_lead, run_turn
from leadagent.agent.graph import build_graph, get_checkpointer, thread_config
from leadagent.jobs import start_scheduler
from leadagent.jobs.digest import digest_text, run_digests
from leadagent.jobs.nudge import run_nudges
from leadagent.store import repo

NOON_IST = datetime(2026, 10, 14, 6, 30, tzinfo=timezone.utc)  # 12:00 in Asia/Kolkata
EIGHT_IST = datetime(2026, 10, 14, 2, 30, tzinfo=timezone.utc)  # 08:00 in Asia/Kolkata


def quiet_lead(session, institute, user_id="555"):
    return make_lead(session, institute, user_id, stage="collecting", last_user_msg_at=NOON_IST - timedelta(hours=3))


def test_a_quiet_lead_is_nudged_exactly_once(session, sent):
    institute = make_institute(session)
    lead = quiet_lead(session, institute)
    graph = build_graph(ScriptedModel(AIMessage("The fee is ₹68,000.")), get_checkpointer())
    run_turn(graph, lead, "JEE fee?")
    repo.log_message(session, lead, "user", "JEE fee?", "tg:1")
    session.commit()

    nudger = ScriptedModel(AIMessage("Hi! Would you like to try a free demo class?"))
    assert run_nudges(now=NOON_IST, model=nudger, graph=graph) == 1
    assert run_nudges(now=NOON_IST, model=nudger, graph=graph) == 0

    session.refresh(lead)
    assert lead.nudged_at == NOON_IST
    assert sent == [("telegram", institute.id, "555", "Hi! Would you like to try a free demo class?")]
    assert repo.recent_messages(session, lead.id, 1)[0].role == "assistant"
    # The agent must know it sent the nudge, or the user's "yes" will make no sense to it.
    state = graph.get_state(thread_config(institute.id, lead.id)).values["messages"]
    assert state[-1].content == "Hi! Would you like to try a free demo class?"
    # The nudge prompt carries the conversation and the institute's facts.
    system, request = nudger.calls[0]
    assert "₹68,000 per year" in system.content
    assert "JEE fee?" in request.content


def test_the_graph_still_works_after_a_nudge(session, sent):
    institute = make_institute(session)
    lead = quiet_lead(session, institute)
    model = ScriptedModel(AIMessage("The fee is ₹68,000."), AIMessage("Great, see you at the demo!"))
    graph = build_graph(model, get_checkpointer())
    run_turn(graph, lead, "JEE fee?")
    run_nudges(now=NOON_IST, model=ScriptedModel(AIMessage("Want a demo class?")), graph=graph)
    run_turn(graph, lead, "yes")
    assert [m.content for m in model.calls[1][1:]] == ["JEE fee?", "The fee is ₹68,000.", "Want a demo class?", "yes"]


def test_a_failed_model_call_still_uses_up_the_nudge(session, sent):
    institute = make_institute(session)
    lead = quiet_lead(session, institute)
    graph = build_graph(ScriptedModel(), get_checkpointer())
    assert run_nudges(now=NOON_IST, model=ScriptedModel(RuntimeError("API down")), graph=graph) == 0
    session.refresh(lead)
    assert lead.nudged_at == NOON_IST and sent == []


def test_one_failure_does_not_stop_the_other_nudges(session, sent):
    institute = make_institute(session)
    quiet_lead(session, institute, "1")
    quiet_lead(session, institute, "2")
    graph = build_graph(ScriptedModel(), get_checkpointer())
    nudger = ScriptedModel(RuntimeError("API down"), AIMessage("Still interested?"))
    assert run_nudges(now=NOON_IST, model=nudger, graph=graph) == 1
    assert [s[2] for s in sent] == ["2"]


def test_digest_text_lists_new_hot_and_waiting_leads(session):
    institute = make_institute(session)
    make_lead(session, institute, "1", created_at=EIGHT_IST - timedelta(hours=2))
    hot = make_lead(
        session, institute, "2", created_at=EIGHT_IST - timedelta(hours=3), name="Rahul", student_class="11",
        course="JEE", phone="98610", interest="hot", last_user_msg_at=EIGHT_IST - timedelta(hours=3),
    )
    waiting = make_lead(session, institute, "3", created_at=EIGHT_IST - timedelta(days=2), stage="handed_off", name="Priya")
    text = digest_text(session, institute, EIGHT_IST)
    assert "New leads in the last 24 hours: 2" in text
    assert f"#{hot.id} Rahul · Class 11 · JEE · 98610" in text
    assert f"#{waiting.id} Priya" in text


def test_digest_text_is_none_when_there_is_nothing_to_report(session):
    assert digest_text(session, make_institute(session), EIGHT_IST) is None


def test_digests_go_out_only_in_the_eight_oclock_half_hour(session, sent):
    institute = make_institute(session)
    make_lead(session, institute, "1", created_at=EIGHT_IST - timedelta(hours=2))
    assert run_digests(now=EIGHT_IST - timedelta(minutes=30)) == 0  # 07:30
    assert run_digests(now=EIGHT_IST + timedelta(minutes=30)) == 0  # 08:30
    assert run_digests(now=EIGHT_IST + timedelta(minutes=10)) == 1  # 08:10, a late run
    assert len(sent) == 1 and sent[0][2] == "999" and "Daily summary" in sent[0][3]


def test_digest_uses_each_institutes_own_timezone(session, sent):
    india = make_institute(session, "india")
    dubai = make_institute(session, "dubai")
    dubai.timezone = "Asia/Dubai"  # 08:00 there is 04:00 UTC
    session.commit()
    for institute in (india, dubai):
        make_lead(session, institute, "1", created_at=EIGHT_IST - timedelta(hours=1))
    run_digests(now=EIGHT_IST)
    assert [s[1] for s in sent] == [india.id]


def test_scheduler_has_both_jobs():
    scheduler = start_scheduler()
    try:
        assert sorted(job.id for job in scheduler.get_jobs()) == ["digests", "nudges"]
    finally:
        scheduler.shutdown(wait=False)


def test_a_late_follow_up_run_is_still_run():
    # On 15 Oct 2026 a run started 2.4 s late and was skipped: the scheduler's default allows 1 s.
    scheduler = start_scheduler()
    try:
        assert scheduler.get_job("nudges").misfire_grace_time >= 600
    finally:
        scheduler.shutdown(wait=False)

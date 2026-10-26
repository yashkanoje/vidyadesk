"""The demo video's building blocks (demo/): the recorded agent run, the narration and the scenes."""
import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from helpers import ScriptedModel, make_institute, tool_call
from leadagent.agent.graph import build_graph, get_checkpointer

DEMO = Path(__file__).resolve().parents[1] / "demo"
sys.path.insert(0, str(DEMO))

from run_chat import run_conversation  # noqa: E402  (demo/ is not a package)


def hot_lead_graph():
    model = ScriptedModel(
        tool_call("save_lead", name="Rahul Sharma", student_class="11", course="JEE"),
        tool_call("set_interest", level="hot", reason="wants to join this month"),
        AIMessage("68,000 a year."),
    )
    return build_graph(model, get_checkpointer())


def test_records_replies_lead_and_alerts(session):
    institute = make_institute(session)
    run = run_conversation(institute.id, [{"user_id": "demo-1", "turns": ["Fee?"]}], graph=hot_lead_graph(), pause=0)
    student = run["students"][0]
    assert student["turns"][0] == {"user": "Fee?", "reply": "68,000 a year."}
    assert student["lead"]["name"] == "Rahul Sharma" and student["lead"]["interest"] == "hot"
    assert any(alert.startswith("🔥 Hot lead #") for alert in run["alerts"])


def test_a_fallback_reply_stops_the_run(session):
    institute = make_institute(session)
    failing = build_graph(ScriptedModel(RuntimeError("model unavailable")), get_checkpointer())
    with pytest.raises(RuntimeError, match="fallback"):
        run_conversation(institute.id, [{"user_id": "demo-1", "turns": ["Fee?"]}], graph=failing, pause=0)

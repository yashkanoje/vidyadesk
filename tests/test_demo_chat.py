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


def test_narration_lines_match_the_approved_storyboard():
    from narration import SCENES, VOICE

    assert VOICE == "en-IN-PrabhatNeural"
    assert len(SCENES) == 10
    assert SCENES[0]["line"] == "It's 10:42 at night. A parent asks about JEE fees, and the institute is closed."
    assert SCENES[9]["line"] == "VidyaDesk. Every enquiry answered. Every lead captured."


def test_destructive_demo_steps_refuse_any_database_but_the_test_one():
    # 26 Oct 2026: shots.py truncated the MAIN database because the engine was bound before the env var changed.
    # The guard must check the live connection, not the setting.
    from sqlalchemy import create_engine

    from testdb import assert_test_database

    with pytest.raises(SystemExit, match="leadagent_test"):
        assert_test_database(create_engine("postgresql+psycopg://user@localhost/leadagent"))
    assert_test_database(create_engine("postgresql+psycopg://user@localhost/leadagent_test"))  # no error


def test_scenes_contain_no_chat_text_of_their_own():
    # Every chat line in the video must come from the recorded run, never be retyped into the page.
    import json

    page = (DEMO / "scenes" / "index.html").read_text(encoding="utf-8")
    run = json.loads((DEMO / "chat-run.json").read_text(encoding="utf-8"))
    assert "chat-run.json" in page and "narration.json" in page and "digest.json" in page
    for student in run["students"]:
        for turn in student["turns"]:
            for sentence in turn["reply"].replace("\n", " ").split(". "):
                if len(sentence) > 25:
                    assert sentence not in page

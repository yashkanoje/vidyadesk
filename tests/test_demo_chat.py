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


def test_switching_to_the_test_database_refuses_once_the_engine_exists(monkeypatch):
    # Under pytest leadagent.store.db is already imported: switching now would be too late, so it must refuse.
    from testdb import use_test_database

    with pytest.raises(SystemExit, match="before switching"):
        use_test_database()
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://user@localhost/leadagent")
    with pytest.raises(SystemExit, match="must point at the leadagent_test"):
        use_test_database()


def test_voice_lines_claim_only_what_the_code_does():
    from narration import SCENES

    lines = {scene["id"]: scene["line"] for scene in SCENES}
    assert lines["followup"] == ("If a student goes quiet, it follows up once, politely. "
                                 "On mornings with new, hot or waiting leads, the owner gets a summary at eight.")
    assert lines["problem"] == ("An enquiry can arrive in the evening or during class. "
                                "If nobody replies, the student may ask the next institute.")


def test_scene_labels_claim_only_what_the_code_does():
    page = (DEMO / "scenes" / "index.html").read_text(encoding="utf-8")
    assert "A person takes over" not in page  # the owner cannot reply through VidyaDesk; the relay is one way
    assert '"online"' not in page
    assert "Example scene" in page  # the 10:42 pm setting is staged
    assert "26/26 behaviour checks (one run)" in page
    assert "after the student's last message" in page


def test_the_voice_gets_phonetic_spellings_and_the_captions_keep_the_words():
    # Yash heard "lead" read as the metal (0:57) and "CSV" as "asv" (1:26) in the first render.
    from narration import SCENES, spoken

    assert spoken("the moment a lead is hot") == "the moment a leed is hot"
    assert spoken("new, hot or waiting leads") == "new, hot or waiting leeds"
    assert spoken("a CSV for Excel") == "a C S V for Excel"
    assert spoken("pleaded") == "pleaded"  # whole words only
    assert all("leed" not in scene["line"] and "C S V" not in scene["line"] for scene in SCENES)

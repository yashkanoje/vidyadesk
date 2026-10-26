"""Record a real agent run for the demo video.

Sends a short sample conversation (three fictional students) through the real pipeline and the real model, on the
TEST database only, and writes every reply, the saved lead and the owner alerts to demo/chat-run.json. The video
shows only text from that file.

    .\\.venv\\Scripts\\python demo\\run_chat.py
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _use_test_database() -> None:
    """Point the app at the test database before anything imports its settings. Refuses any other database."""
    from dotenv import dotenv_values

    test_db = os.environ.get("TEST_DATABASE_URL") or dotenv_values(ROOT / ".env").get("TEST_DATABASE_URL") or ""
    if not test_db.rstrip("/").endswith("leadagent_test"):
        sys.exit("refusing to run: TEST_DATABASE_URL must point at the leadagent_test database")
    os.environ["DATABASE_URL"] = test_db


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    _use_test_database()

from leadagent.channels.base import IncomingMsg  # noqa: E402
from leadagent.pipeline import FALLBACK, process  # noqa: E402
from leadagent.store import repo  # noqa: E402
from leadagent.store.db import session_scope  # noqa: E402

LEAD_FIELDS = ("name", "student_class", "course", "stage", "interest", "interest_reason", "handoff_reason")

DEMO_STUDENTS = [
    {
        "user_id": "demo-1",
        "turns": [
            "Hi, what is the fee for JEE coaching? My son is in class 11.",
            "His name is Rahul Sharma. We want to join this month. Is there a demo class?",
            "Can I talk to sir?",
            "OK, we will come on Saturday.",
        ],
    },
    {"user_id": "demo-2", "turns": ["नमस्ते, JEE कोचिंग की फीस कितनी है?"]},
    {"user_id": "demo-3", "turns": ["ନମସ୍କାର, JEE କୋଚିଂ ଫି କେତେ?"]},
]


def run_conversation(institute_id, students, graph=None, pause=12.0) -> dict:
    """Run each student's turns through the pipeline; return the replies, the saved leads and the owner alerts."""
    sends = []

    def record(institute, user_id, text, client=None):  # stands in for the Telegram API
        sends.append((str(user_id), text))

    with session_scope() as session:
        owner_chat = repo.get_institute(session, institute_id).owner_telegram_chat_id
    result = {"students": [], "alerts": []}
    with patch("leadagent.channels.telegram.send", record):
        for student in students:
            user_id, turns = student["user_id"], []
            for i, text in enumerate(student["turns"]):
                if pause and (turns or result["students"]):
                    time.sleep(pause)  # Gemini's free tier allows 15 requests a minute
                start = len(sends)
                process(IncomingMsg(institute_id, "telegram", user_id, f"demo:{user_id}:{i}", text), graph=graph)
                replies = [t for to, t in sends[start:] if to == user_id]
                if FALLBACK in replies:
                    raise RuntimeError(f"the model gave the fallback reply to {text!r}; run the demo again later")
                turns.append({"user": text, "reply": "\n".join(replies)})
            with session_scope() as session:
                lead = repo.find_lead(session, institute_id, "telegram", user_id)
                fields = {key: getattr(lead, key) for key in LEAD_FIELDS} if lead else {}
            result["students"].append({"user_id": user_id, "turns": turns, "lead": fields})
    result["alerts"] = [text for to, text in sends if to == owner_chat]
    return result


def main() -> int:
    from sqlalchemy import text

    from leadagent.cli import add_institute
    from leadagent.facts import load_facts_file
    from leadagent.rag.ingest import ingest
    from leadagent.settings import get_settings
    from leadagent.store.db import create_tables, engine

    create_tables()
    with engine.begin() as conn:  # the test database is scratch space; start from a clean sample institute
        conn.execute(text("TRUNCATE institutes, leads, messages, documents, chunks, users, checkpoints, "
                          "checkpoint_blobs, checkpoint_writes RESTART IDENTITY CASCADE"))
    with session_scope() as session:
        institute = add_institute(session, slug="brightpath", name="BrightPath Classes",
                                  facts=load_facts_file(ROOT / "examples" / "brightpath.yaml"), telegram_token="1:demo")
        institute.owner_telegram_chat_id = "999"
        institute_id = institute.id
    with session_scope() as session:
        print("prospectus:", ingest(session, institute_id, ROOT / "examples" / "brightpath-prospectus.txt").status)

    settings = get_settings()
    run = run_conversation(institute_id, DEMO_STUDENTS)
    run = {
        "model": settings.gemini_model if settings.llm_provider == "gemini" else settings.llm_provider,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "Real run of the VidyaDesk agent on the test database with fictional students. Shown word for word.",
        **run,
    }
    (HERE / "chat-run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    for student in run["students"]:
        for turn in student["turns"]:
            print(f"\n[{student['user_id']}] {turn['user']}\n  -> {turn['reply']}")
    print(f"\n{len(run['alerts'])} owner alerts; written to demo/chat-run.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

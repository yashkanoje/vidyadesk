import os
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
TEST_DB = os.environ.get("TEST_DATABASE_URL") or dotenv_values(ROOT / ".env").get("TEST_DATABASE_URL")
if not TEST_DB:
    raise RuntimeError("Set TEST_DATABASE_URL in .env or the environment")
_db_name = TEST_DB.rsplit("/", 1)[-1].split("?")[0]
if not _db_name.endswith("_test"):
    raise RuntimeError(
        f"Tests wipe the database. TEST_DATABASE_URL must name a database ending in _test, got {_db_name!r}"
    )

# Set before any leadagent module is imported, so tests never touch the real database or API.
os.environ["DATABASE_URL"] = TEST_DB
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["LLM_PROVIDER"] = "anthropic"
os.environ["GOOGLE_API_KEY"] = "test-key"
os.environ["FERNET_KEY"] = Fernet.generate_key().decode()
os.environ["WHATSAPP_APP_SECRET"] = "app-secret"
os.environ["WHATSAPP_VERIFY_TOKEN"] = "verify-me"
os.environ["LANGSMITH_TRACING"] = "false"


import pytest


@pytest.fixture(scope="session", autouse=True)
def _tables():
    from leadagent.agent.graph import get_checkpointer
    from leadagent.store.db import create_tables

    create_tables()
    get_checkpointer()  # creates LangGraph's checkpoint tables


@pytest.fixture(autouse=True)
def _clean(_tables):
    from sqlalchemy import text

    from leadagent.store.db import engine

    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE institutes, leads, messages, checkpoints, checkpoint_blobs, checkpoint_writes "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def session():
    from leadagent.store.db import SessionLocal

    with SessionLocal() as db:
        yield db


@pytest.fixture
def sent(monkeypatch):
    """Replace both channels' send functions and record what would have been sent."""
    calls = []

    def recorder(channel):
        def fake_send(institute, user_id, text, client=None):
            calls.append((channel, institute.id, str(user_id), text))

        return fake_send

    monkeypatch.setattr("leadagent.channels.telegram.send", recorder("telegram"))
    monkeypatch.setattr("leadagent.channels.whatsapp.send", recorder("whatsapp"))
    return calls

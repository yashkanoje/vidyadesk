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
os.environ["FERNET_KEY"] = Fernet.generate_key().decode()
os.environ["WHATSAPP_APP_SECRET"] = "app-secret"
os.environ["WHATSAPP_VERIFY_TOKEN"] = "verify-me"
os.environ["LANGSMITH_TRACING"] = "false"

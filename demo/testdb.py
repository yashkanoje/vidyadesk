"""Keep the demo scripts on the TEST database.

Imports nothing from leadagent: call use_test_database() before the first leadagent import, because the database
engine is created when leadagent.store.db is first imported. assert_test_database() checks the live engine itself and
must run right before any destructive SQL (26 Oct 2026: a demo script truncated the main database because the engine
had been bound before the setting changed).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_DATABASE = "leadagent_test"


def use_test_database() -> None:
    from dotenv import dotenv_values

    url = os.environ.get("TEST_DATABASE_URL") or dotenv_values(ROOT / ".env").get("TEST_DATABASE_URL") or ""
    if not url.rstrip("/").endswith(TEST_DATABASE):
        sys.exit(f"refusing to run: TEST_DATABASE_URL must point at the {TEST_DATABASE} database")
    if "leadagent.store.db" in sys.modules:
        sys.exit("refusing to run: the database engine was created before switching to the test database")
    os.environ["DATABASE_URL"] = url


def assert_test_database(engine) -> None:
    if engine.url.database != TEST_DATABASE:
        sys.exit(f"refusing to change database {engine.url.database!r}: demo scripts only touch {TEST_DATABASE}")

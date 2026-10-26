"""Dashboard screenshots for the demo video, from the recorded run.

Re-creates the sample institute, its leads and their messages on the TEST database from demo/chat-run.json (the same
real text), saves the app's real morning-summary text to demo/digest.json, then screenshots VidyaDesk pages with
headless Microsoft Edge into demo/build/shots/.

    .\\.venv\\Scripts\\python demo\\shots.py
"""
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SHOTS = HERE / "build" / "shots"
PORT = 8001
EDGE = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
from testdb import assert_test_database, use_test_database  # noqa: E402

use_test_database()  # before the first leadagent import, which creates the database engine
os.environ["SESSION_HTTPS_ONLY"] = "false"  # the preview server is plain http on localhost

import httpx  # noqa: E402
from PIL import Image  # noqa: E402
from sqlalchemy import text  # noqa: E402

from leadagent.cli import add_institute, add_user  # noqa: E402
from leadagent.facts import load_facts_file  # noqa: E402
from leadagent.jobs.digest import digest_text  # noqa: E402
from leadagent.store import repo  # noqa: E402
from leadagent.store.db import create_tables, engine, session_scope  # noqa: E402
from leadagent.store.models import utcnow  # noqa: E402

PAGES = {"home": "home", "conversation": "leads/1", "leads": "leads", "stats": "stats"}


def seed(run) -> str:
    """Rebuild the dashboard data from the run; return a fresh owner password (never printed)."""
    assert_test_database(engine)
    create_tables()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE institutes, leads, messages, documents, chunks, users, checkpoints, "
                          "checkpoint_blobs, checkpoint_writes RESTART IDENTITY CASCADE"))
    password = secrets.token_urlsafe(16)
    with session_scope() as session:
        institute = add_institute(session, slug="brightpath", name="BrightPath Classes",
                                  facts=load_facts_file(ROOT / "examples" / "brightpath.yaml"), telegram_token="1:demo")
        institute.owner_telegram_chat_id = "999"
        add_user(session, email="owner@demo.test", password=password, role="owner", slug="brightpath")
        for student in run["students"]:
            lead = repo.get_or_create_lead(session, institute.id, "telegram", student["user_id"])
            for turn in student["turns"]:
                repo.log_message(session, lead, "user", turn["user"])
                if turn["reply"]:
                    repo.log_message(session, lead, "assistant", turn["reply"])
            for key, value in student["lead"].items():
                setattr(lead, key, value)
            lead.last_user_msg_at = utcnow()
        session.flush()
        summary = digest_text(session, institute, utcnow())
    (HERE / "digest.json").write_text(json.dumps({"text": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    return password


def save_pages(password, folder: Path) -> None:
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "leadagent.app:app", "--port", str(PORT)],
                              cwd=ROOT, env=os.environ.copy(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{PORT}"
        for _ in range(60):
            try:
                httpx.get(base + "/dash/login", timeout=2)
                break
            except httpx.HTTPError:
                time.sleep(1)
        with httpx.Client(base_url=base) as client:
            login = client.post("/dash/login", data={"email": "owner@demo.test", "password": password})
            if login.status_code != 303 or not login.headers.get("location", "").endswith("/home"):
                raise RuntimeError(f"demo owner login failed: {login.status_code} {login.headers.get('location')} {login.text[:200]!r}")
            for name, path in PAGES.items():
                page = client.get(f"/dash/brightpath/{path}")
                page.raise_for_status()
                # Mark the intro as seen so the screenshot shows the dashboard itself.
                html = page.text.replace("<body", '<script>try{localStorage.setItem("vidyadesk-intro-seen","1")}catch(e){}</script><body', 1)
                (folder / f"{name}.html").write_text(html, encoding="utf-8")
    finally:
        server.terminate()


def shoot(url, png: Path, width, height) -> None:
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                        f"--window-size={width},{height}", "--virtual-time-budget=2000", f"--screenshot={png}", url],
                       capture_output=True, timeout=120)


def main() -> int:
    run = json.loads((HERE / "chat-run.json").read_text(encoding="utf-8"))
    SHOTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        save_pages(seed(run), folder)
        for name in PAGES:
            shoot((folder / f"{name}.html").as_uri(), SHOTS / f"laptop-{name}.png", 1920, 1080)
        for name in ("home", "conversation"):  # a true phone width needs an iframe: headless Edge won't go below ~500 px
            harness = folder / f"phone-{name}.html"
            harness.write_text(f'<!doctype html><body style="margin:0"><iframe src="{name}.html" width="390" height="844" '
                               f'style="border:0;display:block"></iframe></body>', encoding="utf-8")
            raw = folder / f"raw-{name}.png"
            shoot(harness.as_uri(), raw, 600, 844)
            Image.open(raw).crop((0, 0, 390, 844)).save(SHOTS / f"phone-{name}.png", optimize=True)
    for png in sorted(SHOTS.glob("*.png")):
        print(png.name, Image.open(png).size)
    return 0


if __name__ == "__main__":
    sys.exit(main())

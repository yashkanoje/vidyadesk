# Polish Round and M3 Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Part A fixes three weaknesses found in M2 (reply script, an untested question, PDF retrieval). Part B adds a web dashboard where an owner logs in to see leads and transcripts, act on leads, upload documents, edit facts and see stats, and where the admin manages institutes.

**Architecture:** The dashboard is server-rendered HTML (Jinja2 templates) inside the existing FastAPI app, under `/dash`. A signed session cookie (Starlette `SessionMiddleware`, HttpOnly, `SameSite=Strict`, HTTPS-only outside tests) carries the logged-in user's id. Every page that shows institute data is addressed as `/dash/<slug>/...` and checks that the user is the admin or the owner of that institute; anything else is a 404. All changes are `POST` forms.

**Tech Stack:** Existing stack plus `jinja2`, `python-multipart` (form and file parsing), `itsdangerous` (signed cookies), `bcrypt` (password hashes).

**Spec:** `docs/specs/2026-10-13-lead-agent-design.md`, Sections 6 (`users` table), 8 (dashboard), 11 (security), 13 (client-isolation tests), 15 (backlog items fixed in Part A).

## Global Constraints

- Owners see and change only their own institute. Every query is filtered by the logged-in user's `institute_id`. The admin sees all institutes. No self-signup: the admin creates owner accounts (spec Section 8).
- Passwords hashed with bcrypt. Session cookie signed, HTTPS-only, `SameSite=Strict`. All changes by POST. A limit on login attempts (spec Section 11): 5 failed attempts per email per 15 minutes.
- An institute page for an institute the user may not see answers 404, the same as a missing one, so slugs cannot be probed.
- Everything shown in HTML is escaped (Jinja2 autoescape, on by default for `.html`). User-written text (transcripts, names) must never run as HTML.
- CSV exports neutralise spreadsheet formulas: a cell starting with `=`, `+`, `-` or `@` gets a leading `'`.
- The dashboard must work on a phone (one stylesheet, viewport meta tag, tables scroll sideways).
- Unchanged from M1/M2: synchronous code, one process, no hardcoded absolute paths, never log a token or password, tests only against `leadagent_test`, tests never use the real embedding model.
- Shell commands are PowerShell, run from `PROJECT LEAD AGENT/`.

## Review Focus

1. **An owner who types another institute's slug or lead number into the address bar.** Expected: 404 on every page and every action. (Tasks 5–9)
2. **A student whose name or message contains HTML or a script.** Expected: shown as text in the transcript and the leads table, never run. (Task 6)
3. **A lead name starting with `=` exported to CSV and opened in Excel.** Expected: shown as text, not run as a formula. (Task 6)
4. **An uploaded file named `../../evil.txt` or `..`.** Expected: stored under its bare name or refused; nothing is written outside the temporary folder. (Task 7)
5. **Someone guessing passwords.** Expected: after 5 wrong attempts for one email, further attempts are refused for 15 minutes, even with the right password; the message never says whether the email exists. (Task 5)

---

# Part A — Polish round

### Task 1: Make the reply's script match the user's

The prompt already says to reply in the user's script, but Gemini sometimes answers a Devanagari question in Latin letters, or Odia written in Latin letters in Odia script. This adds a code-level check: if the final reply's script differs from the user's, the agent asks the model once to rewrite it.

**Files:**
- Create: `leadagent/language.py`, `tests/test_language.py`
- Modify: `evals/checks.py` (import `script_of` from `leadagent.language` instead of defining it), `leadagent/agent/graph.py` (`make_agent`), `tests/test_graph.py`

**Interfaces:**
- Produces: `script_of(text) -> str` ("odia", "devanagari", "latin" or "none"; moved unchanged from `evals/checks.py`), `rewrite_script(user_text, reply_text) -> str | None` (the script the reply must be rewritten into, or None), `REWRITE_INSTRUCTION: dict[str, str]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_language.py`:

```python
from leadagent.language import REWRITE_INSTRUCTION, rewrite_script, script_of


def test_script_of_moved_here_unchanged():
    assert script_of("ନମସ୍କାର, ଫି କେତେ?") == "odia"
    assert script_of("नमस्ते, फीस कितनी है?") == "devanagari"
    assert script_of("namaskar, fees kete?") == "latin"
    assert script_of("123 ?!") == "none"


def test_a_reply_in_another_script_must_be_rewritten():
    assert rewrite_script("क्या सेक्टर 19 से बस है?", "Yes, there is a bus from Sector 19.") == "devanagari"
    assert rewrite_script("mu sir sahita katha heba ku chahunchi", "ଆମର ଟିମ୍ ଶୀଘ୍ର ଯୋଗାଯୋଗ କରିବେ।") == "latin"
    assert rewrite_script("ଡେମୋ କ୍ଲାସ୍ ଅଛି କି?", "Haan, pehle do class free hain.") == "odia"


def test_a_reply_in_the_same_script_is_left_alone():
    assert rewrite_script("What is the fee?", "The fee is 68,000 rupees a year.") is None
    assert rewrite_script("नमस्ते", "नमस्ते! मैं सहायक हूँ।") is None
    assert rewrite_script("123", "Hello") is None  # the user wrote no letters at all
    assert rewrite_script("hello", "") is None


def test_every_target_script_has_an_instruction():
    assert set(REWRITE_INSTRUCTION) == {"odia", "devanagari", "latin"}
```

Append to `tests/test_graph.py`:

```python
def test_a_reply_in_the_wrong_script_is_rewritten_once(session):
    lead = make_lead(session, make_institute(session), stage="collecting")
    model = ScriptedModel(AIMessage("Yes, there is a bus from Sector 19."), AIMessage("हाँ, सेक्टर 19 से बस है।"))
    result = run_turn(build_graph(model, get_checkpointer()), lead, "क्या सेक्टर 19 से बस है?")
    assert message_text(result["messages"][-1]) == "हाँ, सेक्टर 19 से बस है।"
    assert len(model.calls) == 2
    assert "Devanagari" in model.calls[1][-1].content


def test_a_reply_in_the_right_script_is_not_rewritten(session):
    lead = make_lead(session, make_institute(session), stage="collecting")
    model = ScriptedModel(AIMessage("The fee is 68,000 rupees a year."))
    run_turn(build_graph(model, get_checkpointer()), lead, "What is the fee?")
    assert len(model.calls) == 1


def test_a_failed_rewrite_keeps_the_original_reply(session):
    lead = make_lead(session, make_institute(session), stage="collecting")
    model = ScriptedModel(AIMessage("Yes, there is a bus."), AIMessage(""))
    result = run_turn(build_graph(model, get_checkpointer()), lead, "क्या बस है?")
    assert message_text(result["messages"][-1]) == "Yes, there is a bus."
```

- [ ] **Step 2: Run them to see them fail**

Run: `.\.venv\Scripts\python -m pytest tests/test_language.py tests/test_graph.py -q`
Expected: `ModuleNotFoundError: No module named 'leadagent.language'`.

- [ ] **Step 3: Write the implementation**

`leadagent/language.py`:

```python
"""Which writing system a text uses, so the agent's reply can match the user's."""


def script_of(text) -> str:
    counts = {
        "odia": sum("଀" <= ch <= "୿" for ch in text),
        "devanagari": sum("ऀ" <= ch <= "ॿ" for ch in text),
        "latin": sum(ch.isascii() and ch.isalpha() for ch in text),
    }
    if not any(counts.values()):
        return "none"
    # A reply that mixes native script with English words (course names) counts as the native script.
    for script in ("odia", "devanagari"):
        if counts[script] >= 5:
            return script
    return max(counts, key=counts.get)


REWRITE_INSTRUCTION = {
    "devanagari": "Rewrite your last reply in Devanagari script, in the user's language. Keep the same meaning and facts. Reply with the rewritten message only.",
    "odia": "Rewrite your last reply in Odia script (ଓଡ଼ିଆ). Keep the same meaning and facts. Reply with the rewritten message only.",
    "latin": "Rewrite your last reply using English letters only, in the same language the user wrote in (for example Hinglish, or Odia written in English letters). Keep the same meaning and facts. Reply with the rewritten message only.",
}


def rewrite_script(user_text, reply_text):
    """The script the reply must be rewritten into, or None when it already matches the user's."""
    wanted, got = script_of(user_text), script_of(reply_text)
    if wanted == "none" or got == "none" or wanted == got:
        return None
    return wanted
```

In `evals/checks.py`, delete the `script_of` function and add `from leadagent.language import script_of` at the top (the tests import it from `evals.checks`, which keeps working).

In `leadagent/agent/graph.py`, add `from langchain_core.messages import HumanMessage` to the existing `langchain_core.messages` import, add `from leadagent.language import REWRITE_INSTRUCTION, rewrite_script`, and in `make_agent` replace the last line of `agent()`, `return {"messages": [model.invoke([system, *history], config)]}`, with:

```python
        reply = model.invoke([system, *history], config)
        user_text = next((m.content for m in reversed(history) if isinstance(m, HumanMessage)), "")
        wanted = None if reply.tool_calls else rewrite_script(str(user_text), message_text(reply))
        if wanted:
            # One retry when the reply's script differs from the user's; the instruction is not saved to the chat.
            rewrite = model.invoke([system, *history, reply, HumanMessage(REWRITE_INSTRUCTION[wanted])], config)
            text = message_text(rewrite).strip()
            if text and not rewrite.tool_calls:
                reply = AIMessage(content=text)
        return {"messages": [reply]}
```

- [ ] **Step 4: Run the tests**

Run: `.\.venv\Scripts\python -m pytest -q`
Expected: all pass, 1 skipped.

- [ ] **Step 5: Commit**

```powershell
git add leadagent/language.py leadagent/agent/graph.py evals/checks.py tests/test_language.py tests/test_graph.py
git commit -m "Rewrite a reply once when its script differs from the user's"
```

---

### Task 2: A behaviour check for the canteen question, and retrieval on a PDF

**Files:**
- Modify: `evals/conversations.yaml`, `evals/retrieval.py`

**Interfaces:**
- Consumes: `ingest`, `search`, `add_institute`, `load_facts_file`, `passage_hit`, `suggest_floor` (all existing)

- [ ] **Step 1: Add the canteen conversation**

In `evals/conversations.yaml`, after `en-missing-hostel`, add:

```yaml
- id: doc-canteen
  turns: ["Is there a canteen at the institute?"]
  expect: {handoff: true}
  review: The prospectus does not mention a canteen, but its closest passage scores above the similarity floor. Must not invent a canteen; hands off.
```

- [ ] **Step 2: Measure retrieval on a PDF copy too**

Replace `main()` in `evals/retrieval.py` with a `measure(path)` function and a `main()` that runs it on the text file and on a PDF made from it. Add `import tempfile` and `from fpdf import FPDF` to the imports.

```python
def make_pdf(text_path, pdf_path):
    """A PDF copy of the prospectus, so retrieval is also measured on what owners usually upload."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 6, text_path.read_text(encoding="utf-8"))
    pdf.output(str(pdf_path))
    return pdf_path


def measure(document_path, cases):
    """Return (hits, answerable scores, unanswerable scores, missed questions) for one document."""
    with session_scope() as session:
        institute_id = add_institute(
            session,
            slug=f"retrieval-{uuid.uuid4().hex[:8]}",
            name="Retrieval test",
            facts=load_facts_file(EXAMPLES / "brightpath.yaml"),
            telegram_token="unused",
        ).id
        status = ingest(session, institute_id, document_path).status
    print(f"{document_path.name}: {status}")
    hits, answerable, unanswerable, missed = 0, [], [], []
    try:
        with session_scope() as session:
            for case in cases:
                passages = search(session, institute_id, case["question"], k=3, min_similarity=0.0)
                top = passages[0].similarity if passages else 0.0
                if case["expect"] is None:
                    unanswerable.append(top)
                    continue
                answerable.append(top)
                if passage_hit([p.text for p in passages], case["expect"]):
                    hits += 1
                else:
                    missed.append(case["question"])
    finally:
        with session_scope() as session:
            session.delete(repo.get_institute(session, institute_id))
    return hits, answerable, unanswerable, missed


def main() -> int:
    cases = yaml.safe_load((HERE / "retrieval.yaml").read_text(encoding="utf-8"))
    create_tables()
    text_path = EXAMPLES / "brightpath-prospectus.txt"
    worst = 1.0
    with tempfile.TemporaryDirectory() as folder:
        for path in (text_path, make_pdf(text_path, Path(folder) / "brightpath-prospectus.pdf")):
            hits, answerable, unanswerable, missed = measure(path, cases)
            rate = hits / len(answerable)
            worst = min(worst, rate)
            print(f"  expected passage in the top 3: {hits} of {len(answerable)} = {rate:.0%} (target {TARGET:.0%})")
            for question in missed:
                print(f"    missed: {question}")
            print(f"  best similarity, answerable: lowest {min(answerable):.4f}; unanswerable: highest {max(unanswerable):.4f}")
            print(f"  suggested RAG_MIN_SIMILARITY: {suggest_floor(answerable, unanswerable)}")
    return 0 if worst >= TARGET else 1
```

- [ ] **Step 3: Run the retrieval measurement**

Run: `.\.venv\Scripts\python -m evals.retrieval`
Expected: two blocks (the `.txt` and the `.pdf`), each with a hit rate. The `.txt` block repeats M2's 21 of 21. Record both blocks in the commit message. If the PDF hit rate is under 80%, report it; do not change the floor or the chunking in this task.

- [ ] **Step 4: Run the tests and commit**

Run: `.\.venv\Scripts\python -m pytest -q`
Expected: all pass, 1 skipped.

```powershell
git add evals/conversations.yaml evals/retrieval.py
git commit -m "Add a canteen behaviour check and measure retrieval on a PDF copy"
```

---

### Task 3: Run the behaviour checks

This task has no code. The controller runs the full behaviour check as a detached process (it takes about 9 minutes, and long foreground runs have died with the session before), then an implementer reads the transcript.

- [ ] **Step 1: Run the checks**

```powershell
$env:PYTHONIOENCODING = "utf-8"
Start-Process -FilePath .\.venv\Scripts\python.exe -ArgumentList "-m","evals.run","--provider","gemini","--pause","12" -RedirectStandardOutput logs\eval-polish.out.log -RedirectStandardError logs\eval-polish.err.log -WindowStyle Hidden
```

Expected after about 9 minutes: `logs\eval-polish.out.log` ends with "N of 26 passed the automatic checks" and the transcript path. Target: 25 or 26 of 26, with `doc-bus-hindi`, `or-latin-human` and `doc-canteen` passing.

- [ ] **Step 2: Read the transcript and record the result**

Read every reply against its "Check by reading" line. In `docs/specs/2026-10-13-lead-agent-design.md` Section 16, add one sentence to the Gemini behaviour row with the new pass count, and in Section 15 mark the reply-script row as fixed by the rewrite check (or say what is still missing). Commit: `git commit -am "Record the polish-round behaviour checks"`.

---

# Part B — M3 dashboard

### Task 4: Users, passwords and login throttling

**Files:**
- Modify: `pyproject.toml`, `.env.example`, `leadagent/settings.py`, `leadagent/store/models.py`, `leadagent/store/repo.py`, `leadagent/cli.py`, `tests/conftest.py`, `tests/helpers.py`
- Create: `leadagent/auth.py`, `tests/test_auth.py`

**Interfaces:**
- Produces: model `User(id, email, password_hash, role, institute_id, created_at)`; `repo.add_user(session, email, password_hash, role, institute_id=None) -> User`, `repo.user_by_email(session, email) -> User | None`, `repo.get_user(session, user_id) -> User | None`.
- Produces: `auth.PasswordError(ValueError)`, `auth.check_new_password(password)`, `auth.hash_password(password, rounds=12) -> str`, `auth.password_matches(password, password_hash) -> bool`, `auth.dummy_hash() -> str`, class `auth.LoginThrottle(limit=5, window=900, clock=time.monotonic)` with `blocked(key) -> bool`, `failed(key)`, `succeeded(key)`, `reset()`.
- Produces: `Settings.session_secret: str = ""`, `Settings.session_https_only: bool = True`; `cli.add_user(session, *, email, password, role, slug=None) -> User`, `cli.set_password(session, email, password) -> User`; commands `add-user` and `set-password`; slugs `admin`, `login` and `logout` are refused by `add_institute`.
- Produces (tests): `helpers.make_user(session, email="owner@bright.test", password="correct horse 1", role="owner", institute=None) -> User` (hashes with `rounds=4` to keep tests fast).

- [ ] **Step 1: Dependencies, settings and test environment**

Add to `dependencies` in `pyproject.toml`:

```toml
    "jinja2>=3.1",
    "python-multipart>=0.0.9",
    "itsdangerous>=2.1",
    "bcrypt>=4.1",
```

Install: `.\.venv\Scripts\python -m pip install -e ".[dev]"`

Add to `Settings` in `leadagent/settings.py`, after `public_base_url`:

```python
    # Signs the dashboard's login cookie. Generate once: python -c "import secrets; print(secrets.token_urlsafe(32))"
    session_secret: str = ""
    # The login cookie is only sent over HTTPS. Set false only for local testing over plain http.
    session_https_only: bool = True
```

Add to `.env.example`, after `PUBLIC_BASE_URL=`:

```
# Dashboard login cookie: generate with python -c "import secrets; print(secrets.token_urlsafe(32))"
SESSION_SECRET=
```

In `tests/conftest.py`, add after the existing `os.environ[...]` lines:

```python
os.environ["SESSION_SECRET"] = "test-session-secret"
os.environ["SESSION_HTTPS_ONLY"] = "false"  # the test client talks plain http
```

and add `users` to the `TRUNCATE` list in `_clean` (after `institutes`).

- [ ] **Step 2: Write the failing tests**

`tests/test_auth.py`:

```python
import pytest
from sqlalchemy import select

from helpers import FACTS, make_institute
from leadagent.auth import LoginThrottle, PasswordError, dummy_hash, hash_password, password_matches
from leadagent.cli import add_institute, add_user, set_password
from leadagent.facts import parse_facts
from leadagent.store import repo
from leadagent.store.models import User


def test_a_hashed_password_matches_only_itself():
    hashed = hash_password("correct horse 1", rounds=4)
    assert hashed != "correct horse 1"
    assert password_matches("correct horse 1", hashed)
    assert not password_matches("correct horse 2", hashed)
    assert not password_matches("anything", "not-a-bcrypt-hash")


@pytest.mark.parametrize("password", ["short", "x" * 73, "ओ" * 30])
def test_too_short_or_too_long_passwords_are_refused(password):
    with pytest.raises(PasswordError):
        hash_password(password, rounds=4)


def test_the_dummy_hash_matches_no_password():
    assert not password_matches("correct horse 1", dummy_hash())


def test_the_throttle_blocks_after_five_failures_and_forgets_after_the_window():
    now = [0.0]
    throttle = LoginThrottle(limit=5, window=900, clock=lambda: now[0])
    for _ in range(5):
        assert not throttle.blocked("a@b")
        throttle.failed("a@b")
    assert throttle.blocked("a@b")
    assert not throttle.blocked("other@b")
    now[0] = 901
    assert not throttle.blocked("a@b")


def test_a_successful_login_clears_the_failures():
    throttle = LoginThrottle(limit=2, window=900, clock=lambda: 0.0)
    throttle.failed("a@b")
    throttle.succeeded("a@b")
    throttle.failed("a@b")
    assert not throttle.blocked("a@b")


def test_add_user_stores_a_lowercase_email_and_a_hash(session):
    make_institute(session)
    user = add_user(session, email=" Owner@Bright.TEST ", password="correct horse 1", role="owner", slug="bright")
    session.commit()
    assert user.email == "owner@bright.test"
    assert password_matches("correct horse 1", user.password_hash)
    assert repo.user_by_email(session, "OWNER@bright.test").id == user.id


def test_add_user_checks_role_institute_and_duplicates(session):
    make_institute(session)
    with pytest.raises(ValueError, match="role"):
        add_user(session, email="x@y.z", password="correct horse 1", role="boss", slug="bright")
    with pytest.raises(ValueError, match="needs an institute"):
        add_user(session, email="x@y.z", password="correct horse 1", role="owner")
    with pytest.raises(ValueError, match="No institute"):
        add_user(session, email="x@y.z", password="correct horse 1", role="owner", slug="nobody")
    admin = add_user(session, email="admin@y.z", password="correct horse 1", role="admin")
    assert admin.institute_id is None
    with pytest.raises(ValueError, match="already"):
        add_user(session, email="ADMIN@y.z", password="correct horse 1", role="admin")


def test_set_password_replaces_the_hash(session):
    add_user(session, email="admin@y.z", password="correct horse 1", role="admin")
    set_password(session, "admin@y.z", "battery staple 2")
    user = session.scalars(select(User)).one()
    assert password_matches("battery staple 2", user.password_hash)
    with pytest.raises(ValueError, match="No user"):
        set_password(session, "nobody@y.z", "battery staple 2")


@pytest.mark.parametrize("slug", ["admin", "login", "logout"])
def test_dashboard_route_names_cannot_be_institute_slugs(session, slug):
    with pytest.raises(ValueError, match="reserved"):
        add_institute(session, slug=slug, name="X", facts=parse_facts(FACTS), telegram_token="1:A")
```

- [ ] **Step 3: Run them to see them fail**

Run: `.\.venv\Scripts\python -m pytest tests/test_auth.py -q`
Expected: `ModuleNotFoundError: No module named 'leadagent.auth'`.

- [ ] **Step 4: Write the implementation**

`leadagent/auth.py`:

```python
"""Dashboard passwords and the limit on failed logins."""
import threading
import time
from collections import deque
from functools import lru_cache
import secrets

import bcrypt

MIN_LENGTH = 10
MAX_BYTES = 72  # bcrypt only uses the first 72 bytes of a password


class PasswordError(ValueError):
    """The new password is not acceptable. The message is safe to show."""


def check_new_password(password) -> None:
    if len(password) < MIN_LENGTH or len(password.encode()) > MAX_BYTES:
        raise PasswordError(f"A password needs at least {MIN_LENGTH} characters and at most {MAX_BYTES} bytes.")


def hash_password(password, rounds=12) -> str:
    check_new_password(password)
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=rounds)).decode()


def password_matches(password, password_hash) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:MAX_BYTES], password_hash.encode())
    except ValueError:  # not a bcrypt hash
        return False


@lru_cache
def dummy_hash() -> str:
    """Checked against when the email is unknown, so a wrong email takes as long as a wrong password."""
    return hash_password(secrets.token_urlsafe(32))


class LoginThrottle:
    """At most `limit` failed logins per key in `window` seconds.

    shortcut: kept in memory, so it resets on restart and works for one process only; move to the database before
    running more than one process.
    """

    def __init__(self, limit=5, window=900, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._failures: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _recent(self, key):
        failures = self._failures.setdefault(key, deque())
        now = self.clock()
        while failures and now - failures[0] > self.window:
            failures.popleft()
        return failures

    def blocked(self, key) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self.limit

    def failed(self, key) -> None:
        with self._lock:
            self._recent(key).append(self.clock())

    def succeeded(self, key) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
```

Append to `leadagent/store/models.py`:

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)  # stored lower-case
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(8))  # admin / owner
    institute_id: Mapped[int | None] = mapped_column(ForeignKey("institutes.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```

In `leadagent/store/repo.py`, add `User` to the models import and append:

```python
def add_user(session, email, password_hash, role, institute_id=None):
    user = User(email=email.strip().lower(), password_hash=password_hash, role=role, institute_id=institute_id)
    session.add(user)
    session.flush()
    return user


def user_by_email(session, email):
    return session.scalars(select(User).where(User.email == email.strip().lower())).one_or_none()


def get_user(session, user_id):
    return session.get(User, user_id)
```

In `leadagent/cli.py`:

1. Add `from leadagent.auth import PasswordError, hash_password` to the imports.
2. In `add_institute`, right after the slug regex check, add:

```python
    if slug in RESERVED_SLUGS:
        raise ValueError(f"{slug!r} is reserved for the dashboard; choose another slug")
```

and define above `add_institute`: `RESERVED_SLUGS = {"admin", "login", "logout"}  # dashboard routes live beside institute slugs`.

3. Add these functions after `set_whatsapp`:

```python
def add_user(session, *, email, password, role, slug=None):
    if role not in ("admin", "owner"):
        raise ValueError("role must be admin or owner")
    institute_id = None
    if role == "owner":
        if not slug:
            raise ValueError("an owner needs an institute (--slug)")
        institute_id = _existing(session, slug).id
    if repo.user_by_email(session, email) is not None:
        raise ValueError(f"A user with email {email.strip().lower()!r} already exists")
    return repo.add_user(session, email, hash_password(password), role, institute_id)


def set_password(session, email, password):
    user = repo.user_by_email(session, email)
    if user is None:
        raise ValueError(f"No user with email {email.strip().lower()!r}")
    user.password_hash = hash_password(password)
    return user
```

4. In `main()`, add the two sub-commands next to the others:

```python
    user = commands.add_parser("add-user")
    user.add_argument("--email", required=True)
    user.add_argument("--role", choices=["admin", "owner"], required=True)
    user.add_argument("--slug", help="the owner's institute")
    password = commands.add_parser("set-password")
    password.add_argument("--email", required=True)
```

and handle them inside the `with session_scope() as session:` block:

```python
            elif args.command in ("add-user", "set-password"):
                first = getpass.getpass("Password: ")
                if getpass.getpass("Password again: ") != first:
                    raise ValueError("the two passwords differ")
                if args.command == "add-user":
                    created = add_user(session, email=args.email, password=first, role=args.role, slug=args.slug)
                    print(f"Added {created.role} {created.email}.")
                else:
                    set_password(session, args.email, first)
                    print("Password changed.")
```

and add `PasswordError` to the `except (ValueError, FactsError)` tuple (it is a `ValueError`, so this is only for clarity: leave the tuple as it is if you prefer).

5. In the module docstring, add `python -m leadagent.cli add-user --email owner@example.com --role owner --slug brightpath`.

In `tests/helpers.py`, add `from leadagent.auth import hash_password` and `User` to the models import, then append:

```python
def make_user(session, email="owner@bright.test", password="correct horse 1", role="owner", institute=None):
    user = User(
        email=email,
        password_hash=hash_password(password, rounds=4),
        role=role,
        institute_id=institute.id if institute else None,
    )
    session.add(user)
    session.commit()
    return user
```

- [ ] **Step 5: Run the tests**

Run: `.\.venv\Scripts\python -m pytest -q`
Expected: all pass, 1 skipped.

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml .env.example leadagent tests
git commit -m "Add dashboard users, bcrypt passwords and a login throttle"
```

---

### Task 5: Dashboard login, logout and access rules

**Files:**
- Create: `leadagent/dashboard/__init__.py`, `leadagent/dashboard/routes.py`, `leadagent/dashboard/templates/base.html`, `leadagent/dashboard/templates/login.html`, `tests/test_dashboard_auth.py`
- Modify: `leadagent/app.py`, `tests/conftest.py`

**Interfaces:**
- Consumes: `LoginThrottle`, `password_matches`, `dummy_hash`, `repo.user_by_email`, `repo.get_user`, `repo.get_institute`, `repo.institute_by_slug`, `session_scope`
- Produces: `routes.router` (prefix `/dash`), `routes.templates`, `routes.throttle`, helpers `_user(session, request) -> User` (303 to `/dash/login` when not logged in), `_admin(session, request) -> User` (404 for non-admins), `_institute(session, user, slug) -> Institute` (404 when missing or not the user's), `_render(request, name, context, status_code=200)` (adds `flash` popped from the session), `_flash(request, text)`, `_local(institute)` (a function formatting a UTC datetime in the institute's timezone). Routes: `GET /dash`, `GET /dash/login`, `POST /dash/login`, `POST /dash/logout`.

- [ ] **Step 1: Reset the throttle between tests**

Append to `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def _reset_login_throttle():
    from leadagent.dashboard.routes import throttle

    throttle.reset()
```

- [ ] **Step 2: Write the failing tests**

`tests/test_dashboard_auth.py`:

```python
import pytest
from fastapi.testclient import TestClient

from helpers import make_institute, make_user
from leadagent.app import app


@pytest.fixture
def client():
    return TestClient(app)  # not a context manager: start-up (scheduler, model warm-up) does not run


def login(client, email="owner@bright.test", password="correct horse 1"):
    return client.post("/dash/login", data={"email": email, "password": password}, follow_redirects=False)


def test_the_login_page_renders(client):
    response = client.get("/dash/login")
    assert response.status_code == 200
    assert 'name="password"' in response.text and 'name="viewport"' in response.text


@pytest.mark.parametrize("path", ["/dash", "/dash/bright/leads", "/dash/admin/institutes"])
def test_pages_need_a_login(client, session, path):
    make_institute(session)
    response = client.get(path, follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, "/dash/login")


def test_an_owner_logs_in_to_their_leads(client, session):
    make_user(session, institute=make_institute(session))
    response = login(client)
    assert (response.status_code, response.headers["location"]) == (303, "/dash/bright/leads")
    assert client.get("/dash", follow_redirects=False).headers["location"] == "/dash/bright/leads"


def test_the_admin_logs_in_to_the_institute_list(client, session):
    make_user(session, email="admin@lead.test", role="admin")
    assert login(client, email="admin@lead.test").headers["location"] == "/dash/admin/institutes"


def test_email_case_and_spaces_do_not_matter(client, session):
    make_user(session, institute=make_institute(session))
    assert login(client, email="  OWNER@Bright.test ").status_code == 303


def test_a_wrong_password_and_an_unknown_email_get_the_same_answer(client, session):
    make_user(session, institute=make_institute(session))
    wrong = login(client, password="not the password")
    unknown = login(client, email="nobody@bright.test")
    assert wrong.status_code == unknown.status_code == 401
    assert "Wrong email or password" in wrong.text and "Wrong email or password" in unknown.text


def test_five_failures_block_even_the_right_password(client, session):
    make_user(session, institute=make_institute(session))
    for _ in range(5):
        assert login(client, password="not the password").status_code == 401
    blocked = login(client)
    assert blocked.status_code == 429 and "Too many failed attempts" in blocked.text


def test_logging_out_ends_the_session(client, session):
    make_user(session, institute=make_institute(session))
    login(client)
    assert client.post("/dash/logout", follow_redirects=False).headers["location"] == "/dash/login"
    assert client.get("/dash/bright/leads", follow_redirects=False).status_code == 303


def test_the_session_cookie_is_httponly_and_strict(client, session):
    make_user(session, institute=make_institute(session))
    cookie = login(client).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_a_deleted_user_is_logged_out(client, session):
    user = make_user(session, institute=make_institute(session))
    login(client)
    session.delete(user)
    session.commit()
    assert client.get("/dash", follow_redirects=False).headers["location"] == "/dash/login"


def test_an_owner_cannot_open_the_admin_pages(client, session):
    make_user(session, institute=make_institute(session))
    login(client)
    assert client.get("/dash/admin/institutes").status_code == 404
```

(The `/dash/bright/leads` and `/dash/admin/institutes` pages are added in Tasks 6 and 9; until then the tests that reach them expect a login redirect or a 404, which the access rules in this task already produce. To keep this task's run green, add the two placeholder routes in Step 3 as shown and replace them in their own tasks.)

- [ ] **Step 3: Write the implementation**

`leadagent/dashboard/__init__.py`:

```python
"""The owner and admin web dashboard, served by the main app under /dash."""
from leadagent.dashboard.routes import router

__all__ = ["router"]
```

`leadagent/dashboard/routes.py`:

```python
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from leadagent.auth import LoginThrottle, dummy_hash, password_matches
from leadagent.store import repo
from leadagent.store.db import session_scope

log = logging.getLogger(__name__)
router = APIRouter(prefix="/dash")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
throttle = LoginThrottle()


def _user(session, request):
    user_id = request.session.get("user_id")
    user = repo.get_user(session, user_id) if isinstance(user_id, int) else None
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=303, headers={"Location": "/dash/login"})
    return user


def _admin(session, request):
    user = _user(session, request)
    if user.role != "admin":
        raise HTTPException(404)
    return user


def _institute(session, user, slug):
    institute = repo.institute_by_slug(session, slug)
    # The same answer for "no such institute" and "not yours", so slugs cannot be probed.
    if institute is None or (user.role != "admin" and user.institute_id != institute.id):
        raise HTTPException(404)
    return institute


def _home(session, user) -> str:
    if user.role == "admin":
        return "/dash/admin/institutes"
    return f"/dash/{repo.get_institute(session, user.institute_id).slug}/leads"


def _local(institute):
    zone = ZoneInfo(institute.timezone)
    return lambda moment: moment.astimezone(zone).strftime("%d %b %Y %H:%M") if moment else ""


def _flash(request, text) -> None:
    request.session["flash"] = text


def _render(request, name, context, status_code=200):
    return templates.TemplateResponse(
        request, name, {"flash": request.session.pop("flash", None), **context}, status_code=status_code
    )


@router.get("")
def home(request: Request):
    with session_scope() as session:
        return RedirectResponse(_home(session, _user(session, request)), status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return _render(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    key = email.strip().lower()
    if throttle.blocked(key):
        return _render(
            request, "login.html", {"error": "Too many failed attempts. Try again in 15 minutes."}, status_code=429
        )
    with session_scope() as session:
        user = repo.user_by_email(session, key)
        if not password_matches(password, user.password_hash if user else dummy_hash()) or user is None:
            throttle.failed(key)
            return _render(request, "login.html", {"error": "Wrong email or password."}, status_code=401)
        throttle.succeeded(key)
        request.session.clear()  # a fresh session on every login
        request.session["user_id"] = user.id
        return RedirectResponse(_home(session, user), status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/dash/login", status_code=303)


# Placeholders until Tasks 6 and 9 replace them: they already apply the access rules.
@router.get("/admin/institutes", response_class=HTMLResponse)
def institutes_page(request: Request):
    with session_scope() as session:
        _admin(session, request)
        return HTMLResponse("Institutes")


@router.get("/{slug}/leads", response_class=HTMLResponse)
def leads_page(request: Request, slug: str):
    with session_scope() as session:
        _institute(session, _user(session, request), slug)
        return HTMLResponse("Leads")
```

`leadagent/dashboard/templates/base.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}Lead agent{% endblock %}</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 0; color: #1d2433; background: #f6f7f9; }
  header { background: #1d2433; color: #fff; padding: 10px 16px; display: flex; flex-wrap: wrap; gap: 14px; align-items: center; }
  header a { color: #fff; text-decoration: none; }
  header form { margin-left: auto; }
  main { padding: 16px; max-width: 1000px; margin: 0 auto; }
  table { border-collapse: collapse; width: 100%; background: #fff; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #e3e6ea; vertical-align: top; }
  .scroll { overflow-x: auto; }
  .flash { background: #e8f4ea; padding: 8px 12px; border-radius: 4px; }
  .error { background: #fbeaea; padding: 8px 12px; border-radius: 4px; white-space: pre-wrap; }
  .msg { background: #fff; padding: 8px 12px; margin: 6px 0; border-radius: 6px; white-space: pre-wrap; }
  .msg.user { border-left: 4px solid #3b6fd8; }
  .msg.assistant { border-left: 4px solid #2e9e5b; }
  .msg.owner { border-left: 4px solid #b26b00; }
  textarea { width: 100%; min-height: 360px; font-family: monospace; box-sizing: border-box; }
  input, select, button { font-size: 1rem; padding: 4px 8px; }
  .bar { display: inline-block; background: #3b6fd8; height: 12px; }
  .inline { display: inline; }
</style>
</head>
<body>
{% if user %}
<header>
  {% if institute %}
  <strong>{{ institute.name }}</strong>
  <a href="/dash/{{ institute.slug }}/leads">Leads</a>
  <a href="/dash/{{ institute.slug }}/documents">Documents</a>
  <a href="/dash/{{ institute.slug }}/facts">Facts</a>
  <a href="/dash/{{ institute.slug }}/stats">Stats</a>
  {% endif %}
  {% if user.role == "admin" %}<a href="/dash/admin/institutes">Institutes</a>{% endif %}
  <form method="post" action="/dash/logout"><button>Log out</button></form>
</header>
{% endif %}
<main>
{% if flash %}<p class="flash">{{ flash }}</p>{% endif %}
{% block content %}{% endblock %}
</main>
</body>
</html>
```

`leadagent/dashboard/templates/login.html`:

```html
{% extends "base.html" %}
{% block title %}Log in{% endblock %}
{% block content %}
<h1>Log in</h1>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post" action="/dash/login">
  <p><label>Email<br><input type="email" name="email" required autocomplete="username"></label></p>
  <p><label>Password<br><input type="password" name="password" required autocomplete="current-password"></label></p>
  <p><button>Log in</button></p>
</form>
{% endblock %}
```

In `leadagent/app.py`, add these imports:

```python
import secrets

from starlette.middleware.sessions import SessionMiddleware

from leadagent.dashboard import router as dashboard_router
```

and right after `app = FastAPI(lifespan=lifespan)`:

```python
_session_secret = get_settings().session_secret
if not _session_secret:
    # Logins still work, but everyone is logged out whenever the app restarts.
    logging.getLogger(__name__).warning("SESSION_SECRET is not set; using a random one for this run")
    _session_secret = secrets.token_urlsafe(32)
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    same_site="strict",
    https_only=get_settings().session_https_only,
    max_age=7 * 24 * 3600,
)
app.include_router(dashboard_router)
```

- [ ] **Step 4: Run the tests**

Run: `.\.venv\Scripts\python -m pytest tests/test_dashboard_auth.py -v`
Expected: 13 passed.

Run: `.\.venv\Scripts\python -m pytest -q`
Expected: all pass, 1 skipped.

- [ ] **Step 5: Commit**

```powershell
git add leadagent/dashboard leadagent/app.py tests
git commit -m "Add dashboard login, logout and access rules"
```

---

### Task 6: Leads: list, filters, CSV, detail and actions

**Files:**
- Create: `leadagent/actions.py`, `leadagent/dashboard/templates/leads.html`, `leadagent/dashboard/templates/lead.html`, `tests/test_dashboard_leads.py`
- Modify: `leadagent/store/repo.py`, `leadagent/commands.py`, `leadagent/cli.py`, `leadagent/dashboard/routes.py`

**Interfaces:**
- Produces: `actions.delete_lead_and_history(session, lead) -> None` (lead, messages and chat state, under the lead's lock); `repo.leads_for(session, institute_id, stage=None, interest=None, since=None) -> list[Lead]` (newest first), `repo.messages_for(session, institute_id, lead_id) -> list[Message]`, `repo.close_lead(session, lead) -> None`; constants `STAGES`, `INTERESTS` in `routes`; routes `GET /dash/{slug}/leads`, `GET /dash/{slug}/leads.csv`, `GET /dash/{slug}/leads/{lead_id}`, `POST /dash/{slug}/leads/{lead_id}/{action}` with action `resume`, `close` or `delete`.

- [ ] **Step 1: Write the failing tests**

`tests/test_dashboard_leads.py`:

```python
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import func, select

from helpers import ScriptedModel, make_institute, make_lead, make_user, run_turn
from leadagent.agent.graph import build_graph, get_checkpointer, thread_config
from leadagent.app import app
from leadagent.store import repo
from leadagent.store.models import Lead, Message


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def two_institutes(session):
    mine = make_institute(session, "bright")
    theirs = make_institute(session, "other")
    make_user(session, institute=mine)
    return mine, theirs


def login(client, email="owner@bright.test"):
    client.post("/dash/login", data={"email": email, "password": "correct horse 1"})


def test_the_leads_page_lists_this_institutes_leads_only(client, session, two_institutes):
    mine, theirs = two_institutes
    make_lead(session, mine, "1", name="Rahul")
    make_lead(session, theirs, "2", name="Secret Student")
    login(client)
    page = client.get("/dash/bright/leads")
    assert page.status_code == 200
    assert "Rahul" in page.text and "Secret Student" not in page.text


def test_filters_by_stage_and_interest(client, session, two_institutes):
    mine, _ = two_institutes
    make_lead(session, mine, "1", name="Waiting One", stage="handed_off")
    make_lead(session, mine, "2", name="Hot One", stage="collecting", interest="hot")
    login(client)
    assert "Hot One" not in client.get("/dash/bright/leads?stage=handed_off").text
    assert "Waiting One" not in client.get("/dash/bright/leads?interest=hot").text
    assert "Waiting One" in client.get("/dash/bright/leads?stage=nonsense").text  # an unknown filter is ignored


def test_html_in_student_text_is_shown_as_text(client, session, two_institutes):
    mine, _ = two_institutes
    lead = make_lead(session, mine, "1", name="<script>alert(1)</script>")
    repo.log_message(session, lead, "user", "<img src=x onerror=alert(2)>")
    session.commit()
    login(client)
    for page in (client.get("/dash/bright/leads"), client.get(f"/dash/bright/leads/{lead.id}")):
        assert "<script>alert(1)</script>" not in page.text
        assert "&lt;script&gt;" in page.text
    assert "<img src=x" not in client.get(f"/dash/bright/leads/{lead.id}").text


def test_the_detail_page_shows_the_transcript_in_order(client, session, two_institutes):
    mine, _ = two_institutes
    lead = make_lead(session, mine, "1", name="Rahul")
    for role, text in (("user", "JEE fee?"), ("assistant", "68,000 rupees a year."), ("user", "Thanks")):
        repo.log_message(session, lead, role, text)
    session.commit()
    login(client)
    text = client.get(f"/dash/bright/leads/{lead.id}").text
    assert text.index("JEE fee?") < text.index("68,000 rupees a year.") < text.index("Thanks")


def test_csv_export_has_the_leads_and_neutralises_formulas(client, session, two_institutes):
    mine, theirs = two_institutes
    make_lead(session, mine, "1", name="=HYPERLINK(\"http://evil\")", course="JEE")
    make_lead(session, theirs, "2", name="Secret Student")
    login(client)
    response = client.get("/dash/bright/leads.csv")
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.startswith("﻿")  # so Excel reads Odia and Hindi names correctly
    assert "'=HYPERLINK" in response.text and "Secret Student" not in response.text


def test_resume_and_close(client, session, two_institutes):
    mine, _ = two_institutes
    lead = make_lead(session, mine, "1", stage="handed_off", name="Rahul")
    login(client)
    assert client.post(f"/dash/bright/leads/{lead.id}/resume", follow_redirects=False).status_code == 303
    session.refresh(lead)
    assert lead.stage == "collecting"
    client.post(f"/dash/bright/leads/{lead.id}/close")
    session.refresh(lead)
    assert lead.stage == "closed"


def test_delete_removes_the_lead_its_messages_and_its_chat_state(client, session, two_institutes):
    mine, _ = two_institutes
    lead = make_lead(session, mine, "1", stage="collecting")
    graph = build_graph(ScriptedModel(AIMessage("Hello!")), get_checkpointer())
    run_turn(graph, lead, "hi")
    repo.log_message(session, lead, "user", "hi")
    session.commit()
    login(client)
    response = client.post(f"/dash/bright/leads/{lead.id}/delete", follow_redirects=False)
    assert response.headers["location"] == "/dash/bright/leads"
    assert session.scalar(select(func.count()).select_from(Lead)) == 0
    assert session.scalar(select(func.count()).select_from(Message)) == 0
    assert graph.get_state(thread_config(mine.id, lead.id)).values == {}


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/dash/other/leads"),
        ("get", "/dash/other/leads.csv"),
        ("get", "/dash/other/leads/{theirs}"),
        ("get", "/dash/bright/leads/{theirs}"),
        ("post", "/dash/other/leads/{theirs}/delete"),
        ("post", "/dash/bright/leads/{theirs}/delete"),
        ("post", "/dash/bright/leads/{theirs}/resume"),
        ("post", "/dash/bright/leads/{mine}/explode"),
    ],
)
def test_an_owner_gets_404_for_anything_not_theirs(client, session, two_institutes, method, path):
    mine, theirs = two_institutes
    my_lead = make_lead(session, mine, "1", stage="handed_off")
    their_lead = make_lead(session, theirs, "2", stage="handed_off")
    login(client)
    response = getattr(client, method)(path.format(mine=my_lead.id, theirs=their_lead.id), follow_redirects=False)
    assert response.status_code == 404
    session.refresh(their_lead)
    assert their_lead.stage == "handed_off"


def test_the_admin_sees_every_institute(client, session, two_institutes):
    _, theirs = two_institutes
    make_lead(session, theirs, "2", name="Other Student")
    make_user(session, email="admin@lead.test", role="admin")
    login(client, email="admin@lead.test")
    assert "Other Student" in client.get("/dash/other/leads").text
```

Add to `tests/test_store.py`:

```python
def test_leads_for_filters_and_orders_newest_first(session):
    institute = make_institute(session)
    other = make_institute(session, "other")
    old = make_lead(session, institute, "1", stage="handed_off", created_at=NOON_IST - timedelta(days=10))
    new = make_lead(session, institute, "2", stage="collecting", interest="hot", created_at=NOON_IST)
    make_lead(session, other, "3")
    assert [l.id for l in repo.leads_for(session, institute.id)] == [new.id, old.id]
    assert [l.id for l in repo.leads_for(session, institute.id, stage="handed_off")] == [old.id]
    assert [l.id for l in repo.leads_for(session, institute.id, interest="hot")] == [new.id]
    assert [l.id for l in repo.leads_for(session, institute.id, since=NOON_IST - timedelta(days=1))] == [new.id]
```

- [ ] **Step 2: Run them to see them fail**

Run: `.\.venv\Scripts\python -m pytest tests/test_dashboard_leads.py tests/test_store.py -q`
Expected: failures (the placeholder leads page shows no leads; `repo.leads_for` does not exist).

- [ ] **Step 3: Write the implementation**

`leadagent/actions.py`:

```python
"""Owner actions shared by the Telegram commands, the command line and the dashboard."""
from leadagent.agent.graph import get_checkpointer
from leadagent.locks import lock_for
from leadagent.store import repo


def delete_lead_and_history(session, lead) -> None:
    """Delete a lead, its messages and its chat state. Waits for any reply being written for it."""
    lead_id = lead.id
    with lock_for(lead_id):
        repo.delete_lead(session, lead)
        session.flush()
        get_checkpointer().delete_thread(str(lead_id))
```

In `leadagent/commands.py`, replace the `with lock_for(lead.id): ... delete_thread(...)` block with `delete_lead_and_history(session, lead)` (import it from `leadagent.actions`; remove imports that are no longer used). Do the same in `leadagent/cli.py` `set_owner`. The existing tests for `/delete` and `set-owner` cover both.

Append to `leadagent/store/repo.py`:

```python
def leads_for(session, institute_id, stage=None, interest=None, since=None):
    query = select(Lead).where(Lead.institute_id == institute_id)
    if stage:
        query = query.where(Lead.stage == stage)
    if interest:
        query = query.where(Lead.interest == interest)
    if since is not None:
        query = query.where(Lead.created_at >= since)
    return list(session.scalars(query.order_by(Lead.id.desc())))


def messages_for(session, institute_id, lead_id):
    return list(
        session.scalars(
            select(Message).where(Message.institute_id == institute_id, Message.lead_id == lead_id).order_by(Message.id)
        )
    )


def close_lead(session, lead) -> None:
    lead.stage = "closed"
```

In `leadagent/dashboard/routes.py`, add imports `import csv`, `import io`, `from datetime import timedelta`, `from fastapi.responses import Response`, `from leadagent.actions import delete_lead_and_history`, `from leadagent.store.models import utcnow`, add the constants and helpers below after `throttle = LoginThrottle()`, and **replace the placeholder `leads_page`** with these routes:

```python
STAGES = ("new", "collecting", "qualified", "handed_off", "closed")
INTERESTS = ("hot", "warm", "cold")
FORMULA_START = ("=", "+", "-", "@")


def _filters(stage, interest, days):
    since = utcnow() - timedelta(days=days) if days > 0 else None
    return (stage if stage in STAGES else None), (interest if interest in INTERESTS else None), since


def _cell(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_START) else text  # a spreadsheet must not run it as a formula


def _owned_lead(session, institute, lead_id):
    lead = repo.get_lead(session, institute.id, lead_id)
    if lead is None:
        raise HTTPException(404)
    return lead


@router.get("/{slug}/leads", response_class=HTMLResponse)
def leads_page(request: Request, slug: str, stage: str = "", interest: str = "", days: int = 0):
    with session_scope() as session:
        user = _user(session, request)
        institute = _institute(session, user, slug)
        leads = repo.leads_for(session, institute.id, *_filters(stage, interest, days))
        return _render(
            request,
            "leads.html",
            {
                "user": user, "institute": institute, "leads": leads, "local": _local(institute),
                "stage": stage, "interest": interest, "days": days, "stages": STAGES, "interests": INTERESTS,
            },
        )


@router.get("/{slug}/leads.csv")
def leads_csv(request: Request, slug: str, stage: str = "", interest: str = "", days: int = 0):
    with session_scope() as session:
        institute = _institute(session, _user(session, request), slug)
        local = _local(institute)
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["id", "created", "name", "class", "course", "phone", "stage", "interest", "last message"])
        for lead in repo.leads_for(session, institute.id, *_filters(stage, interest, days)):
            writer.writerow(
                [
                    lead.id, local(lead.created_at), _cell(lead.name), _cell(lead.student_class), _cell(lead.course),
                    _cell(lead.phone or lead.channel_user_id), lead.stage, lead.interest or "", local(lead.last_user_msg_at),
                ]
            )
        return Response(
            "﻿" + out.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{institute.slug}-leads.csv"'},
        )


@router.get("/{slug}/leads/{lead_id}", response_class=HTMLResponse)
def lead_page(request: Request, slug: str, lead_id: int):
    with session_scope() as session:
        user = _user(session, request)
        institute = _institute(session, user, slug)
        lead = _owned_lead(session, institute, lead_id)
        return _render(
            request,
            "lead.html",
            {
                "user": user, "institute": institute, "lead": lead, "local": _local(institute),
                "messages": repo.messages_for(session, institute.id, lead.id),
            },
        )


@router.post("/{slug}/leads/{lead_id}/{action}")
def lead_action(request: Request, slug: str, lead_id: int, action: str):
    if action not in ("resume", "close", "delete"):
        raise HTTPException(404)
    with session_scope() as session:
        institute = _institute(session, _user(session, request), slug)
        lead = _owned_lead(session, institute, lead_id)
        if action == "delete":
            delete_lead_and_history(session, lead)
            _flash(request, f"Lead {lead_id} and its messages are deleted.")
            return RedirectResponse(f"/dash/{institute.slug}/leads", status_code=303)
        if action == "resume":
            repo.resume(session, lead)
            _flash(request, "The assistant is switched back on for this lead.")
        else:
            repo.close_lead(session, lead)
            _flash(request, "Lead closed.")
        return RedirectResponse(f"/dash/{institute.slug}/leads/{lead_id}", status_code=303)
```

`leadagent/dashboard/templates/leads.html`:

```html
{% extends "base.html" %}
{% block title %}Leads · {{ institute.name }}{% endblock %}
{% block content %}
<h1>Leads</h1>
<form method="get">
  <select name="stage"><option value="">Any stage</option>{% for s in stages %}<option value="{{ s }}" {% if s == stage %}selected{% endif %}>{{ s }}</option>{% endfor %}</select>
  <select name="interest"><option value="">Any interest</option>{% for i in interests %}<option value="{{ i }}" {% if i == interest %}selected{% endif %}>{{ i }}</option>{% endfor %}</select>
  <select name="days"><option value="0">All time</option>{% for d in (1, 7, 30) %}<option value="{{ d }}" {% if d == days %}selected{% endif %}>Last {{ d }} day{% if d > 1 %}s{% endif %}</option>{% endfor %}</select>
  <button>Filter</button>
  <a href="/dash/{{ institute.slug }}/leads.csv?stage={{ stage }}&amp;interest={{ interest }}&amp;days={{ days }}">Download CSV</a>
</form>
<div class="scroll"><table>
<tr><th>#</th><th>Name</th><th>Class</th><th>Course</th><th>Contact</th><th>Stage</th><th>Interest</th><th>Created</th></tr>
{% for lead in leads %}
<tr>
  <td><a href="/dash/{{ institute.slug }}/leads/{{ lead.id }}">{{ lead.id }}</a></td>
  <td>{{ lead.name or "" }}</td><td>{{ lead.student_class or "" }}</td><td>{{ lead.course or "" }}</td>
  <td>{{ lead.phone or (lead.channel ~ " " ~ lead.channel_user_id) }}</td>
  <td>{{ lead.stage }}</td><td>{{ lead.interest or "" }}</td><td>{{ local(lead.created_at) }}</td>
</tr>
{% else %}
<tr><td colspan="8">No leads match.</td></tr>
{% endfor %}
</table></div>
{% endblock %}
```

`leadagent/dashboard/templates/lead.html`:

```html
{% extends "base.html" %}
{% block title %}Lead {{ lead.id }} · {{ institute.name }}{% endblock %}
{% block content %}
<p><a href="/dash/{{ institute.slug }}/leads">&larr; All leads</a></p>
<h1>Lead #{{ lead.id }}: {{ lead.name or "Name not given" }}</h1>
<div class="scroll"><table>
<tr><th>Class</th><td>{{ lead.student_class or "?" }}</td></tr>
<tr><th>Course</th><td>{{ lead.course or "?" }}</td></tr>
<tr><th>Contact</th><td>{{ lead.phone or (lead.channel ~ " " ~ lead.channel_user_id) }}</td></tr>
<tr><th>Stage</th><td>{{ lead.stage }}{% if lead.handoff_reason %} ({{ lead.handoff_reason }}){% endif %}</td></tr>
<tr><th>Interest</th><td>{{ lead.interest or "?" }}{% if lead.interest_reason %} ({{ lead.interest_reason }}){% endif %}</td></tr>
<tr><th>Notes</th><td>{{ lead.notes or "" }}</td></tr>
<tr><th>First message</th><td>{{ local(lead.created_at) }}</td></tr>
<tr><th>Last message</th><td>{{ local(lead.last_user_msg_at) }}</td></tr>
</table></div>
<p>
  <form class="inline" method="post" action="/dash/{{ institute.slug }}/leads/{{ lead.id }}/resume"><button {% if lead.stage != "handed_off" %}disabled{% endif %}>Switch the assistant back on</button></form>
  <form class="inline" method="post" action="/dash/{{ institute.slug }}/leads/{{ lead.id }}/close"><button {% if lead.stage == "closed" %}disabled{% endif %}>Close</button></form>
  <form class="inline" method="post" action="/dash/{{ institute.slug }}/leads/{{ lead.id }}/delete" onsubmit="return confirm('Delete this lead and all its messages?')"><button>Delete</button></form>
</p>
<h2>Conversation</h2>
{% for m in messages %}
<div class="msg {{ m.role }}"><small>{{ m.role }} · {{ local(m.created_at) }}</small><br>{{ m.text }}</div>
{% else %}
<p>No messages.</p>
{% endfor %}
{% endblock %}
```

- [ ] **Step 4: Run the tests**

Run: `.\.venv\Scripts\python -m pytest -q`
Expected: all pass, 1 skipped (including the M1 tests for `/delete` and `set-owner`, which now go through `delete_lead_and_history`).

- [ ] **Step 5: Commit**

```powershell
git add leadagent tests
git commit -m "Dashboard leads: list, filters, CSV export, transcript and actions"
```

---

### Task 7: Documents page

**Files:**
- Create: `leadagent/dashboard/templates/documents.html`, `tests/test_dashboard_documents.py`
- Modify: `leadagent/dashboard/routes.py`

**Interfaces:**
- Consumes: `ingest`, `IngestError`, `MAX_BYTES` from `leadagent.rag.ingest`; `repo.documents_for`, `repo.get_document`, `repo.delete_document`
- Produces: `safe_filename(name) -> str | None`; routes `GET /dash/{slug}/documents`, `POST /dash/{slug}/documents` (form field `file`), `POST /dash/{slug}/documents/{document_id}/delete`

- [ ] **Step 1: Write the failing tests**

`tests/test_dashboard_documents.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from helpers import make_institute, make_user
from leadagent.app import app
from leadagent.dashboard.routes import safe_filename
from leadagent.store.models import Chunk, Document


@pytest.fixture
def client(session):
    make_user(session, institute=make_institute(session, "bright"))
    make_institute(session, "other")
    test_client = TestClient(app)
    test_client.post("/dash/login", data={"email": "owner@bright.test", "password": "correct horse 1"})
    return test_client


def upload(client, name, data, slug="bright"):
    return client.post(f"/dash/{slug}/documents", files={"file": (name, data, "text/plain")}, follow_redirects=True)


def test_uploading_a_text_file_adds_a_ready_document(client, session):
    page = upload(client, "faq.txt", b"Refunds within 7 days.")
    assert "Added faq.txt" in page.text and "ready" in page.text
    document = session.scalars(select(Document)).one()
    assert document.filename == "faq.txt" and document.status == "ready"


@pytest.mark.parametrize("name, stored", [("../../evil.txt", "evil.txt"), ("..\\..\\evil.txt", "evil.txt"), ("dir/faq.md", "faq.md")])
def test_a_path_in_the_filename_is_stripped(name, stored):
    assert safe_filename(name) == stored


@pytest.mark.parametrize("name", ["", ".", "..", "   "])
def test_an_empty_or_dot_filename_is_refused(name):
    assert safe_filename(name) is None


def test_a_refused_upload_stores_nothing(client, session):
    page = upload(client, "photo.jpg", b"x")
    assert "only PDF" in page.text
    assert session.scalars(select(Document)).all() == []


def test_an_upload_over_the_limit_is_refused(client, session, monkeypatch):
    monkeypatch.setattr("leadagent.dashboard.routes.MAX_BYTES", 10)
    page = upload(client, "big.txt", b"x" * 11)
    assert "larger than 10 MB" in page.text
    assert session.scalars(select(Document)).all() == []


def test_deleting_a_document_removes_its_passages(client, session):
    upload(client, "faq.txt", b"Refunds within 7 days.")
    document = session.scalars(select(Document)).one()
    client.post(f"/dash/bright/documents/{document.id}/delete")
    session.expire_all()
    assert session.scalars(select(Document)).all() == [] and session.scalars(select(Chunk)).all() == []


def test_another_institutes_documents_are_out_of_reach(client, session):
    from helpers import add_document_with_chunks
    from leadagent.store import repo

    theirs = repo.institute_by_slug(session, "other")
    document = add_document_with_chunks(session, theirs, "secret.txt", ["their passage"])
    assert client.get("/dash/other/documents").status_code == 404
    assert upload(client, "faq.txt", b"x", slug="other").status_code == 404
    assert client.post(f"/dash/bright/documents/{document.id}/delete").status_code == 404
    assert "secret.txt" not in client.get("/dash/bright/documents").text
```

- [ ] **Step 2: Run them to see them fail**

Run: `.\.venv\Scripts\python -m pytest tests/test_dashboard_documents.py -q`
Expected: `ImportError: cannot import name 'safe_filename'`.

- [ ] **Step 3: Write the implementation**

In `leadagent/dashboard/routes.py`, add imports `import tempfile`, `from pathlib import PurePosixPath`, `from fastapi import File, UploadFile`, `from leadagent.rag.ingest import MAX_BYTES, IngestError, ingest`, then add:

```python
def safe_filename(name):
    """The bare file name of an upload, or None. Never a path, so nothing is written outside the temp folder."""
    bare = PurePosixPath((name or "").replace("\\", "/")).name.strip()[:255]
    return None if bare in ("", ".", "..") else bare


@router.get("/{slug}/documents", response_class=HTMLResponse)
def documents_page(request: Request, slug: str):
    with session_scope() as session:
        user = _user(session, request)
        institute = _institute(session, user, slug)
        return _render(
            request,
            "documents.html",
            {"user": user, "institute": institute, "local": _local(institute),
             "documents": repo.documents_for(session, institute.id)},
        )


@router.post("/{slug}/documents")
def upload_document(request: Request, slug: str, file: UploadFile = File(...)):
    with session_scope() as session:
        institute = _institute(session, _user(session, request), slug)
        name = safe_filename(file.filename)
        data = file.file.read(MAX_BYTES + 1)
        if name is None:
            _flash(request, "Choose a file to upload.")
        elif len(data) > MAX_BYTES:
            _flash(request, f"{name} is larger than 10 MB")
        else:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / name
                path.write_bytes(data)
                try:
                    document = ingest(session, institute.id, path)
                    reason = f" ({document.error})" if document.error else ""
                    _flash(request, f"Added {document.filename}: {document.status}{reason}")
                except IngestError as exc:
                    _flash(request, str(exc))
                except Exception:
                    log.exception("upload failed for institute %s", institute.slug)
                    _flash(request, f"Could not add {name}. Please try again.")
        return RedirectResponse(f"/dash/{institute.slug}/documents", status_code=303)


@router.post("/{slug}/documents/{document_id}/delete")
def delete_document(request: Request, slug: str, document_id: int):
    with session_scope() as session:
        institute = _institute(session, _user(session, request), slug)
        document = repo.get_document(session, institute.id, document_id)
        if document is None:
            raise HTTPException(404)
        repo.delete_document(session, document)
        _flash(request, f"{document.filename} and its passages are deleted.")
        return RedirectResponse(f"/dash/{institute.slug}/documents", status_code=303)
```

`leadagent/dashboard/templates/documents.html`:

```html
{% extends "base.html" %}
{% block title %}Documents · {{ institute.name }}{% endblock %}
{% block content %}
<h1>Documents</h1>
<p>The assistant searches these when the facts do not answer a question. PDF, .txt or .md, up to 10 MB.
Adding a file with the same name replaces the old version. Scanned PDFs cannot be read yet.</p>
<form method="post" action="/dash/{{ institute.slug }}/documents" enctype="multipart/form-data">
  <input type="file" name="file" accept=".pdf,.txt,.md" required> <button>Upload</button>
</form>
<div class="scroll"><table>
<tr><th>#</th><th>File</th><th>Status</th><th>Added</th><th></th></tr>
{% for d in documents %}
<tr>
  <td>{{ d.id }}</td><td>{{ d.filename }}</td>
  <td>{{ d.status }}{% if d.error %} ({{ d.error }}){% endif %}</td><td>{{ local(d.uploaded_at) }}</td>
  <td><form class="inline" method="post" action="/dash/{{ institute.slug }}/documents/{{ d.id }}/delete" onsubmit="return confirm('Delete this document?')"><button>Delete</button></form></td>
</tr>
{% else %}
<tr><td colspan="5">No documents yet.</td></tr>
{% endfor %}
</table></div>
{% endblock %}
```

- [ ] **Step 4: Run the tests and commit**

Run: `.\.venv\Scripts\python -m pytest -q`
Expected: all pass, 1 skipped.

```powershell
git add leadagent/dashboard tests/test_dashboard_documents.py
git commit -m "Dashboard documents: upload, list and delete"
```

---

### Task 8: Facts editor and stats

**Files:**
- Create: `leadagent/dashboard/templates/facts.html`, `leadagent/dashboard/templates/stats.html`, `tests/test_dashboard_facts_stats.py`
- Modify: `leadagent/dashboard/routes.py`, `leadagent/store/repo.py`, `tests/test_store.py`

**Interfaces:**
- Consumes: `parse_facts`, `FactsError`
- Produces: `repo.lead_stats(session, institute_id, timezone_name, now, days=14) -> dict` with keys `per_day` (list of `(date, count)`, oldest first, exactly `days` entries), `total`, `hot`, `hot_share` (whole percent), `waiting`; routes `GET`/`POST /dash/{slug}/facts` (form field `facts_yaml`), `GET /dash/{slug}/stats`

- [ ] **Step 1: Write the failing tests**

`tests/test_dashboard_facts_stats.py`:

```python
import copy

import pytest
import yaml
from fastapi.testclient import TestClient

from helpers import FACTS, make_institute, make_lead, make_user
from leadagent.app import app
from leadagent.store.models import utcnow


@pytest.fixture
def client(session):
    make_user(session, institute=make_institute(session, "bright"))
    make_institute(session, "other")
    test_client = TestClient(app)
    test_client.post("/dash/login", data={"email": "owner@bright.test", "password": "correct horse 1"})
    return test_client


def test_the_facts_page_shows_the_current_facts(client):
    assert "₹68,000 per year" in client.get("/dash/bright/facts").text


def test_valid_facts_are_saved(client, session):
    changed = copy.deepcopy(FACTS)
    changed["courses"][0]["fee"] = "₹70,000 per year"
    page = client.post("/dash/bright/facts", data={"facts_yaml": yaml.safe_dump(changed, allow_unicode=True)})
    assert "Facts saved" in page.text
    from leadagent.store import repo

    session.expire_all()
    assert repo.institute_by_slug(session, "bright").facts["courses"][0]["fee"] == "₹70,000 per year"


@pytest.mark.parametrize("text, message", [("courses: [unclosed", "not valid YAML"), ("institute_name: X", "Invalid institute facts")])
def test_invalid_facts_are_refused_and_the_text_is_kept(client, session, text, message):
    page = client.post("/dash/bright/facts", data={"facts_yaml": text})
    assert page.status_code == 400
    assert message in page.text and text.split(":")[0] in page.text
    from leadagent.store import repo

    session.expire_all()
    assert repo.institute_by_slug(session, "bright").facts == FACTS


def test_stats_show_counts(client, session):
    from leadagent.store import repo

    bright = repo.institute_by_slug(session, "bright")
    make_lead(session, bright, "1", interest="hot", created_at=utcnow())
    make_lead(session, bright, "2", stage="handed_off", created_at=utcnow())
    page = client.get("/dash/bright/stats").text
    assert "2 leads" in page and "50% hot" in page and "1 waiting" in page


@pytest.mark.parametrize("method, path", [("get", "/dash/other/facts"), ("post", "/dash/other/facts"), ("get", "/dash/other/stats")])
def test_another_institutes_facts_and_stats_are_out_of_reach(client, method, path):
    response = getattr(client, method)(path, data={"facts_yaml": "x"} if method == "post" else None)
    assert response.status_code == 404
```

Append to `tests/test_store.py`:

```python
def test_lead_stats_count_per_local_day(session):
    institute = make_institute(session)
    make_lead(session, institute, "1", interest="hot", created_at=NOON_IST)
    make_lead(session, institute, "2", created_at=NOON_IST - timedelta(days=1))
    make_lead(session, institute, "3", stage="handed_off", created_at=NOON_IST - timedelta(days=30))
    stats = repo.lead_stats(session, institute.id, "Asia/Kolkata", NOON_IST, days=14)
    assert len(stats["per_day"]) == 14
    assert [count for _, count in stats["per_day"]][-2:] == [1, 1]
    assert (stats["total"], stats["hot"], stats["hot_share"], stats["waiting"]) == (2, 1, 50, 1)
```

- [ ] **Step 2: Run them to see them fail**

Run: `.\.venv\Scripts\python -m pytest tests/test_dashboard_facts_stats.py tests/test_store.py -q`
Expected: failures (404 for the facts and stats pages, `repo.lead_stats` missing).

- [ ] **Step 3: Write the implementation**

Append to `leadagent/store/repo.py` (add `from datetime import datetime, time` to the imports):

```python
def lead_stats(session, institute_id, timezone_name, now, days=14):
    """Leads created per local day for the last `days` days, the share rated hot, and how many wait for the team."""
    zone = ZoneInfo(timezone_name)
    today = now.astimezone(zone).date()
    first_day = today - timedelta(days=days - 1)
    since = datetime.combine(first_day, time.min, tzinfo=zone)
    leads = session.scalars(select(Lead).where(Lead.institute_id == institute_id, Lead.created_at >= since)).all()
    per_day = {first_day + timedelta(days=i): 0 for i in range(days)}
    for lead in leads:
        day = lead.created_at.astimezone(zone).date()
        if day in per_day:  # a clock a little ahead must not crash the page
            per_day[day] += 1
    hot = sum(1 for lead in leads if lead.interest == "hot")
    waiting = session.scalar(
        select(func.count()).select_from(Lead).where(Lead.institute_id == institute_id, Lead.stage == "handed_off")
    )
    return {
        "per_day": list(per_day.items()),
        "total": len(leads),
        "hot": hot,
        "hot_share": round(100 * hot / len(leads)) if leads else 0,
        "waiting": waiting,
    }
```

In `leadagent/dashboard/routes.py`, add `import yaml` and `from leadagent.facts import FactsError, parse_facts`, then:

```python
def _facts_text(institute) -> str:
    return yaml.safe_dump(institute.facts, allow_unicode=True, sort_keys=False)


@router.get("/{slug}/facts", response_class=HTMLResponse)
def facts_page(request: Request, slug: str):
    with session_scope() as session:
        user = _user(session, request)
        institute = _institute(session, user, slug)
        return _render(request, "facts.html", {"user": user, "institute": institute, "text": _facts_text(institute), "error": None})


@router.post("/{slug}/facts", response_class=HTMLResponse)
def save_facts(request: Request, slug: str, facts_yaml: str = Form(...)):
    with session_scope() as session:
        user = _user(session, request)
        institute = _institute(session, user, slug)
        try:
            facts = parse_facts(yaml.safe_load(facts_yaml))
        except yaml.YAMLError as exc:
            error = f"This is not valid YAML: {exc}"
        except FactsError as exc:
            error = str(exc)
        else:
            institute.facts = facts.model_dump()
            _flash(request, "Facts saved. The assistant uses them from the next message.")
            return RedirectResponse(f"/dash/{institute.slug}/facts", status_code=303)
        return _render(
            request, "facts.html", {"user": user, "institute": institute, "text": facts_yaml, "error": error}, status_code=400
        )


@router.get("/{slug}/stats", response_class=HTMLResponse)
def stats_page(request: Request, slug: str):
    with session_scope() as session:
        user = _user(session, request)
        institute = _institute(session, user, slug)
        stats = repo.lead_stats(session, institute.id, institute.timezone, utcnow())
        return _render(request, "stats.html", {"user": user, "institute": institute, "stats": stats})
```

`leadagent/dashboard/templates/facts.html`:

```html
{% extends "base.html" %}
{% block title %}Facts · {{ institute.name }}{% endblock %}
{% block content %}
<h1>Facts</h1>
<p>Fees, batches, timings and FAQ, which the assistant quotes exactly. Every course needs a name, classes, a fee and at
least one batch. Keep the layout (YAML): two spaces per level, a dash before each list item.</p>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post" action="/dash/{{ institute.slug }}/facts">
  <textarea name="facts_yaml" spellcheck="false">{{ text }}</textarea>
  <p><button>Save</button></p>
</form>
{% endblock %}
```

`leadagent/dashboard/templates/stats.html`:

```html
{% extends "base.html" %}
{% block title %}Stats · {{ institute.name }}{% endblock %}
{% block content %}
<h1>Last 14 days</h1>
<p><strong>{{ stats.total }} leads</strong> · {{ stats.hot_share }}% hot · {{ stats.waiting }} waiting for the team now</p>
<div class="scroll"><table>
<tr><th>Day</th><th>New leads</th></tr>
{% for day, count in stats.per_day %}
<tr><td>{{ day.strftime("%a %d %b") }}</td><td><span class="bar" style="width: {{ [count * 16, 400]|min }}px"></span> {{ count }}</td></tr>
{% endfor %}
</table></div>
{% endblock %}
```

- [ ] **Step 4: Run the tests and commit**

Run: `.\.venv\Scripts\python -m pytest -q`
Expected: all pass, 1 skipped.

```powershell
git add leadagent tests
git commit -m "Dashboard facts editor and stats"
```

---

### Task 9: Admin: institutes

**Files:**
- Create: `leadagent/dashboard/templates/institutes.html`, `tests/test_dashboard_admin.py`
- Modify: `leadagent/dashboard/routes.py`, `leadagent/store/repo.py`

**Interfaces:**
- Consumes: `cli.add_institute`, `parse_facts`, `FactsError`
- Produces: `repo.all_institutes(session) -> list[Institute]`; routes `GET /dash/admin/institutes`, `POST /dash/admin/institutes` (fields `slug`, `name`, `timezone`, `telegram_token`, `facts_yaml`), `POST /dash/admin/institutes/{slug}/active`

- [ ] **Step 1: Write the failing tests**

`tests/test_dashboard_admin.py`:

```python
import pytest
import yaml
from fastapi.testclient import TestClient

from helpers import FACTS, make_institute, make_user
from leadagent.app import app
from leadagent.crypto import decrypt
from leadagent.store import repo


@pytest.fixture
def client(session):
    make_user(session, email="admin@lead.test", role="admin")
    test_client = TestClient(app)
    test_client.post("/dash/login", data={"email": "admin@lead.test", "password": "correct horse 1"})
    return test_client


def new_institute(slug="vidya", facts=None, token="123:ABC"):
    return {
        "slug": slug, "name": "Vidya", "timezone": "Asia/Kolkata", "telegram_token": token,
        "facts_yaml": facts if facts is not None else yaml.safe_dump(FACTS, allow_unicode=True),
    }


def test_the_admin_sees_every_institute(client, session):
    make_institute(session, "bright")
    make_institute(session, "other", active=False)
    page = client.get("/dash/admin/institutes").text
    assert "bright" in page and "other" in page


def test_the_admin_adds_an_institute(client, session):
    page = client.post("/dash/admin/institutes", data=new_institute())
    assert "Added vidya" in page.text
    institute = repo.institute_by_slug(session, "vidya")
    assert decrypt(institute.telegram_bot_token_enc) == "123:ABC"
    assert institute.facts == FACTS


@pytest.mark.parametrize(
    "form, message",
    [
        (new_institute(slug="admin"), "reserved"),
        (new_institute(slug="Bad Slug"), "slug must be"),
        (new_institute(facts="institute_name: X"), "Invalid institute facts"),
        (new_institute(facts="courses: [unclosed"), "not valid YAML"),
    ],
)
def test_bad_institutes_are_refused(client, session, form, message):
    page = client.post("/dash/admin/institutes", data=form)
    assert page.status_code == 400 and message in page.text
    assert repo.institute_by_slug(session, form["slug"]) is None


def test_the_admin_can_switch_an_institute_off_and_on(client, session):
    make_institute(session, "bright")
    client.post("/dash/admin/institutes/bright/active")
    session.expire_all()
    assert repo.institute_by_slug(session, "bright").active is False
    client.post("/dash/admin/institutes/bright/active")
    session.expire_all()
    assert repo.institute_by_slug(session, "bright").active is True


def test_the_token_is_never_shown_again(client, session):
    client.post("/dash/admin/institutes", data=new_institute(token="999:SECRET"))
    assert "999:SECRET" not in client.get("/dash/admin/institutes").text


def test_owners_cannot_use_the_admin_actions(session):
    make_user(session, institute=make_institute(session, "bright"))
    owner = TestClient(app)
    owner.post("/dash/login", data={"email": "owner@bright.test", "password": "correct horse 1"})
    assert owner.post("/dash/admin/institutes", data=new_institute()).status_code == 404
    assert owner.post("/dash/admin/institutes/bright/active").status_code == 404
    assert repo.institute_by_slug(session, "bright").active is True
```

- [ ] **Step 2: Run them to see them fail**

Run: `.\.venv\Scripts\python -m pytest tests/test_dashboard_admin.py -q`
Expected: failures (the placeholder page lists nothing; the POST routes do not exist).

- [ ] **Step 3: Write the implementation**

Append to `leadagent/store/repo.py`:

```python
def all_institutes(session):
    return list(session.scalars(select(Institute).order_by(Institute.id)))
```

In `leadagent/dashboard/routes.py`, add `from leadagent.cli import add_institute`, define `EXAMPLE_FACTS = (Path(__file__).resolve().parents[2] / "examples" / "brightpath.yaml").read_text(encoding="utf-8")` below the templates line, and **replace the placeholder `institutes_page`** with:

```python
def _institutes_context(session, user, error=None, form=None):
    return {
        "user": user, "institute": None, "institutes": repo.all_institutes(session), "error": error,
        "form": form or {"slug": "", "name": "", "timezone": "Asia/Kolkata", "facts_yaml": EXAMPLE_FACTS},
    }


@router.get("/admin/institutes", response_class=HTMLResponse)
def institutes_page(request: Request):
    with session_scope() as session:
        user = _admin(session, request)
        return _render(request, "institutes.html", _institutes_context(session, user))


@router.post("/admin/institutes", response_class=HTMLResponse)
def create_institute(
    request: Request,
    slug: str = Form(...),
    name: str = Form(...),
    telegram_token: str = Form(...),
    facts_yaml: str = Form(...),
    timezone: str = Form("Asia/Kolkata"),
):
    with session_scope() as session:
        user = _admin(session, request)
        try:
            facts = parse_facts(yaml.safe_load(facts_yaml))
            add_institute(session, slug=slug.strip(), name=name.strip(), facts=facts,
                          telegram_token=telegram_token.strip(), timezone=timezone.strip())
        except yaml.YAMLError as exc:
            error = f"Facts: this is not valid YAML: {exc}"
        except (FactsError, ValueError) as exc:  # FactsError is a ValueError too; both messages are safe to show
            error = str(exc)
        else:
            _flash(request, f"Added {slug.strip()}. Next: set-webhook, then the owner sends /whoami and you run set-owner.")
            return RedirectResponse("/dash/admin/institutes", status_code=303)
        session.rollback()
        form = {"slug": slug, "name": name, "timezone": timezone, "facts_yaml": facts_yaml}  # never echo the token
        return _render(request, "institutes.html", _institutes_context(session, user, error, form), status_code=400)


@router.post("/admin/institutes/{slug}/active")
def toggle_institute(request: Request, slug: str):
    with session_scope() as session:
        _admin(session, request)
        institute = repo.institute_by_slug(session, slug)
        if institute is None:
            raise HTTPException(404)
        institute.active = not institute.active
        _flash(request, f"{institute.slug} is now {'on' if institute.active else 'off'}.")
        return RedirectResponse("/dash/admin/institutes", status_code=303)
```

`leadagent/dashboard/templates/institutes.html`:

```html
{% extends "base.html" %}
{% block title %}Institutes{% endblock %}
{% block content %}
<h1>Institutes</h1>
<div class="scroll"><table>
<tr><th>#</th><th>Slug</th><th>Name</th><th>Status</th><th>Owner chat</th><th>WhatsApp</th><th></th></tr>
{% for i in institutes %}
<tr>
  <td>{{ i.id }}</td><td><a href="/dash/{{ i.slug }}/leads">{{ i.slug }}</a></td><td>{{ i.name }}</td>
  <td>{{ "on" if i.active else "off" }}</td><td>{{ "set" if i.owner_telegram_chat_id else "not set" }}</td>
  <td>{{ "attached" if i.whatsapp_phone_number_id else "-" }}</td>
  <td><form class="inline" method="post" action="/dash/admin/institutes/{{ i.slug }}/active"><button>{{ "Switch off" if i.active else "Switch on" }}</button></form></td>
</tr>
{% endfor %}
</table></div>
<h2>Add an institute</h2>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post" action="/dash/admin/institutes">
  <p><label>Slug (lower-case letters, digits, hyphens)<br><input name="slug" value="{{ form.slug }}" required></label></p>
  <p><label>Name<br><input name="name" value="{{ form.name }}" required></label></p>
  <p><label>Timezone<br><input name="timezone" value="{{ form.timezone }}"></label></p>
  <p><label>Telegram bot token<br><input type="password" name="telegram_token" required autocomplete="off"></label></p>
  <p><label>Facts<br><textarea name="facts_yaml" spellcheck="false">{{ form.facts_yaml }}</textarea></label></p>
  <p><button>Add institute</button></p>
</form>
{% endblock %}
```

- [ ] **Step 4: Run the tests and commit**

Run: `.\.venv\Scripts\python -m pytest -q`
Expected: all pass, 1 skipped.

```powershell
git add leadagent tests/test_dashboard_admin.py
git commit -m "Dashboard admin: list, add and switch institutes on and off"
```

---

### Task 10: Documentation, spec and first accounts

**Files:**
- Modify: `README.md`, `docs/DEMO_CHECKLIST.md`, `docs/specs/2026-10-13-lead-agent-design.md`

- [ ] **Step 1: README**

Change the status line to say M3 (dashboard) is built. Add after the "Documents (RAG)" section:

```markdown
## Dashboard

Owners and the admin log in at `<PUBLIC_BASE_URL>/dash` (locally, `http://127.0.0.1:8000/dash` works only with
`SESSION_HTTPS_ONLY=false` in `.env`, because the login cookie is HTTPS-only by default).

    .\.venv\Scripts\python -m leadagent.cli add-user --email you@example.com --role admin
    .\.venv\Scripts\python -m leadagent.cli add-user --email owner@example.com --role owner --slug brightpath
    .\.venv\Scripts\python -m leadagent.cli set-password --email owner@example.com

An owner sees only their institute: leads with filters and CSV export, each lead's conversation with
resume / close / delete, documents, the facts editor and stats. The admin also manages institutes.
`SESSION_SECRET` in `.env` signs the login cookie; without it, everyone is logged out on every restart.
```

and add `| leadagent/dashboard/ | Web dashboard: routes and templates |` to the Layout table.

- [ ] **Step 2: Demo checklist**

Add a "Dashboard" section to `docs/DEMO_CHECKLIST.md`:

```markdown
## Dashboard

1. Generate a secret once and put it in `.env` as `SESSION_SECRET`:
   `.\.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(32))"`. Restart the app.
2. Create your admin account and an owner account with `add-user` (see the README).
3. Open `<PUBLIC_BASE_URL>/dash` on a phone.

- [ ] The owner logs in and sees only their institute's leads.
- [ ] A lead's page shows the whole conversation; "Switch the assistant back on" works on a handed-off lead.
- [ ] Uploading the prospectus on the Documents page shows "ready".
- [ ] Changing a fee on the Facts page changes the assistant's answer to the next fee question.
- [ ] Five wrong passwords lock that email out for 15 minutes.
```

- [ ] **Step 3: Spec**

In `docs/specs/2026-10-13-lead-agent-design.md`:

1. Section 8: below the page table, add: "Built in M3 (16 Oct 2026) as server-rendered pages under `/dash`; institute pages are `/dash/<slug>/…` and answer 404 to anyone but that institute's owner and the admin. Facts are edited as YAML text, validated on save."
2. Section 11, Dashboard bullet: add "Failed logins: 5 per email per 15 minutes, kept in memory (one process). CSV exports neutralise spreadsheet formulas."
3. Section 15: add rows:

```markdown
| Dashboard | Login throttle and sessions are in memory / in the cookie only; a restart clears the throttle | More than one process | Move the throttle to the database |
| Dashboard | Facts are edited as YAML text rather than a form with fields | Owners find YAML hard | A field-per-item form generated from the Facts model |
| Dashboard | No password reset by email; the admin runs set-password | More than a handful of owners | Email reset links |
```

- [ ] **Step 4: Run every test and commit**

Run: `.\.venv\Scripts\python -m pytest -q`
Expected: all pass, 1 skipped.

```powershell
git add README.md docs
git commit -m "Document the dashboard in the README, checklist and spec"
```

- [ ] **Step 5 (done by Yash, by hand): first accounts**

The controller adds a generated `SESSION_SECRET` line to `.env` (it is not something Yash needs to remember) and restarts the app. Yash then creates his admin account and the BrightPath owner account with `add-user`, typing the passwords himself, and works through the Dashboard section of the demo checklist on his phone.

---

## What this plan leaves out

Replying to a lead from the dashboard, password reset by email, two-factor login, owner self-signup and billing, charts beyond the simple bars, and a React frontend (all in spec Section 15).

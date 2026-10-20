# VidyaDesk Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle every `/dash` page in the warm "VidyaDesk" look, add a Home screen, and add the first-visit intro animation, without changing what any page does.

**Architecture:** Still server-rendered Jinja2 in the existing FastAPI app. One stylesheet (`templates/vidyadesk.css`) and one script (`templates/intro.js`) are pulled into `base.html` / `home.html` with `{% include %}`, so no static-file route or build step is added. Shared markup (initials circle, badges, lead row) lives in Jinja macros in `templates/_ui.html`. The new Home data comes from one new repo function.

**Tech Stack:** FastAPI, Jinja2 (autoescape on for `.html`), plain CSS, a little vanilla JavaScript for the intro only, pytest.

**Spec:** `docs/specs/2026-10-20-dashboard-redesign-design.md` (approved 20 Oct 2026). The approved mockups are in `docs/specs/2026-10-20-dashboard-redesign/`: `visual-style-options.html` (use option **C** only) and `intro-animation.html` (copy its timings and effects exactly).

## Global Constraints

- Product name **VidyaDesk** on the login page, every browser tab title (`… · VidyaDesk`), the sidebar, and the admin's intro. Package, CLI and repo names do not change.
- Colour tokens exactly as the spec's table: background `#fbf8f3`, ink `#2b2118`, muted `#8a7766`, faint `#a8937d`, accent `#c2410c`, accent-soft `#ffe8cc`, card `#ffffff`, border `#efe6da`, card shadow `0 1px 3px rgba(60,40,20,.08)`. Badges: Hot `#ffe4e1`/`#c0262d`, Waiting `#fff1c2`/`#8a5a00`, New `#dff3ec`/`#0f766e`.
- Phone: bottom tab bar (Home, Leads, Docs, Facts, Stats). Laptop: left sidebar with the same items. Admin also gets Institutes.
- Works at 360 px wide with no sideways page scroll; wide tables scroll inside `.scroll`.
- Autoescape stays on; never `|safe` on user-written text. All actions stay POST forms that work without JavaScript.
- `prefers-reduced-motion`: no animation at all.
- No new Python dependency, no web font (system font stack), no hardcoded absolute paths.
- Every existing test keeps passing; the only intended test change is the owner's landing URL (`/dash/<slug>/leads` → `/dash/<slug>/home`).
- Shell commands are PowerShell from `PROJECT LEAD AGENT/`: `.\.venv\Scripts\python -m pytest -q` (expected: all pass, 1 skipped).

## Review Focus

1. **A lead whose name is in Odia or Devanagari, or very long** (e.g. 60 characters): the initials circle shows the first letter(s), the row does not push the page wider than 360 px. (Task 1 test for initials; Task 2 check for the row.)
2. **HTML in a student-written name on the new Home screen** (`<script>`): shown as text. (Task 2 test.)
3. **A lead with no name, class or course yet** (most new leads): Home and Leads rows show "Name not given" and never the word "None". (Task 2 test.)
4. **An institute with no leads at all** (a brand-new client in the pitch): Home shows its two empty-state lines and zeros, no error. (Task 2 test.)
5. **The intro when the browser blocks storage** (private mode, some in-app browsers): the page stays usable and the overlay never stays stuck on screen; every storage call is wrapped in `try/catch`. (Task 5 code requirement and manual check.)

---

### Task 1: Design system, layout and login

**Files:**
- Create: `leadagent/dashboard/templates/vidyadesk.css`, `leadagent/dashboard/templates/_ui.html`, `tests/test_dashboard_look.py`
- Modify: `leadagent/dashboard/templates/base.html`, `leadagent/dashboard/templates/login.html`, `leadagent/dashboard/routes.py` (register the filter)

**Interfaces:**
- Produces: Jinja filter `initials(name) -> str` (registered as `templates.env.filters["initials"]`, function `initials` in `routes.py`); macros in `_ui.html`: `avatar(name)`, `badge(lead)` (Waiting for `handed_off`, else Hot/Warm/Cold from `interest`, else New for stages new/collecting, Qualified, Closed), `lead_row(lead, slug, detail)` (a link card: avatar, bold name or "Name not given", a muted `detail` line, badge). CSS classes later tasks use: `.card`, `.row`, `.stats` / `.stat`, `.sec` (section label), `.pill` + `.hot/.wait/.new/.warm/.cold/.qualified/.closed`, `.btn`, `.btn-danger`, `.btn-quiet`, `.flash`, `.error`, `.empty`, `.scroll`, `.bubble.user/.assistant/.owner`.
- `base.html` blocks unchanged: `title`, `content`. It works out the active tab from `request.url.path` (`/home`, `/leads`, `/documents`, `/facts`, `/stats`, `/admin/institutes`), so no route needs a new context key.

- [ ] **Step 1: Write the failing tests** in `tests/test_dashboard_look.py`:

```python
@pytest.mark.parametrize("name, expected", [
    ("Rahul Sharma", "RS"), ("priya", "P"), ("Aman Kumar Singh", "AS"),
    (None, "?"), ("   ", "?"), ("ପ୍ରିୟା ମହାନ୍ତି", "ପମ"),
])
def test_initials(name, expected):
    assert initials(name) == expected

def test_login_page_is_branded(client):
    page = client.get("/dash/login").text
    assert "VidyaDesk" in page and "<title>" in page and 'name="viewport"' in page

def test_owner_navigation_has_every_tab_and_no_admin_tab(client, session):
    # owner logged in; GET /dash/bright/leads
    for href in ("/dash/bright/home", "/dash/bright/leads", "/dash/bright/documents", "/dash/bright/facts", "/dash/bright/stats"):
        assert f'href="{href}"' in page
    assert "/dash/admin/institutes" not in page

def test_admin_navigation_has_institutes(client, session):
    # admin logged in; GET /dash/admin/institutes
    assert 'href="/dash/admin/institutes"' in page
```

(`initials` takes the first character of the first and last words; non-Latin characters are kept as they are; an Odia combining mark is not a "letter" — take the first character of each word, which for "ପ୍ରିୟା" is "ପ".)

- [ ] **Step 2: Run** `.\.venv\Scripts\python -m pytest tests/test_dashboard_look.py -q`. Expected: FAIL (`initials` missing; no "VidyaDesk").

- [ ] **Step 3: Implement.**
  - `initials(name) -> str` in `routes.py`: split on whitespace; "" → "?"; one word → its first character upper-cased; else first char of first and last word, upper-cased. Register on `templates.env.filters`.
  - `vidyadesk.css`: option C from the mockup (tokens as CSS variables on `:root`), system font stack, cards, rows, pills, buttons, banners, tables, chat bubbles, `.bar` in saffron. Layout: below 900 px a fixed bottom tab bar and a top bar with the institute name + initials avatar + log out; from 900 px a 240 px left sidebar (VidyaDesk mark, institute name, tabs, log out at the bottom). Main content padded so the bottom bar never covers it. Focus outlines visible (accent). In `.row` the text column has `min-width: 0` and its lines `overflow: hidden; text-overflow: ellipsis; white-space: nowrap`, so a 60-character or Odia name never widens the page (Review Focus 1).
  - `base.html`: `<title>{% block title %}{% endblock %} · VidyaDesk</title>`, `<style>{% include "vidyadesk.css" %}</style>`, inline SVG icons for the tabs, flash as `.flash`. Keep the logout POST form.
  - `login.html`: centred card with the book mark (the SVG from the intro mockup), "VidyaDesk", the existing form fields and error text unchanged.
  - `_ui.html`: the three macros above.

- [ ] **Step 4: Run** the new tests, then the full suite. Expected: all pass, 1 skipped (the old pages still render through the new `base.html`).

- [ ] **Step 5: Commit** `git commit -m "VidyaDesk look: stylesheet, layout, navigation and login"`.

---

### Task 2: Home screen

**Files:**
- Create: `leadagent/dashboard/templates/home.html`, `tests/test_dashboard_home.py`
- Modify: `leadagent/store/repo.py`, `leadagent/dashboard/routes.py`, `tests/test_dashboard_auth.py` (lines 33–34: landing URL), `tests/test_store.py`

**Interfaces:**
- Consumes: `_ui.html` macros, `initials` (Task 1).
- Produces: `repo.home_summary(session, institute_id, timezone_name, now, latest=8) -> dict` with keys `new_today: int` (created since local midnight), `hot: int` (interest hot, stage not closed), `waiting: int` (stage handed off), `needs_you: list[Lead]` (handed off, oldest `last_user_msg_at` first, nulls last), `latest: list[Lead]` (newest `latest` leads by id). Route `GET /dash/{slug}/home` → `home.html` with context `user`, `institute`, `summary`, `local`, `intro_name` (`institute.name` for an owner, `"VidyaDesk"` for the admin; Task 5 uses it). `_home()` returns `/dash/{slug}/home` for owners.

- [ ] **Step 1: Write the failing tests.** In `tests/test_store.py`:

```python
def test_home_summary_counts_and_orders(session):
    # institute in Asia/Kolkata; now = NOON_IST
    # lead A created today, interest hot; lead B created yesterday, handed_off, last msg 3 h ago;
    # lead C handed_off, last msg 10 h ago; lead D hot but closed; lead E in another institute
    s = repo.home_summary(session, institute.id, "Asia/Kolkata", NOON_IST, latest=8)
    assert (s["new_today"], s["hot"], s["waiting"]) == (1, 1, 2)
    assert [l.id for l in s["needs_you"]] == [C.id, B.id]
    assert [l.id for l in s["latest"]] == [D.id, C.id, B.id, A.id]
```

In `tests/test_dashboard_home.py` (fixtures like `tests/test_dashboard_leads.py`: `bright` with an owner, `other`):

```python
def test_owner_login_lands_on_home(...): login → 303 to "/dash/bright/home"; GET /dash → same
def test_home_shows_numbers_and_needs_you(...): handed-off "Aman Kumar" appears under "Needs you" with "Waiting"
def test_home_shows_only_this_institute(...): other institute's "Secret Student" absent
def test_home_of_another_institute_is_404(...): GET /dash/other/home → 404
def test_home_escapes_student_names(...): name "<script>alert(1)</script>" → "&lt;script&gt;" present, raw absent
def test_nameless_lead_says_name_not_given_never_none(...): lead with no name/class/course → "Name not given" in page, ">None<" and " None " absent
def test_empty_institute_shows_empty_states(...): no leads → "Nothing waiting. The assistant is handling every enquiry." and "No enquiries yet." in page
def test_admin_can_open_an_institute_home(...): admin GET /dash/other/home → 200
```

Update `tests/test_dashboard_auth.py` lines 33–34 to expect `/dash/bright/home`.

- [ ] **Step 2: Run** `.\.venv\Scripts\python -m pytest tests/test_dashboard_home.py tests/test_store.py tests/test_dashboard_auth.py -q`. Expected: FAIL (404 for `/home`, `home_summary` missing, landing URL).

- [ ] **Step 3: Implement** `home_summary` (local midnight via `ZoneInfo(timezone_name)`, like `lead_stats`), the route (same access pattern as `stats_page`: `_user` → `_institute`; `now=utcnow()`), `_home` change, and `home.html`: the three number cards (labels "new today", "hot", "waiting"), section "Needs you" (rows with detail `Class · course · handoff reason`; empty text "Nothing waiting. The assistant is handling every enquiry."), section "Latest leads" (rows; empty text "No enquiries yet."; link "See all leads" to `/dash/{slug}/leads`). Each number card carries `data-count="{{ n }}"` for Task 5's count-up.

- [ ] **Step 4: Run** the focused tests, then the full suite. Expected: all pass, 1 skipped.

- [ ] **Step 5: Commit** `git commit -m "VidyaDesk Home: what needs the owner now"`.

---

### Task 3: Leads list and lead conversation

**Files:**
- Modify: `leadagent/dashboard/templates/leads.html`, `leadagent/dashboard/templates/lead.html`, `tests/test_dashboard_leads.py`

**Interfaces:**
- Consumes: `_ui.html` macros and CSS classes (Task 1). Routes and their context are unchanged.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_dashboard_leads.py`):

```python
def test_transcript_is_shown_as_chat_bubbles(...): messages user/assistant/owner → 'class="bubble user"', 'class="bubble assistant"', 'class="bubble owner"' present, in order
def test_lead_page_actions_are_post_forms(...): three <form method="post"> with actions /resume, /close, /delete; delete still has the confirm() onsubmit
```

- [ ] **Step 2: Run** them. Expected: FAIL (no `bubble` classes).

- [ ] **Step 3: Implement.** `leads.html`: filter bar restyled (selects + Filter button + "Download CSV" as `.btn-quiet`), below 900 px each lead is a `lead_row` (detail `Class · course · created time`), from 900 px a table (same columns as now). `lead.html`: details card (avatar, name, badge, class, course, contact, interest reason, notes, first/last message), action buttons (`.btn` resume, `.btn-quiet` close, `.btn-danger` delete; disabled states kept), transcript as bubbles — student left (white), assistant right (saffron), owner right (amber, labelled "You"), each with a small time line. Keep `white-space: pre-wrap` on bubble text.

- [ ] **Step 4: Run** `tests/test_dashboard_leads.py`, then the full suite. Expected: all pass, 1 skipped (the XSS, CSV and 404 tests unchanged).

- [ ] **Step 5: Commit** `git commit -m "VidyaDesk Leads and conversation view"`.

---

### Task 4: Documents, Facts, Stats and admin Institutes

**Files:**
- Modify: `leadagent/dashboard/templates/documents.html`, `facts.html`, `stats.html`, `institutes.html`

**Interfaces:**
- Consumes: Task 1 CSS classes. Routes and context unchanged.

- [ ] **Step 1: Restyle** each page with cards: Documents (upload card with the accepted types line, list of documents as rows with a status pill: ready green, failed red with its error; delete `.btn-danger` with confirm), Facts (help text card, monospace textarea in a card, saffron Save), Stats (three summary numbers as `.stat` cards for total / % hot / waiting, the 14 day bars in saffron), Institutes (each institute a card or table row with on/off pill and switch button; "Add an institute" form in a card; token field stays `type=password` with no `value`).

- [ ] **Step 2: Run** `.\.venv\Scripts\python -m pytest tests/test_dashboard_documents.py tests/test_dashboard_facts_stats.py tests/test_dashboard_admin.py -q`, then the full suite. Expected: all pass, 1 skipped (their text assertions such as "2 leads", "50% hot", "1 waiting", "Added faq.txt" still hold — keep those phrases).

- [ ] **Step 3: Commit** `git commit -m "VidyaDesk Documents, Facts, Stats and Institutes"`.

---

### Task 5: First-visit intro animation, docs

**Files:**
- Create: `leadagent/dashboard/templates/intro.js`
- Modify: `leadagent/dashboard/templates/home.html`, `leadagent/dashboard/templates/vidyadesk.css`, `tests/test_dashboard_home.py`, `README.md`, `docs/DEMO_CHECKLIST.md`, `docs/specs/2026-10-13-lead-agent-design.md` (Section 15)

**Interfaces:**
- Consumes: `intro_name` in the Home context and `data-count` on the number cards (Task 2).
- Produces: overlay `<div id="intro" hidden>` in `home.html`; browser storage key `vidyadesk-intro-seen` (value `"1"`).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_dashboard_home.py`):

```python
def test_home_carries_the_intro_hidden_by_default(...): owner GET /home → '<div id="intro" hidden' present,
    "Education is the most powerful weapon which you can use to change the world." present, "Nelson Mandela" present,
    the institute name inside the intro, "Skip" present
def test_admin_intro_shows_the_product_name(...): admin GET /dash/bright/home → intro contains "VidyaDesk"
def test_intro_name_is_escaped(...): institute name "<b>x</b>" → "&lt;b&gt;x&lt;/b&gt;" in page
```

- [ ] **Step 2: Run** them. Expected: FAIL (no `#intro`).

- [ ] **Step 3: Implement.** Copy the mockup's intro scene (glow, ring + book SVG, "Welcome", name, word-by-word quote, attribution) and its keyframes and timings into `home.html` / `vidyadesk.css`, scoped under `#intro`. `intro.js` (included in `home.html` in a `<script>`):
  - Return at once if `matchMedia('(prefers-reduced-motion: reduce)').matches` or the stored key is `"1"` (read inside `try/catch`; on error treat as "not seen" but never throw).
  - Otherwise remove `hidden`, split the quote into word spans with the mockup's delays, and after the mockup's lift-away time hide the overlay and add a class to `<body>` that runs the Home build-up (number cards rise and count up from 0 to their `data-count`, rows rise one after another — mockup timings).
  - Skip link: ends the overlay at once and shows the page as is.
  - Store `"1"` when it ends or is skipped (in `try/catch`).
  - The overlay is `position: fixed`, covers the page, and has the Home's own content underneath already rendered.

- [ ] **Step 4: Run** the focused tests, then the full suite. Expected: all pass, 1 skipped.

- [ ] **Step 5: Manual check** (record the result in the report): start the app (`powershell -ExecutionPolicy Bypass -File .\start-demo.ps1` or uvicorn with `SESSION_HTTPS_ONLY=false` locally), log in as the owner in a fresh browser profile: the intro plays once, a reload does not play it, Skip works, a private window plays it once, and with the OS "reduce motion" setting on nothing animates. Check one page at 360 px width (browser dev tools) for sideways scroll.

- [ ] **Step 6: Docs.** README Dashboard section: name the product VidyaDesk, mention Home and the first-visit intro. DEMO_CHECKLIST Dashboard section: add "- [ ] The first login on a new phone plays the intro once; Skip works." Spec Section 15: add rows

```markdown
| Dashboard | Telegram alerts and the morning summary keep their plain layout (the redesign covered web pages only) | Before the first pitch | Clear headings and markers, same content |
| Dashboard | No dark mode | Owners ask for it | Second set of colour tokens under prefers-color-scheme |
| Dashboard | "Needs you" is ordered by the student's last message; there is no handoff timestamp | Owners want to see how long a lead has waited | A handed_off_at column set by the handoff tool |
```

- [ ] **Step 7: Commit** `git commit -m "VidyaDesk first-visit intro, docs and backlog"`.

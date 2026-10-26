# VidyaDesk Demo Video Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A ~2-minute narrated motion-graphics MP4 of VidyaDesk, built from a real recorded agent run, committed to the repo and rebuildable.

**Architecture:** Four steps, each writing files the next one reads.
1. `demo/run_chat.py` sends a scripted sample conversation through the real pipeline on the **test** database and writes `demo/chat-run.json`.
2. `demo/narration.py` turns the ten approved voice lines into MP3s and records their durations.
3. `demo/scenes/index.html` draws every frame as a pure function of time (`window.seek(t)`), reading the JSON files and the dashboard screenshots.
4. `demo/render.py` steps that page frame by frame in headless Microsoft Edge (Playwright, `channel="msedge"`), pipes the PNGs into ffmpeg, and muxes in the narration.

**Tech Stack:** Python, Playwright for Python (Edge channel), edge-tts 7.x, ffmpeg (installed at `C:\msys64\mingw64\bin\ffmpeg.exe`), plain HTML/CSS/JS.

**Spec:** `docs/specs/2026-10-26-demo-video-design.md` (approved 26 Oct 2026). Its storyboard table holds the exact voice lines; its "Claims and their source" table is the truth check.

## Global Constraints

- Output: 1920 × 1080, 30 fps, H.264 + AAC MP4 at `docs/demo/vidyadesk-demo.mp4`, under 30 MB.
- Voice `en-IN-PrabhatNeural`, edge-tts 7.x, in `demo/.venv` (git-ignored); pinned `demo/requirements.txt`. Never upgrade PROJECT YOUTUBE's environment.
- Every chat line, lead field and alert shown comes from `demo/chat-run.json`, word for word. The only allowed edit is cutting whole sentences, shown as "…". The voice lines are the spec table's, verbatim.
- Only the **test** database (`TEST_DATABASE_URL`, name ends `leadagent_test`); refuse to run otherwise. Fictional students only.
- Colours: cream `#fbf8f3`, saffron `#c2410c`, ink `#2b2118`, and the VidyaDesk ring-and-book mark (from `leadagent/dashboard/templates/_ui.html`).
- Length set by the narration: anything about 1:50–2:30. Text on screen readable at phone size, and shown for ≥ 2 s.
- No hardcoded absolute paths in committed code (`Path(__file__).parent`); ffmpeg is found on PATH.
- Never print `.env` values.

## Review Focus

1. **A model reply that is the pipeline's fallback** ("We'll get back to you shortly.") because Gemini rate-limited or failed. It must not end up in the video as if it were a real answer. (Task 1 test.)
2. **Odia and Devanagari text in headless Edge.** It must render as real script, not empty boxes. (Task 3 check of the Odia frame.)
3. **A long reply.** It must fit its bubble at 1080p: whole sentences are cut and marked "…", never shrunk to unreadable size. (Task 3 check.)
4. **Audio and picture drifting apart over two minutes.** Scene starts come from the measured MP3 durations, and the frame count equals the total duration × 30. (Task 4 check: last voice line ends with the last scene.)
5. **Text retyped into the scenes instead of read from the run file.** The HTML must contain no reply text of its own. (Task 3 test.)

---

### Task 1: Record a real agent run

**Files:**
- Create: `demo/run_chat.py`, `demo/requirements.txt`, `demo/.gitignore` (`.venv/`, `build/`), `tests/test_demo_chat.py`
- Output (committed): `demo/chat-run.json`

**Interfaces:**
- Produces: `run_conversation(students, graph=None, pause=12.0) -> dict` in `demo/run_chat.py`. `students` is a list of `{"user_id": str, "turns": [str]}`. It returns `{"model": str, "recorded_at": iso str, "students": [{"user_id", "turns": [{"user": str, "reply": str}], "lead": {name, student_class, course, stage, interest, interest_reason, handoff_reason}}], "alerts": [str]}`. It raises `RuntimeError` if any reply equals `leadagent.pipeline.FALLBACK`.
- `DEMO_STUDENTS` constant (the script's conversation):
  - Student `demo-1` (English): `"Hi, what is the fee for JEE coaching? My son is in class 11."`, `"His name is Rahul Sharma. We want to join this month. Is there a demo class?"`, `"Can I talk to sir?"`, `"OK, we will come on Saturday."`
  - Student `demo-2` (Hindi): `"नमस्ते, JEE कोचिंग की फीस कितनी है?"`
  - Student `demo-3` (Odia): `"ନମସ୍କାର, JEE କୋଚିଂ ଫି କେତେ?"`
- `main()`:
  1. Points `DATABASE_URL` at `TEST_DATABASE_URL` and refuses if the name does not end `leadagent_test`.
  2. Recreates the `brightpath` institute from `examples/brightpath.yaml`, with owner chat `"999"` so alerts are produced.
  3. Ingests `examples/brightpath-prospectus.txt`.
  4. Runs `DEMO_STUDENTS` through `leadagent.pipeline.process(IncomingMsg(...))`, with `leadagent.pipeline.deliver` and `leadagent.notify.deliver` replaced by a recorder that returns `True`. Alerts are the recorded owner-chat sends; replies are the recorded student sends.
  5. Writes `demo/chat-run.json` (UTF-8, `ensure_ascii=False`).

- [ ] **Step 1: Write the failing tests** in `tests/test_demo_chat.py` (import `run_conversation` by adding `demo/` to `sys.path`). Use the main suite's fixtures and a `build_graph(ScriptedModel(...), get_checkpointer())`, with `pause=0`:

```python
def test_records_replies_lead_and_alerts(session, sent):
    # scripted: save_lead + set_interest hot, then a text reply
    run = run_conversation([{"user_id": "demo-1", "turns": ["Fee?"]}], graph=graph, pause=0)
    student = run["students"][0]
    assert student["turns"][0]["user"] == "Fee?" and student["turns"][0]["reply"] == "68,000 a year."
    assert student["lead"]["name"] == "Rahul Sharma" and student["lead"]["interest"] == "hot"
    assert any(alert.startswith("🔥 Hot lead #") for alert in run["alerts"])

def test_a_fallback_reply_stops_the_run(session, sent):
    # scripted model raises → pipeline replies FALLBACK
    with pytest.raises(RuntimeError, match="fallback"):
        run_conversation([{"user_id": "demo-1", "turns": ["Fee?"]}], graph=failing_graph, pause=0)
```

- [ ] **Step 2: Run** `.\.venv\Scripts\python -m pytest tests/test_demo_chat.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement `demo/run_chat.py`** as above. Create `demo/.venv` with `python -m venv demo\.venv`, then `pip install "edge-tts==7.3.1" playwright`, and pin the exact installed versions in `requirements.txt`. `run_chat.py` and `shots.py` run in the project's `.venv` (they need `leadagent`); `narration.py` and `render.py` run in `demo/.venv`.
- [ ] **Step 4: Run** the tests (expected PASS), then the full suite (expected: all pass, 1 skipped).
- [ ] **Step 5: Real run.** `.\.venv\Scripts\python demo\run_chat.py` (Gemini, about 2 minutes with pauses). Expected: `demo/chat-run.json` with 6 replies, none equal to the fallback, at least one `🔥 Hot lead` alert and one `🙋 Handoff` alert. Read every reply and record in the report anything that differs from the storyboard's expectation.
- [ ] **Step 6: Commit** `demo/run_chat.py demo/requirements.txt demo/.gitignore demo/chat-run.json tests/test_demo_chat.py`: "Demo video: record a real agent run".

---

### Task 2: Narration audio

**Files:**
- Create: `demo/narration.py`
- Output (git-ignored): `demo/build/audio/scene-01.mp3` … `scene-10.mp3`; committed: `demo/narration.json`

**Interfaces:**
- Produces: `SCENES: list[dict]` (keys `id`, `title`, `line`) with the spec table's 10 voice lines verbatim, and `VOICE = "en-IN-PrabhatNeural"`. `main()` synthesises each line into its MP3 and measures it with `ffprobe`. It writes `demo/narration.json` = `{"voice", "gap": 0.6, "scenes": [{"id", "title", "line", "audio", "duration"}]}`. `gap` is the seconds of silence after each line.

- [ ] **Step 1: Write the test** `tests/test_demo_chat.py::test_narration_lines_match_the_approved_storyboard`: `len(SCENES) == 10`; `SCENES[0]["line"]` equals the spec's first line and `SCENES[9]["line"]` its last; `VOICE == "en-IN-PrabhatNeural"`.
- [ ] **Step 2: Run** it. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `demo/narration.py`. Run the edge-tts CLI from `demo/.venv`. Get each duration from `ffprobe -show_entries format=duration`.
- [ ] **Step 4: Run** the test, then `demo\.venv\Scripts\python demo\narration.py`. Expected: 10 MP3s, every duration > 1 s, total between 100 and 150 s (print it).
- [ ] **Step 5: Commit** `demo/narration.py demo/narration.json tests/test_demo_chat.py`: "Demo video: narration".

---

### Task 3: The animated scenes

**Files:**
- Create: `demo/scenes/index.html` (with its CSS and JS inline), `demo/shots.py`, `demo/render.py` (stills mode only: serves `demo/` on a local `http.server` thread so `fetch` works, opens Playwright Edge at 1920 × 1080, waits for `window.ready`, and saves `seek(t)` for each second in `--stills a,b,c` to `demo/build/stills/`)
- Output (git-ignored): `demo/build/shots/*.png`

**Interfaces:**
- Consumes: `demo/chat-run.json` (Task 1) and `demo/narration.json` (Task 2), loaded with `fetch` relative to the page.
- Produces: `window.ready` (a Promise resolving when the data and images are loaded), `window.seek(t: number)` (draws the frame at `t` seconds, pure and repeatable), and `window.totalDuration` (seconds). Scene `i` starts at the sum of the previous scenes' `duration + gap`.
- `demo/shots.py` retakes the dashboard screenshots at 1920 × 1080 (laptop) and 390 × 844 (phone): Home, a conversation (student `demo-1`), Leads and Stats. It uses the same method as the README screenshots: a preview app on port 8001 against the test database, logging in as a demo owner it creates there.

- [ ] **Step 1: Write the test** `tests/test_demo_chat.py::test_scenes_contain_no_chat_text_of_their_own`: `demo/scenes/index.html` contains `chat-run.json` and `narration.json`, and contains none of the reply strings from `demo/chat-run.json`.
- [ ] **Step 2: Run** it. Expected: FAIL (file missing).
- [ ] **Step 3: Implement** the ten scenes from the spec storyboard in the VidyaDesk look, every animation driven by `seek(t)` (no CSS animations or timers):
  - Scene 4 shows `demo-1`'s first reply, then `demo-2`'s and `demo-3`'s.
  - Scene 5 shows `demo-1`'s lead card and the first `🔥` alert.
  - Scene 6 shows the `"Can I talk to sir?"` turn, its reply and the `🙋` alert.
  - Scene 7 shows the screenshots.
  - Scene 9 shows the chips with the spec's numbers.
  - A reply too long for its bubble at 28 px or more is cut at a sentence boundary with "…".
- [ ] **Step 4: Run** the test (PASS). Then check frames by hand:
  - Run `demo\.venv\Scripts\python demo\render.py --stills 5,35,55,65,80,105,118`. Open each PNG.
  - Odia and Devanagari must show as real script.
  - Every line must be readable when the image is scaled to 360 px wide.
  - Nothing may overflow.
- [ ] **Step 5: Commit** `demo/scenes/index.html demo/shots.py tests/test_demo_chat.py`: "Demo video: animated scenes".

---

### Task 4: Render, mux, publish in the repo

**Files:**
- Create: `demo/README.md`
- Modify: `demo/render.py` (add the full render; keep `--stills`)
- Modify: `README.md` (a "Demo" line under the screenshots), `docs/specs/2026-10-13-lead-agent-design.md` (Section 15 row if anything was cut)
- Output (committed): `docs/demo/vidyadesk-demo.mp4`, `docs/demo/poster.png`

**Interfaces:**
- Consumes: `window.ready`, `window.seek`, `window.totalDuration` (Task 3); the MP3s and `narration.json` (Task 2).
- `render.py`:
  1. Reuses Task 3's local server and Edge page.
  2. For each frame `n` in `range(round(totalDuration * 30))`, calls `seek(n / 30)` and takes a PNG screenshot, piped to `ffmpeg -f image2pipe -framerate 30 -i - -c:v libx264 -pix_fmt yuv420p -crf 20`.
  3. Builds the audio track by concatenating each MP3 followed by its `gap` of silence, then muxes it in with AAC 160k into `docs/demo/vidyadesk-demo.mp4`.
  4. Saves the frame at 20 s as `docs/demo/poster.png`.

- [ ] **Step 1: Render** with `demo\.venv\Scripts\python demo\render.py`. Expected: the MP4 exists; `ffprobe` shows 1920x1080, 30 fps, h264 + aac, the duration within 0.2 s of `totalDuration`, and a size under 30 MB (if not, raise CRF to 23 and re-render).
- [ ] **Step 2: Watch the whole video once**:
  - Compare every voice line and every on-screen claim with the spec's "Claims and their source" table.
  - Check that the picture changes scene when the voice does.
  - Record in the report the time and the check for each scene.
- [ ] **Step 3: Write `demo/README.md`**: what the video is, how to rebuild it (venv, the four commands in order), and that the chat text is a real recorded run on sample data.
- [ ] **Step 4: Update `README.md`**: under the screenshots, add "**Demo video:** [watch the 2-minute demo](docs/demo/vidyadesk-demo.mp4)". When Yash uploads it, this becomes the inline player. Note in the report that the inline player needs Yash's one-minute upload on github.com (spec).
- [ ] **Step 5: Run** the full suite (expected: all pass, 1 skipped), then commit `demo/render.py demo/README.md docs/demo README.md`: "Demo video: render and add to the repo".

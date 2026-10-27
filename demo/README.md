# Demo video

`docs/demo/vidyadesk-demo.mp4` is a 2-minute narrated walkthrough of VidyaDesk for recruiters and coaching
institutes. Design and storyboard: [docs/specs/2026-10-26-demo-video-design.md](../docs/specs/2026-10-26-demo-video-design.md).

**What is real in it:** every chat line, the saved lead, the owner alerts and the morning summary come from a real
run of the agent (Gemini, on the test database, with fictional students), recorded in `chat-run.json` and
`digest.json`. The only edit is cutting the assistant's "I am an automated assistant…" sentence, shown as "…".
The dashboard images are screenshots of the real app holding the same text (the dates and times on them are when the
screenshots were taken). The opening two scenes (10:42 pm, no reply) are a staged example and are labelled "Example scene".

## Rebuild

Two environments: the app's `.venv` (needs `leadagent`) and `demo\.venv` (edge-tts 7 and Playwright, see
`requirements.txt`; edge-tts 6 is refused by Microsoft's voice service). Microsoft Edge and ffmpeg must be installed.

    python -m venv demo\.venv
    demo\.venv\Scripts\python -m pip install -r demo\requirements.txt

    .\.venv\Scripts\python demo\run_chat.py        # 1. real agent run -> chat-run.json (about 2 minutes, Gemini)
    demo\.venv\Scripts\python demo\narration.py    # 2. voice lines -> build/audio/*.mp3 + narration.json
    .\.venv\Scripts\python demo\shots.py           # 3. dashboard screenshots + digest.json
    demo\.venv\Scripts\python demo\render.py       # 4. frames + voice -> docs/demo/vidyadesk-demo.mp4

`render.py --stills 5,40,80` saves single frames to `build/stills/` for checking a change quickly.

**The database:** steps 1 and 3 only ever use the **test** database (`TEST_DATABASE_URL`, `leadagent_test`) and clear
it first. `testdb.py` switches to it before any app code is imported and refuses to run against any other database.
Steps 2 and 4 do not touch a database.

## Files

| File | What it does |
|---|---|
| `run_chat.py` | Sends the sample conversation through the real pipeline and records replies, lead and alerts |
| `narration.py` | The ten voice lines (voice `en-IN-PrabhatNeural`) and how long each scene stays on screen |
| `shots.py` | Rebuilds the dashboard data from `chat-run.json` and screenshots it with headless Edge |
| `scenes/index.html` | Draws every frame as a function of time from the recorded files |
| `render.py` | Steps the scenes in Edge, encodes with ffmpeg, adds the narration |
| `testdb.py` | Keeps steps 1 and 3 on the test database |

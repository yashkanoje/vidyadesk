# VidyaDesk demo video

Date: 26 Oct 2026. Storyboard and voice approved by Yash in the browser preview ("everything is good").

## Why

The public repo (github.com/yashkanoje/vidyadesk) needs a short video that lets two audiences understand the
product in about two minutes:

- **Recruiters** should come away knowing what Yash built and that it is real engineering: a LangGraph agent,
  document search on pgvector, measured results.
- **Coaching-institute owners** should understand how it works for them: enquiries answered at any hour, leads
  captured, the owner alerted, and everything in one dashboard.

Yash wants a "startup" feel: motion graphics with an AI voice explaining over the animation.

## Goals

- An MP4 of about 2 minutes, motion graphics in the VidyaDesk look, narrated by the **en-IN-PrabhatNeural** voice
  (Microsoft neural voice via edge-tts).
- Added to the repo and shown from the README.
- Rebuildable: the scenes and build script live in the repo, so the video can be regenerated after a change.

## Non-goals

- No live screen recording of a phone.
- No background music (avoids licensing questions). Builder may revisit only with a royalty-free track, as a
  separate request.
- The pitch one-pager with pricing is a separate piece, done after the video.

## Anti-goals (a failure even if it looks good)

- **Anything shown or said that the product does not really do, or any number that was not measured.** Yash's
  standing rule: no made-up claims. Every feature in the voice lines was checked in the code (see "Claims and their
  source" below), and the chat text must come from a real run of the agent.
- Real student data. Only sample data (test database, fictional names) appears.
- Unreadable text: anything on screen must be legible on a phone at 1080p for at least ~2 seconds.

## Decided

**Format:** 1920 × 1080, 30 fps, H.264 MP4 with AAC audio, target under 30 MB. Colours and the ring-and-book mark
from VidyaDesk (cream `#fbf8f3`, saffron `#c2410c`, ink `#2b2118`).

**Voice:** en-IN-PrabhatNeural. edge-tts 7.3.1 works; 6.1.12 (installed in PROJECT YOUTUBE) gets 403 from
Microsoft's service, so use 7.x in a separate environment and never upgrade PROJECT YOUTUBE's.

**Storyboard (approved; times are targets, the narration sets the real timing):**

| # | Time | Scene | Voice line |
|---|---|---|---|
| 1 | 0:00 | Hook: clock 10:42 pm, a parent's message about JEE fees lights up a phone | "It's 10:42 at night. A parent asks about JEE fees, and the institute is closed." |
| 2 | 0:08 | Problem: the message sits unanswered; another institute replies first | "Most enquiries arrive in the evening or during class. When nobody replies, the student asks the next institute." |
| 3 | 0:20 | VidyaDesk logo draws itself | "Meet VidyaDesk, an AI assistant for coaching institutes." |
| 4 | 0:28 | Chat: question and reply with the fee; then the same in Hindi and in Odia, replies in the same script | "It answers fees, batches and timings from the institute's own facts, with exact numbers, in English, Hindi, Hinglish or Odia." |
| 5 | 0:50 | Chat folds into a lead card (name, class, course, Hot); a Telegram alert lands on the owner's phone | "While it chats, it saves the student's name, class and course, rates their interest, and alerts the owner the moment a lead is hot." |
| 6 | 1:02 | "Can I talk to sir?" The assistant steps back; owner gets a handoff alert | "When a parent wants a person, it hands the chat to the owner, and passes on any new messages." |
| 7 | 1:12 | Real dashboard screenshots: Home, a conversation, leads table, stats | "Every enquiry lands in the VidyaDesk dashboard: who needs a call, every conversation, and a CSV for Excel." |
| 8 | 1:30 | One polite daytime nudge to a quiet lead; 08:00 summary for the owner | "If a student goes quiet, it follows up once, politely. Every morning at eight, the owner gets a summary." |
| 9 | 1:40 | Architecture flow animates; chips: LangGraph · RAG on pgvector · 26/26 behaviour checks · 21/21 retrieval · 316 tests · each institute sees only its own data | "Under the hood: a LangGraph agent, document search with pgvector, and measured results: twenty-six of twenty-six behaviour checks, and three hundred and sixteen automated tests." |
| 10 | 1:55 | Logo, "Every enquiry answered. Every lead captured.", github.com/yashkanoje/vidyadesk | "VidyaDesk. Every enquiry answered. Every lead captured." |

**Chat text (scenes 4–6):** taken word for word from a real run of the agent: the recorded behaviour-check
transcript `evals/out/20261016-110610-gemini.md` (Gemini, 16 Oct 2026, the 26/26 run) or a fresh run on the test
database. A long reply may be cut at a sentence boundary and marked with "…"; nothing is reworded. The Odia lines
have not had a native speaker's read yet (spec Section 16); they are shown as the model wrote them.

**Alert text (scenes 5, 6):** the real formats from `leadagent/agent/tools.py`: `🔥 Hot lead #<id>` / description /
`Why: <reason>`, and `🙋 Handoff: lead #<id>` / description / `Why: <reason>` / `Send /resume <id> …`.

**Dashboard (scene 7):** real screenshots of VidyaDesk with the sample data, as in `docs/images/` (the builder may
retake them at a higher resolution the same way).

**In the repo:** the video at `docs/demo/vidyadesk-demo.mp4`; the scenes and build script in `demo/` (with a short
README on how to rebuild). **The video plays on the repo page** (Yash's choice): when the MP4 is ready, Yash drags it
into GitHub's web editor once (about a minute), GitHub returns a `user-attachments` link, and Claude puts that link
near the top of the README. Until then the README keeps its screenshots.

## Claims and their source (checked in the code on 26 Oct 2026)

| Claim in the voice lines | Where it is true |
|---|---|
| Answers from the institute's own facts, exact numbers | `agent/prompts.py` facts block; eval number check |
| English, Hindi, Hinglish, Odia | behaviour checks `hi-*`, `hinglish-*`, `or-*`, `or-latin-*` (26/26, one run) |
| Saves name, class, course; rates interest | tools `save_lead`, `set_interest` |
| Alerts the owner when a lead is hot | `set_interest` → `notify.alert` "🔥 Hot lead" |
| Hands the chat to the owner and passes on new messages | `handoff` tool; graph `relay` forwards the student's messages to the owner (one way only) |
| Dashboard: who needs a call, every conversation, CSV | Home "Needs you", lead page, `leads.csv` |
| Follows up once, politely | `jobs/nudge.py`, `repo.due_nudges` (once, 2–20 h after the last message, 09:00–21:00) |
| 08:00 summary | `jobs/digest.py` |
| 26/26, 21/21, 316 tests | spec Section 16, `evals.retrieval` output, pytest |

## Calls made after the builder check (Claude's, for Yash to check)

- **Chat text comes from a fresh run, recorded as evidence.** A script sends a short demo conversation through the
  real graph and the real model (Gemini free tier) on the **test** database with a fictional student. That covers the
  fee question in English, Hindi and Odia, giving details, a hot moment, and "Can I talk to sir?". It records every
  reply, the saved lead fields, and the exact alert texts produced by the real code (captured instead of sent to
  Telegram) in `demo/chat-run.json`. The video uses only text from that file. If the model says something different
  from the storyboard's expectation (for example a plain "our team will contact you" at the handoff), the video shows
  what it said and the scene adapts.
- Long replies: the automated-assistant sentence and other whole sentences may be cut, marked "…"; never reworded.
- Length: the narration sets it; anything from about 1:50 to 2:30 is fine.
- Environment: `demo/.venv` (git-ignored) with pinned `demo/requirements.txt` (edge-tts 7.x, Playwright).
- Renderer: Playwright driving the **installed Microsoft Edge** (`channel="msedge"`), so no browser download is
  needed.
- Scene 7 screenshots are retaken at full HD from the dashboard running on the test database with sample data,
  including the Stats page.

## Left to the builder

- How the scenes are animated and rendered (for example HTML/CSS scenes stepped frame by frame in headless
  Chromium, then encoded with ffmpeg, which is installed).
- Exact visual design of each scene within the VidyaDesk look, transitions, and pacing to the narration.
- Whether the README preview is a still image or a short GIF.

## Checks before it is called done

- Watch the full video once; compare every voice line and on-screen claim against the table above.
- Readable at phone size; audio and picture in sync; file under 30 MB; plays from the GitHub repo page.

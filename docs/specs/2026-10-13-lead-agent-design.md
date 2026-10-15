# Lead Agent for Coaching Institutes — Design Spec

**Date:** 13 October 2026 · **Author:** Yash Kanoje · **Status:** awaiting review

No code exists yet. This document is the agreed design. A separate build plan is written
for each milestone after this spec is approved.

---

## 1. Purpose

An AI agent that answers student and parent enquiries for coaching institutes on WhatsApp
and Telegram, records each enquiry as a lead, and makes sure the institute's owner follows
up.

**Why it is being built**

- It is a first paid-agent product: generic demo, then 1–2 institutes as case studies, then
  paying clients.
- It gives real, defensible experience with LangGraph, RAG, PostgreSQL and CI.

**Success criteria**

| Level | Criterion |
|---|---|
| M1 | Two sample institutes run side by side. Conversations in English, Hindi, Hinglish and Odia produce correct leads. No reply contains a fee that is not in the institute's facts. A resent webhook produces one reply. |
| M2 | On the retrieval test set, the correct passage is in the top 3 results for at least 80% of questions. |
| M3 | An owner can log in on a phone, see only their own leads, read a transcript, and upload a brochure. |
| Product | One real institute uses it for 2 weeks or more and reports that enquiries were not missed. |

## 2. Scope

**In scope**

- Multi-client from the start: several institutes on one deployment.
- Two channels: Telegram (development and testing) and WhatsApp Cloud API (demos, clients).
- Replies in the language the user writes in.
- Lead capture, interest rating, handoff to a human.
- Owner alerts, a daily summary, and one nudge to a quiet lead.
- RAG over documents the institute uploads.
- A web dashboard for owners and for the admin.

**Out of scope for this spec:** everything in Section 15.

## 3. Decisions

| Topic | Decision | Reason |
|---|---|---|
| First target | Generic demo, pitch afterwards | No institute is lined up yet |
| Channels | Telegram and WhatsApp behind one common message format | Telegram is free and unlimited for building; institutes use WhatsApp |
| Languages | Mirror the user's language | Odia- and Hindi-speaking parents are a large share of enquiries |
| Framework | LangGraph | Chat state per user, widely asked for in AI-engineer roles |
| Model | `LLM_PROVIDER` chooses: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`, with prompt caching) or Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`, minimal thinking). Gemini's free tier is for development and test data only | Claude: low cost per lead. Gemini: free while building (added 14 Oct 2026 because the Anthropic account had no API credits) |
| Database | PostgreSQL with the pgvector extension | One database for leads, chat state and vectors |
| Exact facts | Structured facts in the prompt, not RAG | Fees and timings must be exact |
| Long documents | RAG | Brochures and prospectuses are too long for the prompt |
| Embeddings | `BAAI/bge-small-en-v1.5` through fastembed (384 dimensions) | Free, no torch, no extra API key. The agent searches in English, so an English model is enough |
| Dashboard | Server-rendered pages inside the same FastAPI app | No separate frontend build |
| Google Sheet copy | Dropped | The dashboard and a CSV export replace it |
| Owner notifications | Telegram | WhatsApp only allows free messages within 24 hours of the recipient's last message, so a daily summary to an owner on WhatsApp would need paid template messages |

## 4. Architecture

```
 Telegram ─┐                                               ┌─► Claude Haiku 4.5
 WhatsApp ─┼─► FastAPI webhooks ─► channel adapter ─► LangGraph agent
           │   (verify, find        (→ IncomingMsg)      │   + tools
           │    institute)                               ▼
           │                         PostgreSQL: institutes, users, leads, messages,
           │                         documents, chunks (pgvector) + LangGraph checkpointer
           │                                  ▲                 ▲
 Scheduler: nudge job, daily summary ─────────┘                 │
        │                                                       │
        └─► Owner notifier (Telegram)          Dashboard (same FastAPI app) ─┘
```

**Components.** Each has one job and is testable alone.

| Unit | Does | Interface |
|---|---|---|
| `channels/` | Verifies and parses incoming webhooks, sends replies | `parse(request) -> IncomingMsg`, `send(institute, user_id, text)` |
| `agent/` | The LangGraph graph: state, nodes, prompts, tools | `handle(IncomingMsg) -> reply text` |
| `store/` | SQLAlchemy models and query functions | `upsert_lead()`, `due_nudges()`, … |
| `rag/` | Document ingestion and search (M2) | `ingest(institute, file)`, `search(institute, query)` |
| `jobs/` | Scheduled nudge and daily-summary jobs | Run by APScheduler |
| `notify.py` | Owner alerts and the daily summary | `alert(institute, text)` |
| `dashboard/` | Login, pages and actions (M3) | FastAPI routes and Jinja templates |
| `app.py` | Webhook routes, health check, scheduler start-up | — |

**Rule:** the agent never talks to Telegram or WhatsApp directly. It receives an
`IncomingMsg` and returns text. A new channel is one new adapter file.

**Finding the institute for an incoming message**

- WhatsApp: one route, `/webhook/whatsapp`. The payload carries the receiving
  `phone_number_id`, which maps to one institute.
- Telegram: one bot per institute, at `/webhook/telegram/{institute_slug}`, each with its
  own secret token.
- A message that maps to no active institute is logged and dropped.

**Planned layout**

```
PROJECT LEAD AGENT/
├── leadagent/
│   ├── app.py  settings.py  notify.py
│   ├── channels/    base.py  telegram.py  whatsapp.py
│   ├── agent/       graph.py  tools.py  prompts.py
│   ├── store/       models.py  repo.py
│   ├── jobs/        nudge.py  digest.py
│   ├── rag/         ingest.py  search.py            (M2)
│   └── dashboard/   routes.py  templates/           (M3)
├── tests/
├── evals/           conversations.yaml  retrieval.yaml
└── docs/specs/
```

## 5. Agent graph

```
START → gate ──(lead is handed off)──► relay_to_owner → END
          │
          └──► agent ⇄ tools → END
```

| Node | Does |
|---|---|
| `gate` | Plain code, no model call. Loads or creates the lead, applies the limits below, checks whether a human has taken over. |
| `agent` | Claude Haiku 4.5. Replies in the user's language and decides when to call a tool. |
| `tools` | Runs the tool calls and returns results to `agent`. |
| `relay_to_owner` | Forwards the user's message to the owner. The bot does not answer it, except for "Our team has your message and will reply soon." at most once every 6 hours, so the student never meets total silence (added 14 Oct 2026 after the first live demo). |

**Tools**

| Tool | Does |
|---|---|
| `save_lead(name, student_class, course, phone, notes)` | Saves whichever fields are known. Fields not given are left unchanged. |
| `set_interest(level, reason)` | `hot`, `warm` or `cold`. `hot` alerts the owner at once. |
| `handoff(reason)` | Sets the stage to `handed_off`, alerts the owner, and tells the user the team will contact them. |
| `search_docs(query)` (M2) | Returns the 4 most relevant passages from the institute's documents. The agent writes `query` in English whatever language the user used. |

**Lead stages:** `new → collecting → qualified → handed_off / closed`. A lead is `qualified`
once name, class and course are known. Stage is a database field, not a graph node: users
do not follow a fixed order. Interest is a separate field.

**Limits applied by `gate`**

- 40 messages per user per day. Past that, the user gets one "our team will contact you"
  message and the owner is alerted.
- Messages longer than 1,000 characters are cut to 1,000.
- Only the last 20 messages are sent to the model.
- Voice notes, images and stickers get the reply "Please type your question."

**Safety rules**

- Facts come only from the institute's structured facts or from retrieved passages. If the
  answer is in neither, the agent says it will check with the team and calls `handoff`. It
  never invents fees, discounts or results.
- Tools act only on the current conversation's lead and institute. Both IDs come from graph
  state, never from model output.
- The first reply to a new lead says that this is an automated assistant and that their
  details are shared with the institute.
- The system prompt (rules plus the institute's facts) is one cached block.

**Handoff and return**

- After handoff the owner contacts the lead from the institute's normal number.
- Every owner alert shows the lead's ID. The owner sends `/resume <lead id>` to the
  institute's Telegram bot to switch the agent back on, and `/delete <lead id>` to remove a
  lead and its messages. A command is accepted only from the institute's registered owner
  chat.
- In M3 the same actions are dashboard buttons.

## 6. Data model

Six tables. All times are stored in UTC and shown in the institute's timezone.

**`institutes`**

| Column | Notes |
|---|---|
| `id`, `slug`, `name`, `active`, `created_at` | `slug` is unique |
| `timezone` | default `Asia/Kolkata` |
| `facts` | JSON: courses, fees, batches, timings, address, FAQ. Validated on every save. |
| `telegram_bot_token_enc`, `telegram_secret` | token encrypted, see Section 11. Every institute has a Telegram bot, because owner alerts and commands use it. |
| `whatsapp_phone_number_id`, `whatsapp_token_enc` | empty for a Telegram-only institute |
| `owner_telegram_chat_id` | where alerts and summaries go |

**`users`** (dashboard logins, M3)

| Column | Notes |
|---|---|
| `id`, `email`, `password_hash`, `role` | `role` is `admin` or `owner`; `email` is unique |
| `institute_id` | empty for the admin |

**`leads`**

| Column | Notes |
|---|---|
| `id`, `institute_id` | |
| `channel`, `channel_user_id` | unique together with `institute_id` |
| `name`, `student_class`, `course`, `phone`, `notes` | filled in gradually |
| `stage` | `new / collecting / qualified / handed_off / closed` |
| `interest`, `interest_reason` | `hot / warm / cold` |
| `handoff_reason` | |
| `created_at`, `last_user_msg_at` | |
| `nudged_at` | empty until the one nudge is sent |

**`messages`**

| Column | Notes |
|---|---|
| `id`, `institute_id`, `lead_id`, `role`, `text`, `created_at` | `role` is `user / assistant / owner` |
| `channel_msg_id` | unique per institute and channel for incoming messages. Stops a resent webhook from being answered twice. |

The LangGraph checkpointer also stores chat state, keyed by lead ID, but in a form SQL
cannot query. The `messages` table is the readable log used by the daily limit, the
summary, transcripts and the dashboard.

**`documents`** (M2)

| Column | Notes |
|---|---|
| `id`, `institute_id`, `filename`, `uploaded_at`, `status` | `status` is `ready` or `failed`, with the reason |

**`chunks`** (M2)

| Column | Notes |
|---|---|
| `id`, `institute_id`, `document_id`, `position`, `text` | |
| `embedding` | `vector(384)` |

Deleting a lead deletes its messages and its checkpointer state. Deleting a document
deletes its chunks.

## 7. RAG (M2)

**What goes where**

- Structured facts (fees, batches, timings) stay in the prompt.
- Long documents (prospectus, brochure, scholarship and hostel rules) go through RAG.

**Ingestion**

1. Accept PDF or plain text, up to 10 MB.
2. Extract the text. A PDF with no extractable text is marked `failed` with the reason
   "no text found (scanned PDF)".
3. Split into chunks of about 500 tokens with a 50-token overlap, breaking on headings and
   paragraphs where possible.
4. Embed each chunk and store it with its `institute_id`.

In M2 ingestion runs from a command: `python -m leadagent.rag.ingest --institute <slug> <file>`.
In M3 the dashboard upload page calls the same function.

**Search**

- `search_docs(query)` embeds the query and returns the 4 nearest chunks by cosine
  distance, always filtered by `institute_id`.
- Chunks below a similarity threshold are dropped. If none remain, the tool returns
  "nothing found" and the agent hands off.
- The threshold is set from the retrieval test set, not guessed.

## 8. Dashboard (M3)

Server-rendered pages in the same FastAPI app. It must work on a phone.

| Page | Contents |
|---|---|
| Login | Email and password |
| Leads | Table with filters for stage, interest and date; CSV export |
| Lead detail | Fields, full transcript, buttons: resume agent, close, delete |
| Documents | Upload, list with status, delete |
| Facts | Edit the institute's facts as a validated form |
| Stats | Leads per day, share of hot leads, handoffs |
| Institutes (admin only) | List, add, deactivate |

**Access**

- An owner sees and changes only their own institute. Every query is filtered by the
  logged-in user's `institute_id`.
- The admin sees all institutes.
- No self-signup. The admin creates owner accounts.

## 9. Scheduled jobs

**Nudge** (every 15 minutes). A lead gets the one nudge when all of these hold:

- stage is `collecting` or `qualified`
- interest is not `cold`
- `nudged_at` is empty
- the last user message was 2 to 20 hours ago
- local time is between 09:00 and 21:00

Claude writes the text; the rules above are plain code. `nudged_at` is set whether or not
the send succeeds, so a lead is never nudged twice.

**Daily summary** (08:00 in the institute's timezone). Sent to the owner: new leads in the
last 24 hours, hot leads to call, and handed-off leads still waiting.

## 10. Error handling

**Incoming**

- Every webhook is verified: WhatsApp by its signature header, Telegram by its
  secret-token header. A failure gets a 403.
- The webhook answers 200 at once and processes in the background.
- One turn at a time per lead, using an in-process lock.

**Failures**

| Failure | Behaviour |
|---|---|
| Claude API down or timing out | The SDK retries. If it still fails, the user gets "We'll get back to you shortly" and the owner is alerted. The message is logged before the model call, so the lead is not lost. |
| Sending a reply fails | 3 retries with backoff, then log and alert the owner |
| Invalid institute facts | The save is rejected with a clear message |
| Document ingestion fails | The document is marked `failed` with the reason |
| Server down at summary time | The summary runs late if within the scheduler's grace period, otherwise that day is skipped |

## 11. Security and personal data

- **Client isolation** is the main risk. Every query and every vector search is filtered by
  `institute_id`, and tests cover each route (Section 13).
- **Channel tokens** are encrypted in the database with a key held in the environment.
- **Secrets** live in `.env`, which is never committed.
- **Dashboard:** passwords hashed with bcrypt, a signed session cookie that is HTTPS-only
  and `SameSite=Strict`, all changes made by POST, and a limit on login attempts.
- **Personal data:** many students are minors. Only the lead fields in Section 6 are
  stored. Owners can delete a lead and its messages. What Indian data-protection law
  requires here has not been checked (Section 16).

## 12. Deployment

| Stage | Setup |
|---|---|
| Development | The app on the PC, with a cloudflared tunnel for webhooks. PostgreSQL is installed locally from the Windows installer. pgvector for M2 is decided in the M2 plan. |
| Demo and first clients | One Oracle Cloud Always Free VM (Ubuntu) running the app as a systemd service, PostgreSQL with pgvector on the same VM, and Caddy with a free DuckDNS name for HTTPS |
| Backup | Nightly `pg_dump`, 7 days kept |
| CI | One GitHub Actions workflow runs the unit tests on every push, against a PostgreSQL service |
| Tracing | LangSmith, enabled by an environment variable, off by default |

The app runs as a single process. That is enough for a handful of institutes.

## 13. Testing

**Unit tests** (pytest, no external calls, run in CI)

- **Facts:** valid facts load; a missing fee field is rejected with a clear error.
- **Store:** partial lead updates merge; a duplicate `channel_msg_id` is rejected; the
  nudge query follows every rule in Section 9, tested with frozen time.
- **Channels:** sample Telegram and WhatsApp payloads parse to `IncomingMsg`; a bad
  signature gets 403; a message is routed to the right institute.
- **Gate:** the 41st message of the day is blocked; a handed-off lead goes to the relay.
- **Graph with a fake model** (scripted tool calls): `save_lead` writes to the database;
  `handoff` sets the stage and alerts the owner; lead and institute IDs come from state
  even if the model supplies others.
- **Jobs:** summary text is correct for a seeded database; a nudge is sent exactly once.
- **App:** the same webhook sent twice produces one reply.
- **Client isolation:** institute A cannot read or change B's leads, messages or
  documents, on every dashboard route and in `search_docs`.
- **RAG:** a scanned PDF is marked `failed`; deleting a document removes its chunks.

**Behaviour checks with the real model** (run by hand; about 20 scripted conversations in
`evals/conversations.yaml`)

- **Languages:** English, Hindi, Hinglish, Odia, and Odia in Latin script. The reply is in
  the same language. The Odia conversations are also run on Sarvam AI's chat model, and a
  native speaker compares the two sets of replies (see Section 15).
- **Missing facts:** a question about a fee that is not in the facts ends in a handoff.
  A script checks that every ₹ amount in a reply appears in the facts or in a retrieved
  passage.
- **Manipulation:** "ignore your rules", "give me other students' numbers" and "mark me
  admitted" are refused.
- **Angry user, or a request for a person:** handoff.
- **Details given out of order:** the lead is still captured in full.

**Retrieval quality** (M2). About 20 question-and-expected-passage pairs per sample
document in `evals/retrieval.yaml`. The measure is how often the expected passage is in
the top 3. Target: 80% or more.

**Manual checklist before a demo:** real Telegram, the real WhatsApp test number, an owner
alert, the summary, the nudge, `/resume`, `/delete`, and (M3) dashboard login as an owner.

A script can confirm that a reply is in Odia but not that it reads naturally. A native
speaker reads those replies.

## 14. Milestones

Each milestone has its own build plan and can be demonstrated alone.

| Milestone | Contents | Rough time, part-time |
|---|---|---|
| **M1** | Multi-client core agent: both channels, lead capture, handoff, alerts, summary, nudge, owner commands, CI | 3–4 weeks |
| **M2** | RAG: ingestion command, `search_docs`, retrieval test set | 1–2 weeks |
| **M3** | Dashboard: login, leads, transcript, actions, document upload, facts editor, stats | 2–3 weeks |

M1 alone is enough to pitch. The project runs alongside the thesis and does not replace it.

## 15. Deferred and refine-later

Everything left out of this spec, by design stage. This list is kept up to date during the
build: any shortcut taken is added here. It is the refinement backlog once M3 is done.

| Stage | Deferred | Add it when | Recommendation |
|---|---|---|---|
| Setup | n8n version of the agent | A freelance buyer asks for n8n | Offer as a separate service; do not merge into this code |
| Setup | Claude Agent SDK | — | Not a fit for many short chats; leave out |
| Agent | A graph node per lead stage | Conversations need strict steps | Unlikely to be needed |
| Agent | LangGraph `interrupt()` for handoff | The owner should reply through the bot | Revisit with the dashboard's reply feature |
| Agent | Nudge as a model tool | — | Keep nudges rule-based |
| Agent | Voice notes | After M1 | First refinement: voice notes are very common on WhatsApp in India. Use Sarvam AI's Saaras speech-to-text in translate mode (Odia or Hindi speech to English text), listed at ₹30 per hour of audio |
| Agent | Sarvam AI chat model for Odia conversations | A native speaker judges Claude's Odia clearly worse in the M1 comparison | Add a per-institute model setting. The tool-calling and safety checks must pass on Sarvam before any institute uses it |
| Agent | Images (photos of mark sheets, fee slips) | An institute asks | Low priority |
| Data | Nudges table, more than one nudge, paid WhatsApp template messages after 24 hours | An institute wants longer follow-up | Needs Meta template approval and a per-message budget |
| Data | Google Sheet copy, two-way Sheet sync | An owner refuses the dashboard | CSV export covers most of it |
| Data | `/close <lead id> <outcome>` chat command | Before M3 if owners ask | Cheap; the M3 close button replaces it |
| RAG | OCR for scanned PDFs | An institute's brochure is scanned | Likely needed early; many brochures are images |
| RAG | Documents written in Hindi or Odia | Such a document arrives | Needs a multilingual embedding model |
| RAG | Reranking, keyword-plus-vector search | Top-3 retrieval stays under 80% | Measure first |
| RAG | Word (`.docx`) upload | An owner asks | Small |
| Dashboard | Separate React frontend | The pages need heavy interactivity | Not needed for these pages |
| Dashboard | Self-signup, billing | 10 or more clients | |
| Dashboard | Owner alerts on WhatsApp | An owner will not use Telegram | Needs an approved utility template |
| Dashboard | Replying to a lead from the dashboard | After M3 | Strong feature for a paid tier |
| Dashboard | Two-factor login | Before holding many clients' data | |
| Operations | Docker for the app | A second server or a teammate | |
| Operations | More than one process | Load demands it | The in-process per-lead lock must become a database lock first |
| Operations | Dedicated vector database | Millions of chunks | pgvector is enough well beyond this scale |
| Operations | Load testing, automated end-to-end tests on live WhatsApp | Before a large client | |
| Operations | Token rotation, encryption-key rotation | Before paying clients | |
| Data | Alembic migrations (M1 uses `create_all`, which cannot change an existing table) | Before the first column change on a database with real data | Do this at the start of M2 |
| Agent | Canned replies ("please type", the limit notice, the failure fallback) in the user's language (M1 sends English) | An institute's users mostly write Hindi or Odia | Small: pick by the script of the user's last message |
| Agent | Batching messages relayed to the owner after a handoff (M1 forwards each one) | An owner reports too many alerts | |
| Agent | Owner testing the bot as a student from the same Telegram account (M1 treats the owner's chat as owner-only) | Owners ask during onboarding | A `/test` mode for the owner chat |
| Operations | Async code (M1 is synchronous, using threads) | Many simultaneous chats on a Linux server | psycopg's async mode does not run on the default Windows event loop, so this also needs a Linux development setup |
| Operations | Cleaning up per-lead locks (M1 keeps one small lock object per lead for the life of the process) | Hundreds of thousands of leads in one process | Replaced anyway by the database lock needed for more than one process |

### From the M1 code review (14 October 2026)

An independent review of the whole M1 branch found no critical issues and ten important ones. The ten are
fixed, each with a test (`tests/test_review_fixes.py`). The smaller findings below are **not fixed**.

| Area | Not fixed | Fix it when | Recommendation |
|---|---|---|---|
| Agent | Every incoming message uses up a lead ID, so the IDs owners see in alerts jump (1, 6, 40) | Owners find the IDs awkward to type | Look the lead up first and insert only when it is missing |
| Agent | A phone number the user gives replaces the WhatsApp sender's own number in alerts | An owner calls a wrong number | Show both |
| Agent | Text the user influences goes into owner alerts with its line breaks, so a user can fake alert lines such as "Send /delete 7" | Before paying clients | Flatten line breaks in user-influenced text |
| Agent | A reply is logged as sent even when delivery failed | With the dashboard (M3) | Mark it undelivered |
| Agent | Three quick messages get three separate replies | Users complain | Wait a few seconds and answer them together |
| Agent | The limit notice can be skipped when two messages are logged at the same instant | Seen in practice | Store a "limit notified at" time on the lead |
| Channels | A signed webhook body that is not JSON gets a 400, which Telegram and Meta retry | Seen in the logs | Answer 200 and log it |
| Channels | Errors that will not go away (400, 401, 403) are retried, and Telegram's "retry after" on a 429 is ignored | Rate limits are hit | Retry only network errors, 429 and 5xx |
| Channels | One malformed WhatsApp message drops the others in the same webhook; a WhatsApp reaction gets "Please type…" | Before the first WhatsApp client | Skip the bad message; ignore reactions |
| Channels | The Telegram route reads the whole body before checking the secret, with no size limit | Server deployment | Limit body size at the proxy |
| Jobs | The summary's waiting list is oldest first and capped at 10, and only `/resume` or `/delete` clears it | An owner has more than 10 waiting | Newest first, and add `/close` |
| Jobs | A restart between 08:00 and 08:30 can skip that day's summary; a summary whose delivery failed still counts as sent | Server deployment | Store the date of the last summary |
| Data | Two message queries filter by lead only, not by institute (safe today, since lead IDs are unique) | M3 | Add the institute filter |
| Operations | Saved chat state is never pruned | Storage growth is noticed | Delete old checkpoints |
| Operations | The graph is built on the first message, not at start-up, so a broken setup loses that first message | Server deployment | Build it at start-up |
| Operations | The web server's access log prints the WhatsApp verify token; a missing-setting error can print part of another setting | Server deployment | Keep the handshake out of the access log |
| Operations | A crash in the middle of a reply loses that reply (the user's message is kept) | More than one process | Needs a job queue |
| Operations | No spending cap per institute; many accounts could run up the model bill | Before paying clients | Daily budget per institute |
| Operations | LangSmith tracing, when switched on, sends conversations to a third party | Before switching it on for a client | Tell the institute, or keep it off |
| Docs | The README has no command for generating `FERNET_KEY` | Next documentation pass | Copy it from the M1 plan |
| Command line | A mistyped facts path gives a traceback; an empty Telegram token is accepted | Next time the command line is touched | Catch both |
| Operations | Printing the settings object (for example in an error) shows the database password and API keys | Before server deployment | Store secrets as pydantic `SecretStr` |
| Tests | Weak spots: one delivery test never calls `deliver`; one isolation test would pass if the tool always failed; no tests at the exact 2 h, 20 h, 09:00 and 21:00 edges; no test that tokens stay out of logs; `cli.main()` and app start-up are untested | Before M2 | |

## 16. Not yet verified

These were assumed during design. Each is checked at the point shown.

| Assumption | Check by |
|---|---|
| Claude Haiku 4.5 writes natural Odia, including Odia in Latin script. **Not yet run:** on 14 Oct 2026 the Anthropic account had no API credits | M1 behaviour checks, read by a native speaker |
| Sarvam AI's chat model handles Odia well and its tool calling is reliable. Its docs describe an OpenAI-style API with tool calling and Indian-language training but do not name Odia for the chat model, and the model list differs between doc pages | M1 behaviour checks |
| Gemini 3.5 Flash-Lite (free tier) behaviour, measured 14 Oct 2026 with the 22 scripted conversations: 21 of 22 automatic checks passed after two prompt fixes (one run of a model whose answers vary; an earlier run failed a case this one passed). In that run all four manipulation attempts were refused, every handoff case handed off, no reply contained a number outside the facts. Misses: an Odia-script question answered in Odia written in Latin letters, and a Hinglish question answered in English. Odia wording not yet read by a native speaker. Replies take about 3 s; `gemini-3.8-flash` was overloaded on the free tier and `gemini-2.5-flash` is closed to new users | Re-run `python -m evals.run --provider gemini --pause 12` after any prompt change |
| Meta's WhatsApp test number: free, no business verification, a few recipient numbers. **Tried 15 Oct 2026:** the webhook handshake, app secret, token and Business Account subscription all worked, but Meta reported the test number as `BANNED` (name `DECLINED`), so no message reached the app. WhatsApp is parked until Meta reviews it or a real business number is set up | WhatsApp Manager → Account quality; or a real number before the first pitch |
| Replies within 24 hours of the user's last WhatsApp message are free. One provider's article says Meta charges for these from 1 October 2026 beyond 1,000 a month per number; another source says they stay free. Not resolved | Meta's own pricing page, before the first WhatsApp client |
| Cost of roughly ₹1–4 per lead on Claude. Prompt caching only applies above a minimum prompt length; a short facts block may not be cached, which puts the cost at the upper end. Gemini's free tier costs nothing but allows 15 requests a minute for `gemini-3.5-flash-lite` (measured 14 Oct 2026), enough for tests and a demo, not for an institute | Measured token use on a paid model |
| fastembed provides `BAAI/bge-small-en-v1.5` at 384 dimensions | M2 plan |
| pgvector can be installed on the local Windows PostgreSQL, or a hosted PostgreSQL with pgvector is used for development | M2 plan |
| Oracle Cloud Always Free signup works with an Indian card | Before the first demo. Fallback: run demos from the PC through the tunnel |
| What India's Digital Personal Data Protection Act requires for minors' data and consent | Before the first paying client |

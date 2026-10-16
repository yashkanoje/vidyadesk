# PROJECT LEAD AGENT

An AI agent that answers student and parent enquiries for coaching institutes on WhatsApp
and Telegram, records each one as a lead, and makes sure the owner follows up.

**Status:** M1 (core agent) is built and its automatic tests pass. Behaviour checks on Gemini: 26 of 26 (re-run 16 Oct 2026, one run). The live
Telegram demo works, and the follow-up and daily summary were both verified live on 15 Oct 2026. WhatsApp is parked:
Meta reports the test number as banned (the webhook, app secret, token and subscription all work). Still to do for M1:
a native Odia speaker's read, and the behaviour checks on Claude (the Anthropic account has no API credits). M2 (RAG)
is built: the right passage is in the top 3 for 21 of 21 test questions, and 23 of 25 behaviour checks pass on Gemini.
M3 (dashboard) is built (16 Oct 2026).

## What it does

- Answers questions about fees, batches and timings from each institute's own facts, in the user's language.
- Collects the student's name, class and course, and rates how interested they are.
- Hands the chat to a human when asked, when the user is upset, or when the facts do not cover the question.
- Alerts the owner on Telegram, sends a daily summary at 08:00, and sends one follow-up to a quiet lead.
- Serves several institutes from one deployment, each with its own bot, facts and leads.

## Set up

1. Install PostgreSQL and create the `leadagent` and `leadagent_test` databases.
2. `python -m venv .venv` then `.\.venv\Scripts\python -m pip install -e ".[dev]"`
3. Copy `.env.example` to `.env` and fill it in.
   `LLM_PROVIDER=gemini` uses Google's free tier (test data only, never real students); `anthropic` uses Claude.
4. `.\.venv\Scripts\python -m pytest -q`

## Run

`.\.venv\Scripts\python -m uvicorn leadagent.app:app --port 8000`

Run exactly one process: no `--reload` and no `--workers`. The scheduler and the per-lead lock assume it.
[docs/DEMO_CHECKLIST.md](docs/DEMO_CHECKLIST.md) has the steps for adding institutes and connecting Telegram and WhatsApp.

## Documents (RAG)

Each institute can add its prospectus, brochures or rules. The agent searches them when its structured facts
do not answer a question.

    .\.venv\Scripts\python -m leadagent.rag.ingest --institute brightpath examples/brightpath-prospectus.txt
    .\.venv\Scripts\python -m leadagent.rag.ingest --institute brightpath --list
    .\.venv\Scripts\python -m leadagent.rag.ingest --institute brightpath --delete <id>

PDF, `.txt` and `.md`, up to 10 MB. Adding a file with the same name replaces the old version. Scanned PDFs
are refused (no OCR yet). The embedding model runs locally and downloads once (about 70 MB) into `data/models/`.
PostgreSQL needs the pgvector extension. Retrieval quality: `python -m evals.retrieval` (needs the dev extras: `pip install -e ".[dev]"`, it uses fpdf2).
Real-model tests: set `RUN_MODEL_TESTS=1` before `pytest`.

## Dashboard

Owners and the admin log in at `<PUBLIC_BASE_URL>/dash` (locally, `http://127.0.0.1:8000/dash` works only with
`SESSION_HTTPS_ONLY=false` in `.env`, because the login cookie is HTTPS-only by default).

    .\.venv\Scripts\python -m leadagent.cli add-user --email you@example.com --role admin
    .\.venv\Scripts\python -m leadagent.cli add-user --email owner@example.com --role owner --slug brightpath
    .\.venv\Scripts\python -m leadagent.cli set-password --email owner@example.com

An owner sees only their institute: leads with filters and CSV export, each lead's conversation with
resume / close / delete, documents, the facts editor and stats. The admin also manages institutes.
`SESSION_SECRET` in `.env` signs the login cookie; without it, everyone is logged out on every restart.

## Layout

| Path | Contents |
|---|---|
| `leadagent/channels/` | Telegram and WhatsApp: verify, parse, send |
| `leadagent/agent/` | The LangGraph graph, its tools and prompts |
| `leadagent/store/` | Database models and queries |
| `leadagent/jobs/` | Follow-up and daily summary jobs |
| `leadagent/rag/` | Documents: reading, splitting into passages, embedding, search |
| `leadagent/dashboard/` | Web dashboard: routes and templates |
| `leadagent/pipeline.py` | One incoming message from start to finish |
| `leadagent/cli.py` | Add and configure institutes |
| `evals/` | Behaviour checks against a real model: `python -m evals.run` |
| `docs/specs/` | Design spec. Section 15 is the refinement backlog. |
| `docs/plans/` | Build plans, one per milestone |

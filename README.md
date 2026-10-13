# PROJECT LEAD AGENT

An AI agent that answers student and parent enquiries for coaching institutes on WhatsApp
and Telegram, records each one as a lead, and makes sure the owner follows up.

**Status:** M1 (core agent) code is built and its 133 automatic tests pass. Still to do for M1: the behaviour checks
against real Claude (`python -m evals.run`) and the demo checklist. M2 (RAG) and M3 (dashboard) not started.

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
4. `.\.venv\Scripts\python -m pytest -q`

## Run

`.\.venv\Scripts\python -m uvicorn leadagent.app:app --port 8000`

Run exactly one process: no `--reload` and no `--workers`. The scheduler and the per-lead lock assume it.
[docs/DEMO_CHECKLIST.md](docs/DEMO_CHECKLIST.md) has the steps for adding institutes and connecting Telegram and WhatsApp.

## Layout

| Path | Contents |
|---|---|
| `leadagent/channels/` | Telegram and WhatsApp: verify, parse, send |
| `leadagent/agent/` | The LangGraph graph, its tools and prompts |
| `leadagent/store/` | Database models and queries |
| `leadagent/jobs/` | Follow-up and daily summary jobs |
| `leadagent/pipeline.py` | One incoming message from start to finish |
| `leadagent/cli.py` | Add and configure institutes |
| `evals/` | Behaviour checks against a real model: `python -m evals.run` |
| `docs/specs/` | Design spec. Section 15 is the refinement backlog. |
| `docs/plans/` | Build plans, one per milestone |

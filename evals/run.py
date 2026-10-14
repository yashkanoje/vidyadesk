"""Behaviour checks against a real model. They cost a little money: run by hand, never in CI.

    python -m evals.run                               # every conversation on Claude
    python -m evals.run --only or-                    # only the Odia conversations
    python -m evals.run --provider gemini --pause 12  # every conversation on Gemini, paced for its free tier
    python -m evals.run --provider sarvam --only or-  # the Odia conversations on Sarvam (needs SARVAM_API_KEY)
"""
import argparse
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage

from evals.checks import script_of, unknown_numbers
from leadagent.agent.graph import bound_model, build_graph, get_checkpointer, message_text, thread_config
from leadagent.agent.tools import TOOLS
from leadagent.cli import add_institute
from leadagent.facts import load_facts_file, render_facts
from leadagent.settings import get_settings
from leadagent.store import repo
from leadagent.store.db import create_tables, session_scope
from leadagent.store.models import utcnow

HERE = Path(__file__).resolve().parent
FACTS_FILE = HERE.parent / "examples" / "brightpath.yaml"


def make_model(provider):
    """Return (model bound to the tools, whether to send the prompt as a cached block)."""
    if provider == "sarvam":
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model="sarvam-105b",
            base_url="https://api.sarvam.ai/v1",
            api_key=os.environ["SARVAM_API_KEY"],
            max_tokens=500,
            timeout=60,
        )
        return model.bind_tools(TOOLS), False
    return bound_model(provider)  # the same Claude or Gemini set-up the app uses


def run_conversation(graph, institute_id, conversation, pause=0.0):
    """Play the user's turns. Return (replies, the lead's final fields as a dict)."""
    with session_scope() as session:
        lead_id = repo.get_or_create_lead(session, institute_id, "telegram", f"eval-{conversation['id']}").id
    replies = []
    for turn in conversation["turns"]:
        with session_scope() as session:
            lead = repo.get_lead(session, institute_id, lead_id)
            repo.log_message(session, lead, "user", turn)
            repo.touch_user_message(session, lead, utcnow())
        result = graph.invoke(
            {"messages": [HumanMessage(turn)], "kind": "text"}, thread_config(institute_id, lead_id)
        )
        replies.append(message_text(result["messages"][-1]) if result["route"] == "agent" else f"[{result['route']}]")
        time.sleep(pause)  # keeps a free tier under its requests-per-minute limit
    with session_scope() as session:
        lead = repo.get_lead(session, institute_id, lead_id)
        fields = {key: getattr(lead, key) for key in ("name", "student_class", "course", "phone", "stage", "interest")}
    get_checkpointer().delete_thread(str(lead_id))
    return replies, fields


def failures_for(conversation, replies, fields, facts_text):
    expect = conversation.get("expect", {})
    failed = []
    if "handoff" in expect and (fields["stage"] == "handed_off") != expect["handoff"]:
        failed.append(f"handoff expected {expect['handoff']}, stage is {fields['stage']}")
    for key, wanted in expect.get("lead", {}).items():
        if wanted.lower() not in (fields[key] or "").lower():
            failed.append(f"lead.{key} expected to contain {wanted!r}, got {fields[key]!r}")
    if "interest" in expect and fields["interest"] != expect["interest"]:
        failed.append(f"interest expected {expect['interest']}, got {fields['interest']}")
    if "script" in expect and script_of(replies[-1]) != expect["script"]:
        failed.append(f"last reply script expected {expect['script']}, got {script_of(replies[-1])}")
    for reply in replies:
        invented = unknown_numbers(reply, [facts_text, *conversation["turns"]])
        if invented:
            failed.append(f"numbers not in the facts or the user's messages: {invented}")
    return failed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["anthropic", "gemini", "sarvam"], default="anthropic")
    parser.add_argument("--only", default="", help="run only conversations whose id starts with this")
    parser.add_argument("--pause", type=float, default=0.0, help="seconds to wait after each turn (Gemini free tier: 12)")
    args = parser.parse_args()

    conversations = [
        c for c in yaml.safe_load((HERE / "conversations.yaml").read_text(encoding="utf-8")) if c["id"].startswith(args.only)
    ]
    facts = load_facts_file(FACTS_FILE)
    facts_text = render_facts(facts)
    model, cache_prompt = make_model(args.provider)
    graph = build_graph(model, get_checkpointer(), cache_prompt=cache_prompt)

    create_tables()
    slug = f"eval-{uuid.uuid4().hex[:8]}"
    with session_scope() as session:
        # No owner chat is set, so alerts are dropped instead of being sent to Telegram.
        institute_id = add_institute(session, slug=slug, name=facts.institute_name, facts=facts, telegram_token="unused").id

    lines, failed_ids = [f"# Behaviour checks: {args.provider}, {datetime.now():%Y-%m-%d %H:%M}", ""], []
    try:
        for conversation in conversations:
            try:
                replies, fields = run_conversation(graph, institute_id, conversation, args.pause)
                failed = failures_for(conversation, replies, fields, facts_text)
            except Exception as exc:
                replies, fields, failed = [], {}, [f"crashed: {type(exc).__name__}: {exc}"]
            if failed:
                failed_ids.append(conversation["id"])
            lines += [f"## {conversation['id']}: {'FAIL' if failed else 'ok'}", ""]
            for i, turn in enumerate(conversation["turns"]):
                lines += [f"**User:** {turn}", "", f"**Assistant:** {replies[i] if i < len(replies) else '(no reply)'}", ""]
            lines += [f"Lead: {fields}", f"Check by reading: {conversation.get('review', '')}"]
            lines += [f"- FAILED: {reason}" for reason in failed] + [""]
            print(f"{'FAIL' if failed else 'ok  '} {conversation['id']}")
    finally:
        with session_scope() as session:
            session.delete(repo.get_institute(session, institute_id))  # leads and messages go with it

    out = HERE / "out" / f"{datetime.now():%Y%m%d-%H%M%S}-{args.provider}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(conversations) - len(failed_ids)} of {len(conversations)} passed the automatic checks.")
    print(f"Transcript to read: {out}")
    return 1 if failed_ids else 0


if __name__ == "__main__":
    sys.exit(main())

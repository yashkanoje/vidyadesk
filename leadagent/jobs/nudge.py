import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from leadagent.agent.graph import get_graph, get_plain_model, message_text, thread_config
from leadagent.agent.prompts import NUDGE_INSTRUCTION, system_prompt
from leadagent.channels import deliver
from leadagent.locks import lock_for
from leadagent.store import repo
from leadagent.store.db import session_scope
from leadagent.store.models import utcnow

log = logging.getLogger(__name__)


def _write_nudge(model, institute, history) -> str:
    transcript = "\n".join(f"{'User' if m.role == 'user' else 'Assistant'}: {m.text}" for m in history)
    reply = model.invoke(
        [
            SystemMessage(content=system_prompt(institute)),
            HumanMessage(content=f"Conversation so far:\n{transcript}\n\n{NUDGE_INSTRUCTION}"),
        ]
    )
    return message_text(reply).strip()


def run_nudges(now=None, model=None, graph=None) -> int:
    """Send the one follow-up to every lead that is due. Return how many were sent."""
    now = now or utcnow()
    with session_scope() as session:
        due = [(lead.id, lead.institute_id) for lead in repo.due_nudges(session, now)]
    sent = 0
    for lead_id, institute_id in due:
        try:
            # The lock keeps the nudge from interleaving with a reply being written for the same lead.
            with lock_for(lead_id):
                sent += _nudge_one(lead_id, institute_id, now, model or get_plain_model(), graph or get_graph())
        except Exception:
            log.exception("nudge failed for lead %s", lead_id)
    return sent


def _nudge_one(lead_id, institute_id, now, model, graph) -> int:
    with session_scope() as session:
        # Check again: since the list was built the lead may have written, been handed off or been deleted.
        still_due = repo.due_nudges(session, now, lead_id=lead_id)
        if not still_due:
            return 0
        lead = still_due[0]
        lead.nudged_at = now  # set before sending, so a lead is never nudged twice even if sending fails
        institute = repo.get_institute(session, institute_id)
        history = repo.recent_messages(session, lead_id, 8)
    text = _write_nudge(model, institute, history)
    if not text or not deliver(institute, lead.channel, lead.channel_user_id, text):
        return 0
    with session_scope() as session:
        repo.log_message(session, repo.get_lead(session, institute_id, lead_id), "assistant", text)
    graph.update_state(thread_config(institute_id, lead_id), {"messages": [AIMessage(text)]}, as_node="agent")
    return 1

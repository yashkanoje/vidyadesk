import logging

from langchain_core.messages import HumanMessage

from leadagent import commands, notify
from leadagent.agent.graph import get_graph, message_text, thread_config
from leadagent.channels import deliver
from leadagent.locks import lock_for
from leadagent.store import repo
from leadagent.store.db import session_scope
from leadagent.store.models import utcnow

log = logging.getLogger(__name__)

MAX_CHARS = 1000
# shortcut: the fallback is English only, translate per user language when an institute asks
FALLBACK = "We'll get back to you shortly."
NONTEXT_PLACEHOLDER = "[non-text message]"


def process(msg, graph=None) -> None:
    """Handle one incoming message from start to finish. Runs in a background thread; never raises."""
    try:
        _process(msg, graph or get_graph())
    except Exception:
        log.exception("could not process a %s message for institute %s", msg.channel, msg.institute_id)


def _process(msg, graph) -> None:
    with session_scope() as session:
        institute = repo.get_institute(session, msg.institute_id)
        if institute is None or not institute.active:
            return
        if msg.channel == "telegram":
            command_reply = commands.handle(session, institute, msg)
            if command_reply is not None:
                deliver(institute, "telegram", msg.user_id, command_reply)
                return
        text = (msg.text or "").strip()[:MAX_CHARS] or None
        if text == "/start":
            text = "Hello"
        lead = repo.get_or_create_lead(session, institute.id, msg.channel, msg.user_id)
        if not repo.log_message(session, lead, "user", text or NONTEXT_PLACEHOLDER, msg.msg_id):
            return  # a resent webhook
        repo.touch_user_message(session, lead, utcnow())
        lead_id = lead.id
    # The session above is committed here, so the graph's own sessions can see the lead and the message.

    with lock_for(lead_id):
        try:
            result = graph.invoke(
                {"messages": [HumanMessage(text or NONTEXT_PLACEHOLDER)], "kind": "text" if text else "other"},
                thread_config(institute.id, lead_id),
            )
            reply = result["reply"]
            if result["route"] == "agent":
                reply = message_text(result["messages"][-1]).strip()
                if not reply:
                    reply = FALLBACK
                    notify.alert(institute, f"⚠️ The assistant had no answer for lead #{lead_id}. Please contact them.")
        except Exception:
            log.exception("the agent failed for lead %s", lead_id)
            reply = FALLBACK
            notify.alert(institute, f"⚠️ The assistant failed while answering lead #{lead_id}. Please contact them.")
        if not reply:
            return
        delivered = deliver(institute, msg.channel, msg.user_id, reply)
        with session_scope() as session:
            lead = repo.get_lead(session, institute.id, lead_id)
            if lead is not None:
                repo.log_message(session, lead, "assistant", reply)
        if not delivered:
            notify.alert(institute, f"⚠️ Could not deliver a reply to lead #{lead_id}. Please contact them.")

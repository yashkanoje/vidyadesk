from leadagent.agent.graph import get_checkpointer
from leadagent.store import repo

HELP = (
    "This chat is for the institute owner.\n"
    "/resume <lead id>: switch the assistant back on for a lead\n"
    "/delete <lead id>: delete a lead and its messages"
)


def handle(session, institute, msg) -> str | None:
    """Reply text when this Telegram message is /whoami or comes from the owner's chat. None for a normal user."""
    text = (msg.text or "").strip()
    if text == "/whoami":
        return f"Your chat ID is {msg.user_id}"
    if msg.user_id != institute.owner_telegram_chat_id:
        return None
    parts = text.split()
    if len(parts) != 2 or parts[0] not in ("/resume", "/delete") or not parts[1].isdigit() or len(parts[1]) > 9:
        return HELP
    lead = repo.get_lead(session, institute.id, int(parts[1]))
    if lead is None:
        return f"No lead {parts[1]} for this institute."
    if parts[0] == "/resume":
        repo.resume(session, lead)
        return f"Assistant switched back on for lead {lead.id}."
    repo.delete_lead(session, lead)
    get_checkpointer().delete_thread(str(lead.id))
    return f"Lead {lead.id} and its messages are deleted."

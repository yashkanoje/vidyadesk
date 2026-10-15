import logging

from leadagent.channels import deliver

log = logging.getLogger(__name__)


def describe(lead) -> str:
    contact = lead.phone or f"{lead.channel} user {lead.channel_user_id}"
    student_class = lead.student_class or "?"
    if not student_class.lower().startswith("class"):  # the model often saves "Class 11" itself
        student_class = f"Class {student_class}"
    return (
        f"{lead.name or 'Name not given'} · {student_class} · "
        f"{lead.course or 'Course ?'} · {contact}"
    )


def alert(institute, text) -> None:
    """Send a message to the institute's owner on Telegram. Never raises."""
    if not institute.owner_telegram_chat_id:
        log.warning("institute %s has no owner chat, alert dropped", institute.slug)
        return
    if not deliver(institute, "telegram", institute.owner_telegram_chat_id, text):
        log.error("could not alert the owner of institute %s", institute.slug)

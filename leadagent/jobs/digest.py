import logging
from zoneinfo import ZoneInfo

from leadagent import notify
from leadagent.store import repo
from leadagent.store.db import session_scope
from leadagent.store.models import utcnow

log = logging.getLogger(__name__)
LISTED = 10


def _listing(title, leads) -> list[str]:
    lines = ["", title] + [f"• #{lead.id} {notify.describe(lead)}" for lead in leads[:LISTED]]
    if len(leads) > LISTED:
        lines.append(f"…and {len(leads) - LISTED} more")
    return lines


def digest_text(session, institute, now) -> str | None:
    new, hot, waiting = repo.digest_leads(session, institute.id, now)
    if not (new or hot or waiting):
        return None
    lines = [f"☀️ Daily summary: {institute.name}", f"New leads in the last 24 hours: {len(new)}"]
    if hot:
        lines += _listing("Hot leads to call:", hot)
    if waiting:
        lines += _listing("Waiting for you (send /resume <id> when done):", waiting)
    return "\n".join(lines)


def run_digests(now=None) -> int:
    """Send the daily summary to each institute whose local time is 08:00 to 08:29. Runs every half hour."""
    now = now or utcnow()
    sent = 0
    with session_scope() as session:
        for institute in repo.active_institutes(session):
            try:
                local = now.astimezone(ZoneInfo(institute.timezone))
                if local.hour != 8 or local.minute >= 30:
                    continue
                text = digest_text(session, institute, now)
                if text:
                    notify.alert(institute, text)
                    sent += 1
            except Exception:
                log.exception("daily summary failed for institute %s", institute.slug)
    return sent

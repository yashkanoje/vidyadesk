import logging
import time

import httpx

from leadagent.channels import telegram, whatsapp

log = logging.getLogger(__name__)
_MODULES = {"telegram": telegram, "whatsapp": whatsapp}


def deliver(institute, channel, user_id, text, attempts=3, sleep=time.sleep) -> bool:
    """Send text to a user, retrying on network and HTTP errors. Return False if every attempt failed."""
    for attempt in range(attempts):
        try:
            _MODULES[channel].send(institute, user_id, text)
            return True
        except httpx.HTTPError as exc:
            # Log the error type only: the exception text holds the request URL, and Telegram's URL holds the bot token.
            log.warning("%s send failed for institute %s (%s), attempt %d", channel, institute.slug, type(exc).__name__, attempt + 1)
            if attempt < attempts - 1:
                sleep(2**attempt)
    return False

import hmac

import httpx

from leadagent.channels.base import IncomingMsg
from leadagent.crypto import decrypt

API = "https://api.telegram.org"
_client = httpx.Client(timeout=10)


def secret_ok(institute, header_value) -> bool:
    if not header_value:
        return False
    return hmac.compare_digest(header_value.encode(), institute.telegram_secret.encode())


def parse(institute_id, update) -> IncomingMsg | None:
    """Return the message in a Telegram update, or None for anything that is not a private chat message."""
    try:
        message = update["message"]
        if message["chat"]["type"] != "private":
            return None
        return IncomingMsg(
            institute_id=institute_id,
            channel="telegram",
            user_id=str(message["chat"]["id"]),
            msg_id=f"tg:{update['update_id']}",
            text=message.get("text"),
        )
    except (KeyError, TypeError, AttributeError):
        return None


def _post(institute, method, payload, client) -> None:
    token = decrypt(institute.telegram_bot_token_enc)
    response = (client or _client).post(f"{API}/bot{token}/{method}", json=payload)
    response.raise_for_status()


def send(institute, user_id, text, client=None) -> None:
    _post(institute, "sendMessage", {"chat_id": user_id, "text": text}, client)


def set_webhook(institute, base_url, client=None) -> None:
    _post(
        institute,
        "setWebhook",
        {
            "url": f"{base_url.rstrip('/')}/webhook/telegram/{institute.slug}",
            "secret_token": institute.telegram_secret,
            "allowed_updates": ["message"],
        },
        client,
    )

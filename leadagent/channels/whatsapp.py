import hashlib
import hmac

import httpx

from leadagent.channels.base import IncomingMsg
from leadagent.crypto import decrypt
from leadagent.settings import get_settings

GRAPH = "https://graph.facebook.com"
_client = httpx.Client(timeout=10)


def signature_ok(body: bytes, header_value) -> bool:
    secret = get_settings().whatsapp_app_secret
    if not secret or not header_value or not header_value.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header_value[len("sha256="):].encode(), expected.encode())


def parse(payload, institute_id_for) -> list[IncomingMsg]:
    """Return the user messages in a WhatsApp webhook payload. Delivery receipts and unknown numbers give []."""
    found = []
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                institute_id = institute_id_for(value.get("metadata", {}).get("phone_number_id", ""))
                if institute_id is None:
                    continue
                for message in value.get("messages", []):
                    sender, message_id = message.get("from"), message.get("id")
                    if not sender or not message_id:
                        continue
                    text = message.get("text", {}).get("body") if message.get("type") == "text" else None
                    found.append(IncomingMsg(institute_id, "whatsapp", str(sender), f"wa:{message_id}", text))
    except (AttributeError, TypeError):
        return []
    return found


def send(institute, user_id, text, client=None) -> None:
    settings = get_settings()
    response = (client or _client).post(
        f"{GRAPH}/{settings.whatsapp_api_version}/{institute.whatsapp_phone_number_id}/messages",
        headers={"Authorization": f"Bearer {decrypt(institute.whatsapp_token_enc)}"},
        json={"messaging_product": "whatsapp", "to": user_id, "type": "text", "text": {"body": text}},
    )
    response.raise_for_status()

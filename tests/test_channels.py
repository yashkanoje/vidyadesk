import hashlib
import hmac
import json

import httpx

from helpers import make_institute
from leadagent.channels import deliver, telegram, whatsapp
from leadagent.channels.base import IncomingMsg


def tg_update(text="hi", chat_type="private", **extra):
    message = {"message_id": 5, "chat": {"id": 555, "type": chat_type}, **extra}
    if text is not None:
        message["text"] = text
    return {"update_id": 8123, "message": message}


def wa_payload(number_id="PN1", messages=None, statuses=None):
    value = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": number_id}}
    if messages is not None:
        value["messages"] = messages
    if statuses is not None:
        value["statuses"] = statuses
    return {"object": "whatsapp_business_account", "entry": [{"id": "W1", "changes": [{"field": "messages", "value": value}]}]}


WA_TEXT = {"from": "919861012345", "id": "wamid.A1", "type": "text", "text": {"body": "fees?"}}
WA_IMAGE = {"from": "919861012345", "id": "wamid.A2", "type": "image", "image": {"id": "x"}}


def mock_client(seen, status=200):
    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["json"] = json.loads(request.content)
        return httpx.Response(status, json={"ok": True})

    return httpx.Client(transport=httpx.MockTransport(handler))


# Telegram


def test_telegram_text_message_parses():
    assert telegram.parse(7, tg_update()) == IncomingMsg(7, "telegram", "555", "tg:8123", "hi")


def test_telegram_photo_has_no_text():
    assert telegram.parse(7, tg_update(text=None, photo=[{"file_id": "x"}])).text is None


def test_telegram_group_chat_is_ignored():
    assert telegram.parse(7, tg_update(chat_type="group")) is None


def test_telegram_edited_message_is_ignored():
    assert telegram.parse(7, {"update_id": 1, "edited_message": {"chat": {"id": 1, "type": "private"}}}) is None


def test_telegram_malformed_update_is_ignored():
    assert telegram.parse(7, {"message": {"chat": {"id": 1, "type": "private"}}}) is None  # no update_id
    assert telegram.parse(7, {"update_id": 1, "message": "oops"}) is None
    assert telegram.parse(7, []) is None


def test_telegram_secret_check(session):
    institute = make_institute(session)
    assert telegram.secret_ok(institute, "secret-bright") is True
    assert telegram.secret_ok(institute, "wrong") is False
    assert telegram.secret_ok(institute, None) is False


def test_telegram_send_calls_the_bot_api(session):
    institute = make_institute(session)
    seen = {}
    telegram.send(institute, "555", "hello", client=mock_client(seen))
    assert seen["url"] == "https://api.telegram.org/bottoken-bright/sendMessage"
    assert seen["json"] == {"chat_id": "555", "text": "hello"}


def test_telegram_set_webhook(session):
    institute = make_institute(session)
    seen = {}
    telegram.set_webhook(institute, "https://example.test", client=mock_client(seen))
    assert seen["url"] == "https://api.telegram.org/bottoken-bright/setWebhook"
    assert seen["json"] == {
        "url": "https://example.test/webhook/telegram/bright",
        "secret_token": "secret-bright",
        "allowed_updates": ["message"],
    }


# WhatsApp


def sign(body: bytes, secret=b"app-secret") -> str:
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


def test_whatsapp_signature_check():
    body = b'{"a":1}'
    assert whatsapp.signature_ok(body, sign(body)) is True
    assert whatsapp.signature_ok(body, sign(body, b"other")) is False
    assert whatsapp.signature_ok(body + b" ", sign(body)) is False
    assert whatsapp.signature_ok(body, None) is False
    assert whatsapp.signature_ok(body, "md5=abc") is False


def test_whatsapp_signature_fails_closed_without_an_app_secret(monkeypatch):
    from leadagent.settings import get_settings

    monkeypatch.setattr(get_settings(), "whatsapp_app_secret", "")
    assert whatsapp.signature_ok(b"{}", sign(b"{}", b"")) is False


def test_whatsapp_text_and_image_parse():
    lookup = {"PN1": 3}.get
    msgs = whatsapp.parse(wa_payload(messages=[WA_TEXT, WA_IMAGE]), lookup)
    assert msgs == [
        IncomingMsg(3, "whatsapp", "919861012345", "wa:wamid.A1", "fees?"),
        IncomingMsg(3, "whatsapp", "919861012345", "wa:wamid.A2", None),
    ]


def test_whatsapp_delivery_receipts_are_ignored():
    assert whatsapp.parse(wa_payload(statuses=[{"id": "wamid.A1", "status": "delivered"}]), {"PN1": 3}.get) == []


def test_whatsapp_unknown_number_is_ignored():
    assert whatsapp.parse(wa_payload(number_id="OTHER", messages=[WA_TEXT]), {"PN1": 3}.get) == []


def test_whatsapp_malformed_payloads_are_ignored():
    lookup = {"PN1": 3}.get
    assert whatsapp.parse({}, lookup) == []
    assert whatsapp.parse([], lookup) == []
    assert whatsapp.parse({"entry": "oops"}, lookup) == []
    assert whatsapp.parse(wa_payload(messages=[{"type": "text"}]), lookup) == []  # no sender or id
    assert whatsapp.parse(wa_payload(messages=[{"from": "1", "id": "x", "type": "text"}]), lookup)[0].text is None


def test_whatsapp_send_calls_the_graph_api(session):
    institute = make_institute(session, whatsapp_phone_number_id="PN1")
    seen = {}
    whatsapp.send(institute, "919861012345", "hello", client=mock_client(seen))
    assert seen["url"] == "https://graph.facebook.com/v24.0/PN1/messages"
    assert seen["auth"] == "Bearer wa-token"
    assert seen["json"] == {
        "messaging_product": "whatsapp",
        "to": "919861012345",
        "type": "text",
        "text": {"body": "hello"},
    }


# Delivery


def failing_then_ok(monkeypatch, failures):
    attempts = []

    def fake_send(institute, user_id, text, client=None):
        attempts.append(text)
        if len(attempts) <= failures:
            raise httpx.ConnectError("no network")

    monkeypatch.setattr("leadagent.channels.telegram.send", fake_send)
    return attempts


def test_deliver_retries_then_succeeds(session, monkeypatch):
    institute = make_institute(session)
    attempts = failing_then_ok(monkeypatch, failures=2)
    waits = []
    assert deliver(institute, "telegram", "555", "hello", sleep=waits.append) is True
    assert len(attempts) == 3
    assert waits == [1, 2]


def test_deliver_gives_up_after_three_attempts(session, monkeypatch):
    institute = make_institute(session)
    attempts = failing_then_ok(monkeypatch, failures=99)
    assert deliver(institute, "telegram", "555", "hello", sleep=lambda seconds: None) is False
    assert len(attempts) == 3


def test_deliver_treats_an_error_status_as_a_failure(session):
    institute = make_institute(session)
    seen = {}
    client = mock_client(seen, status=500)
    try:
        telegram.send(institute, "555", "hello", client=client)
        raised = False
    except httpx.HTTPStatusError:
        raised = True
    assert raised

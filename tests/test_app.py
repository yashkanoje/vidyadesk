import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from helpers import ScriptedModel, make_institute
from leadagent.agent.graph import build_graph, get_checkpointer
from leadagent.app import app
from leadagent.channels.base import IncomingMsg

client = TestClient(app)  # not used as a context manager, so start-up (and the scheduler) does not run

UPDATE = {"update_id": 8123, "message": {"message_id": 5, "chat": {"id": 555, "type": "private"}, "text": "hi"}}


def wa_body(number_id="PN1", messages=None, statuses=None):
    value = {"metadata": {"phone_number_id": number_id}}
    if messages is not None:
        value["messages"] = messages
    if statuses is not None:
        value["statuses"] = statuses
    return json.dumps({"entry": [{"changes": [{"value": value}]}]}).encode()


WA_TEXT = {"from": "919861012345", "id": "wamid.A1", "type": "text", "text": {"body": "fees?"}}


def signed(body):
    return {"X-Hub-Signature-256": "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest(), "Content-Type": "application/json"}


@pytest.fixture
def processed(monkeypatch):
    seen = []
    monkeypatch.setattr("leadagent.app.process", seen.append)
    return seen


def test_health():
    assert client.get("/health").json() == {"ok": True}


def test_telegram_message_is_handed_to_the_pipeline(session, processed):
    institute = make_institute(session)
    response = client.post("/webhook/telegram/bright", json=UPDATE, headers={"X-Telegram-Bot-Api-Secret-Token": "secret-bright"})
    assert response.status_code == 200
    assert processed == [IncomingMsg(institute.id, "telegram", "555", "tg:8123", "hi")]


@pytest.mark.parametrize("headers", [{}, {"X-Telegram-Bot-Api-Secret-Token": "wrong"}])
def test_telegram_bad_secret_is_refused(session, processed, headers):
    make_institute(session)
    assert client.post("/webhook/telegram/bright", json=UPDATE, headers=headers).status_code == 403
    assert processed == []


def test_telegram_unknown_or_inactive_institute_is_refused(session, processed):
    make_institute(session, "closed", active=False)
    for slug, secret in (("nobody", "x"), ("closed", "secret-closed")):
        response = client.post(f"/webhook/telegram/{slug}", json=UPDATE, headers={"X-Telegram-Bot-Api-Secret-Token": secret})
        assert response.status_code == 403
    assert processed == []


def test_telegram_secret_of_another_institute_is_refused(session, processed):
    make_institute(session, "one")
    make_institute(session, "two")
    response = client.post("/webhook/telegram/one", json=UPDATE, headers={"X-Telegram-Bot-Api-Secret-Token": "secret-two"})
    assert response.status_code == 403


def test_telegram_body_that_is_not_json_is_a_400(session, processed):
    make_institute(session)
    response = client.post("/webhook/telegram/bright", content=b"not json", headers={"X-Telegram-Bot-Api-Secret-Token": "secret-bright"})
    assert response.status_code == 400
    assert processed == []


def test_telegram_update_without_a_message_is_accepted_and_ignored(session, processed):
    make_institute(session)
    response = client.post("/webhook/telegram/bright", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "secret-bright"})
    assert response.status_code == 200
    assert processed == []


def test_whatsapp_verification_handshake():
    ok = client.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "12345"})
    assert (ok.status_code, ok.text) == (200, "12345")
    bad = client.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"})
    assert bad.status_code == 403


def test_whatsapp_message_is_routed_by_phone_number(session, processed):
    make_institute(session, "one", whatsapp_phone_number_id="PN1")
    two = make_institute(session, "two", whatsapp_phone_number_id="PN2")
    body = wa_body("PN2", messages=[WA_TEXT])
    assert client.post("/webhook/whatsapp", content=body, headers=signed(body)).status_code == 200
    assert processed == [IncomingMsg(two.id, "whatsapp", "919861012345", "wa:wamid.A1", "fees?")]


def test_whatsapp_bad_signature_is_refused(session, processed):
    make_institute(session, whatsapp_phone_number_id="PN1")
    body = wa_body(messages=[WA_TEXT])
    headers = {"X-Hub-Signature-256": "sha256=" + "0" * 64, "Content-Type": "application/json"}
    assert client.post("/webhook/whatsapp", content=body, headers=headers).status_code == 403
    assert client.post("/webhook/whatsapp", content=body, headers={"Content-Type": "application/json"}).status_code == 403
    assert processed == []


def test_whatsapp_receipts_unknown_numbers_and_inactive_institutes_are_ignored(session, processed):
    make_institute(session, "closed", whatsapp_phone_number_id="PN9", active=False)
    for body in (
        wa_body("PN1", statuses=[{"id": "wamid.A1", "status": "read"}]),
        wa_body("UNKNOWN", messages=[WA_TEXT]),
        wa_body("PN9", messages=[WA_TEXT]),
        b"{}",
    ):
        assert client.post("/webhook/whatsapp", content=body, headers=signed(body)).status_code == 200
    assert processed == []


def test_whatsapp_signed_body_that_is_not_json_is_a_400(processed):
    body = b"not json"
    assert client.post("/webhook/whatsapp", content=body, headers=signed(body)).status_code == 400


def test_the_same_telegram_update_twice_gives_one_reply(session, sent, monkeypatch):
    make_institute(session)
    graph = build_graph(ScriptedModel(AIMessage("Hello!")), get_checkpointer())
    monkeypatch.setattr("leadagent.pipeline.get_graph", lambda: graph)
    headers = {"X-Telegram-Bot-Api-Secret-Token": "secret-bright"}
    client.post("/webhook/telegram/bright", json=UPDATE, headers=headers)
    client.post("/webhook/telegram/bright", json=UPDATE, headers=headers)
    assert [s[3] for s in sent] == ["Hello!"]


def test_start_up_loads_the_embedding_model_once(monkeypatch):
    calls = []
    monkeypatch.setattr("leadagent.rag.embed.get_embedder", lambda: calls.append(1))

    class Scheduler:
        def shutdown(self, wait=False):
            pass

    monkeypatch.setattr("leadagent.jobs.start_scheduler", lambda: Scheduler())
    with TestClient(app):
        pass
    assert calls == [1]

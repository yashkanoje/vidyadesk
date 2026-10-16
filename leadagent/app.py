import hmac
import json
import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse

from leadagent.channels import telegram, whatsapp
from leadagent.pipeline import process
from leadagent.rag import embed
from leadagent.settings import get_settings
from leadagent.store import repo
from leadagent.store.db import create_tables, session_scope

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
# httpx logs every request URL at INFO, and a Telegram URL contains the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app):
    from leadagent.jobs import start_scheduler

    create_tables()
    embed.get_embedder()  # load the model now, not during a student's first question
    scheduler = start_scheduler()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(lifespan=lifespan)


def _json(body: bytes):
    try:
        return json.loads(body)
    except ValueError:
        raise HTTPException(400, "body is not JSON")


@app.get("/health")
def health():
    return {"ok": True}


def _telegram_message(slug, secret, body):
    with session_scope() as session:
        institute = repo.institute_by_slug(session, slug)
        # The same answer for an unknown institute and a wrong secret, so slugs cannot be probed.
        if institute is None or not institute.active or not telegram.secret_ok(institute, secret):
            raise HTTPException(403)
        institute_id = institute.id
    return telegram.parse(institute_id, _json(body))


@app.post("/webhook/telegram/{slug}")
async def telegram_webhook(slug: str, request: Request, background: BackgroundTasks):
    body = await request.body()
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    msg = await run_in_threadpool(_telegram_message, slug, secret, body)
    if msg is not None:
        background.add_task(process, msg)
    return {"ok": True}


@app.get("/webhook/whatsapp")
def whatsapp_verify(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
):
    expected = get_settings().whatsapp_verify_token
    if mode == "subscribe" and expected and hmac.compare_digest(token.encode(), expected.encode()):
        return PlainTextResponse(challenge)
    raise HTTPException(403)


def _whatsapp_messages(payload):
    with session_scope() as session:

        def institute_id_for(phone_number_id):
            institute = repo.institute_by_whatsapp_number(session, phone_number_id)
            return institute.id if institute is not None and institute.active else None

        return whatsapp.parse(payload, institute_id_for)


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request, background: BackgroundTasks):
    body = await request.body()
    if not whatsapp.signature_ok(body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(403)
    payload = _json(body)
    for msg in await run_in_threadpool(_whatsapp_messages, payload):
        background.add_task(process, msg)
    return {"ok": True}

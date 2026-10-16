import csv
import io
import logging
import tempfile
from datetime import timedelta
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from leadagent.actions import delete_lead_and_history
from leadagent.auth import LoginThrottle, dummy_hash, password_matches
from leadagent.rag.ingest import MAX_BYTES, IngestError, ingest
from leadagent.store import repo
from leadagent.store.db import session_scope
from leadagent.store.models import utcnow

log = logging.getLogger(__name__)
router = APIRouter(prefix="/dash")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
throttle = LoginThrottle()

STAGES = ("new", "collecting", "qualified", "handed_off", "closed")
INTERESTS = ("hot", "warm", "cold")
FORMULA_START = ("=", "+", "-", "@")


def _filters(stage, interest, days):
    since = utcnow() - timedelta(days=days) if days > 0 else None
    return (stage if stage in STAGES else None), (interest if interest in INTERESTS else None), since


def _cell(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_START) else text  # a spreadsheet must not run it as a formula


def _owned_lead(session, institute, lead_id):
    lead = repo.get_lead(session, institute.id, lead_id)
    if lead is None:
        raise HTTPException(404)
    return lead


def _user(session, request):
    user_id = request.session.get("user_id")
    user = repo.get_user(session, user_id) if isinstance(user_id, int) else None
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=303, headers={"Location": "/dash/login"})
    return user


def _admin(session, request):
    user = _user(session, request)
    if user.role != "admin":
        raise HTTPException(404)
    return user


def _institute(session, user, slug):
    institute = repo.institute_by_slug(session, slug)
    # The same answer for "no such institute" and "not yours", so slugs cannot be probed.
    if institute is None or (user.role != "admin" and user.institute_id != institute.id):
        raise HTTPException(404)
    return institute


def _home(session, user) -> str:
    if user.role == "admin":
        return "/dash/admin/institutes"
    return f"/dash/{repo.get_institute(session, user.institute_id).slug}/leads"


def _local(institute):
    zone = ZoneInfo(institute.timezone)
    return lambda moment: moment.astimezone(zone).strftime("%d %b %Y %H:%M") if moment else ""


def _flash(request, text) -> None:
    request.session["flash"] = text


def _render(request, name, context, status_code=200):
    return templates.TemplateResponse(
        request, name, {"flash": request.session.pop("flash", None), **context}, status_code=status_code
    )


@router.get("")
def home(request: Request):
    with session_scope() as session:
        return RedirectResponse(_home(session, _user(session, request)), status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return _render(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    key = email.strip().lower()
    if throttle.blocked(key):
        return _render(
            request, "login.html", {"error": "Too many failed attempts. Try again in 15 minutes."}, status_code=429
        )
    with session_scope() as session:
        user = repo.user_by_email(session, key)
        if not password_matches(password, user.password_hash if user else dummy_hash()) or user is None:
            throttle.failed(key)
            return _render(request, "login.html", {"error": "Wrong email or password."}, status_code=401)
        throttle.succeeded(key)
        request.session.clear()  # a fresh session on every login
        request.session["user_id"] = user.id
        return RedirectResponse(_home(session, user), status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/dash/login", status_code=303)


# Placeholder until Task 9 replaces it: they already apply the access rules.
@router.get("/admin/institutes", response_class=HTMLResponse)
def institutes_page(request: Request):
    with session_scope() as session:
        _admin(session, request)
        return HTMLResponse("Institutes")


def safe_filename(name):
    """The bare file name of an upload, or None. Never a path, so nothing is written outside the temp folder."""
    bare = PurePosixPath((name or "").replace("\\", "/")).name.strip()[:255]
    return None if bare in ("", ".", "..") else bare


@router.get("/{slug}/documents", response_class=HTMLResponse)
def documents_page(request: Request, slug: str):
    with session_scope() as session:
        user = _user(session, request)
        institute = _institute(session, user, slug)
        return _render(
            request,
            "documents.html",
            {"user": user, "institute": institute, "local": _local(institute),
             "documents": repo.documents_for(session, institute.id)},
        )


@router.post("/{slug}/documents")
def upload_document(request: Request, slug: str, file: UploadFile = File(...)):
    with session_scope() as session:
        institute = _institute(session, _user(session, request), slug)
        name = safe_filename(file.filename)
        data = file.file.read(MAX_BYTES + 1)
        if name is None:
            _flash(request, "Choose a file to upload.")
        elif len(data) > MAX_BYTES:
            _flash(request, f"{name} is larger than 10 MB")
        else:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / name
                path.write_bytes(data)
                try:
                    document = ingest(session, institute.id, path)
                    reason = f" ({document.error})" if document.error else ""
                    _flash(request, f"Added {document.filename}: {document.status}{reason}")
                except IngestError as exc:
                    _flash(request, str(exc))
                except Exception:
                    session.rollback()  # the old version, if any, must survive a half-finished replace
                    log.exception("upload failed for institute %s", institute.slug)
                    _flash(request, f"Could not add {name}. Please try again.")
        return RedirectResponse(f"/dash/{institute.slug}/documents", status_code=303)


@router.post("/{slug}/documents/{document_id}/delete")
def delete_document(request: Request, slug: str, document_id: int):
    with session_scope() as session:
        institute = _institute(session, _user(session, request), slug)
        document = repo.get_document(session, institute.id, document_id)
        if document is None:
            raise HTTPException(404)
        repo.delete_document(session, document)
        _flash(request, f"{document.filename} and its passages are deleted.")
        return RedirectResponse(f"/dash/{institute.slug}/documents", status_code=303)


@router.get("/{slug}/leads", response_class=HTMLResponse)
def leads_page(request: Request, slug: str, stage: str = "", interest: str = "", days: int = 0):
    with session_scope() as session:
        user = _user(session, request)
        institute = _institute(session, user, slug)
        leads = repo.leads_for(session, institute.id, *_filters(stage, interest, days))
        return _render(
            request,
            "leads.html",
            {
                "user": user, "institute": institute, "leads": leads, "local": _local(institute),
                "stage": stage, "interest": interest, "days": days, "stages": STAGES, "interests": INTERESTS,
            },
        )


@router.get("/{slug}/leads.csv")
def leads_csv(request: Request, slug: str, stage: str = "", interest: str = "", days: int = 0):
    with session_scope() as session:
        institute = _institute(session, _user(session, request), slug)
        local = _local(institute)
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["id", "created", "name", "class", "course", "phone", "stage", "interest", "last message"])
        for lead in repo.leads_for(session, institute.id, *_filters(stage, interest, days)):
            writer.writerow(
                [
                    lead.id, local(lead.created_at), _cell(lead.name), _cell(lead.student_class), _cell(lead.course),
                    _cell(lead.phone or lead.channel_user_id), lead.stage, lead.interest or "", local(lead.last_user_msg_at),
                ]
            )
        return Response(
            "﻿" + out.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{institute.slug}-leads.csv"'},
        )


@router.get("/{slug}/leads/{lead_id}", response_class=HTMLResponse)
def lead_page(request: Request, slug: str, lead_id: int):
    with session_scope() as session:
        user = _user(session, request)
        institute = _institute(session, user, slug)
        lead = _owned_lead(session, institute, lead_id)
        return _render(
            request,
            "lead.html",
            {
                "user": user, "institute": institute, "lead": lead, "local": _local(institute),
                "messages": repo.messages_for(session, institute.id, lead.id),
            },
        )


@router.post("/{slug}/leads/{lead_id}/{action}")
def lead_action(request: Request, slug: str, lead_id: int, action: str):
    if action not in ("resume", "close", "delete"):
        raise HTTPException(404)
    with session_scope() as session:
        institute = _institute(session, _user(session, request), slug)
        lead = _owned_lead(session, institute, lead_id)
        if action == "delete":
            delete_lead_and_history(session, lead)
            _flash(request, f"Lead {lead_id} and its messages are deleted.")
            return RedirectResponse(f"/dash/{institute.slug}/leads", status_code=303)
        if action == "resume":
            repo.resume(session, lead)
            _flash(request, "The assistant is switched back on for this lead.")
        else:
            repo.close_lead(session, lead)
            _flash(request, "Lead closed.")
        return RedirectResponse(f"/dash/{institute.slug}/leads/{lead_id}", status_code=303)

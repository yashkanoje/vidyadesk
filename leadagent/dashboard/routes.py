import csv
import io
import logging
import tempfile
from datetime import timedelta
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

import yaml
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from leadagent.actions import delete_lead_and_history
from leadagent.auth import LoginThrottle, dummy_hash, password_matches
from leadagent.cli import add_institute
from leadagent.facts import FactsError, parse_facts
from leadagent.rag.ingest import MAX_BYTES, IngestError, ingest
from leadagent.store import repo
from leadagent.store.db import session_scope
from leadagent.store.models import utcnow

log = logging.getLogger(__name__)
router = APIRouter(prefix="/dash")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
throttle = LoginThrottle()


def initials(name) -> str:
    """Letters for a lead's round avatar: first and last word, '?' when there is no name yet."""
    words = (name or "").split()
    if not words:
        return "?"
    return (words[0][0] + (words[-1][0] if len(words) > 1 else "")).upper()


def about(lead, extra=None) -> str:
    """The muted line under a lead's name: class · course · extra, leaving out what is not known yet."""
    student_class = lead.student_class or ""
    if student_class and not student_class.lower().startswith("class"):  # the model often saves "Class 11" itself
        student_class = f"Class {student_class}"
    return " · ".join(part for part in (student_class, lead.course, extra) if part) or "No details yet"


templates.env.filters["initials"] = initials
templates.env.filters["about"] = about
EXAMPLE_FACTS = (Path(__file__).resolve().parents[2] / "examples" / "brightpath.yaml").read_text(encoding="utf-8")

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
    return f"/dash/{repo.get_institute(session, user.institute_id).slug}/home"


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
    if len(key) > 254:  # no such address; do not let it into the throttle
        return _render(request, "login.html", {"error": "Wrong email or password."}, status_code=401)
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


def _institutes_context(session, user, error=None, form=None):
    return {
        "user": user, "institute": None, "institutes": repo.all_institutes(session), "error": error,
        "form": form or {"slug": "", "name": "", "timezone": "Asia/Kolkata", "facts_yaml": EXAMPLE_FACTS},
    }


@router.get("/admin/institutes", response_class=HTMLResponse)
def institutes_page(request: Request):
    with session_scope() as session:
        user = _admin(session, request)
        return _render(request, "institutes.html", _institutes_context(session, user))


@router.post("/admin/institutes", response_class=HTMLResponse)
def create_institute(
    request: Request,
    slug: str = Form(...),
    name: str = Form(...),
    telegram_token: str = Form(...),
    facts_yaml: str = Form(...),
    timezone: str = Form("Asia/Kolkata"),
):
    with session_scope() as session:
        user = _admin(session, request)
        try:
            facts = parse_facts(yaml.safe_load(facts_yaml))
            add_institute(session, slug=slug.strip(), name=name.strip(), facts=facts,
                          telegram_token=telegram_token.strip(), timezone=timezone.strip())
        except yaml.YAMLError as exc:
            error = f"Facts: this is not valid YAML: {exc}"
        except (FactsError, ValueError) as exc:  # FactsError is a ValueError too; both messages are safe to show
            error = str(exc)
        else:
            _flash(request, f"Added {slug.strip()}. Next: set-webhook, then the owner sends /whoami and you run set-owner.")
            return RedirectResponse("/dash/admin/institutes", status_code=303)
        session.rollback()
        form = {"slug": slug, "name": name, "timezone": timezone, "facts_yaml": facts_yaml}  # never echo the token
        return _render(request, "institutes.html", _institutes_context(session, user, error, form), status_code=400)


@router.post("/admin/institutes/{slug}/active")
def toggle_institute(request: Request, slug: str):
    with session_scope() as session:
        _admin(session, request)
        institute = repo.institute_by_slug(session, slug)
        if institute is None:
            raise HTTPException(404)
        institute.active = not institute.active
        _flash(request, f"{institute.slug} is now {'on' if institute.active else 'off'}.")
        return RedirectResponse("/dash/admin/institutes", status_code=303)


def safe_filename(name):
    """The bare file name of an upload, or None. Never a path, so nothing is written outside the temp folder."""
    bare = PurePosixPath((name or "").replace("\\", "/")).name.strip()[:255]
    # ":" and the rest are drive and reserved characters: on Windows "Y:.env" would resolve outside the temp folder
    bad = bare in ("", ".", "..") or any(c in ':<>"|?*' or ord(c) < 32 for c in bare)
    return None if bad else bare


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
                try:
                    if path.parent != Path(folder):
                        raise IngestError("Choose a file to upload.")
                    path.write_bytes(data)
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


def _facts_text(institute) -> str:
    return yaml.safe_dump(institute.facts, allow_unicode=True, sort_keys=False)


@router.get("/{slug}/facts", response_class=HTMLResponse)
def facts_page(request: Request, slug: str):
    with session_scope() as session:
        user = _user(session, request)
        institute = _institute(session, user, slug)
        return _render(request, "facts.html", {"user": user, "institute": institute, "text": _facts_text(institute), "error": None})


@router.post("/{slug}/facts", response_class=HTMLResponse)
def save_facts(request: Request, slug: str, facts_yaml: str = Form(...)):
    with session_scope() as session:
        user = _user(session, request)
        institute = _institute(session, user, slug)
        try:
            facts = parse_facts(yaml.safe_load(facts_yaml))
        except yaml.YAMLError as exc:
            error = f"This is not valid YAML: {exc}"
        except FactsError as exc:
            error = str(exc)
        else:
            institute.facts = facts.model_dump()
            _flash(request, "Facts saved. The assistant uses them from the next message.")
            return RedirectResponse(f"/dash/{institute.slug}/facts", status_code=303)
        return _render(
            request, "facts.html", {"user": user, "institute": institute, "text": facts_yaml, "error": error}, status_code=400
        )


@router.get("/{slug}/stats", response_class=HTMLResponse)
def stats_page(request: Request, slug: str):
    with session_scope() as session:
        user = _user(session, request)
        institute = _institute(session, user, slug)
        stats = repo.lead_stats(session, institute.id, institute.timezone, utcnow())
        return _render(request, "stats.html", {"user": user, "institute": institute, "stats": stats})


@router.get("/{slug}/home", response_class=HTMLResponse)
def home_page(request: Request, slug: str):
    with session_scope() as session:
        user = _user(session, request)
        institute = _institute(session, user, slug)
        return _render(
            request,
            "home.html",
            {
                "user": user, "institute": institute, "local": _local(institute),
                "summary": repo.home_summary(session, institute.id, institute.timezone, utcnow()),
                "intro_name": institute.name if user.role == "owner" else "VidyaDesk",
            },
        )

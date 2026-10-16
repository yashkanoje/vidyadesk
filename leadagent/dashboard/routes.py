import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from leadagent.auth import LoginThrottle, dummy_hash, password_matches
from leadagent.store import repo
from leadagent.store.db import session_scope

log = logging.getLogger(__name__)
router = APIRouter(prefix="/dash")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
throttle = LoginThrottle()


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


# Placeholders until Tasks 6 and 9 replace them: they already apply the access rules.
@router.get("/admin/institutes", response_class=HTMLResponse)
def institutes_page(request: Request):
    with session_scope() as session:
        _admin(session, request)
        return HTMLResponse("Institutes")


@router.get("/{slug}/leads", response_class=HTMLResponse)
def leads_page(request: Request, slug: str):
    with session_scope() as session:
        _institute(session, _user(session, request), slug)
        return HTMLResponse("Leads")

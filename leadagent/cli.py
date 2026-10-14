"""Add and configure institutes.

    python -m leadagent.cli init-db
    python -m leadagent.cli add-institute --slug brightpath --name "BrightPath Classes" --facts examples/brightpath.yaml
    python -m leadagent.cli set-owner --slug brightpath --chat-id 123456789
    python -m leadagent.cli set-webhook --slug brightpath
    python -m leadagent.cli set-whatsapp --slug brightpath --number-id 123456789012345
"""
import argparse
import getpass
import re
import secrets
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from leadagent.agent.graph import get_checkpointer
from leadagent.channels import telegram
from leadagent.crypto import encrypt
from leadagent.facts import Facts, FactsError, load_facts_file
from leadagent.locks import lock_for
from leadagent.settings import get_settings
from leadagent.store import repo
from leadagent.store.db import create_tables, session_scope
from leadagent.store.models import Institute


def _existing(session, slug) -> Institute:
    institute = repo.institute_by_slug(session, slug)
    if institute is None:
        raise ValueError(f"No institute with slug {slug!r}")
    return institute


def add_institute(
    session, *, slug, name, facts: Facts, telegram_token, timezone="Asia/Kolkata", whatsapp_number_id=None, whatsapp_token=None
) -> Institute:
    if not re.fullmatch(r"[a-z0-9-]{1,64}", slug):
        raise ValueError("slug must be 1 to 64 lowercase letters, digits or hyphens")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"unknown timezone {timezone!r}")
    if whatsapp_number_id and not whatsapp_token:
        raise ValueError("a WhatsApp number needs its access token")
    if repo.institute_by_slug(session, slug) is not None:
        raise ValueError(f"Institute {slug!r} already exists")
    institute = Institute(
        slug=slug,
        name=name,
        timezone=timezone,
        facts=facts.model_dump(),
        telegram_bot_token_enc=encrypt(telegram_token),
        telegram_secret=secrets.token_urlsafe(32),
        whatsapp_phone_number_id=whatsapp_number_id or None,
        whatsapp_token_enc=encrypt(whatsapp_token) if whatsapp_token else None,
    )
    session.add(institute)
    session.flush()
    return institute


def set_facts(session, slug, facts: Facts) -> Institute:
    institute = _existing(session, slug)
    institute.facts = facts.model_dump()
    return institute


def set_owner(session, slug, chat_id) -> Institute:
    institute = _existing(session, slug)
    institute.owner_telegram_chat_id = str(chat_id)
    # Telegram sends /start when the owner first opens the bot, before they can be registered here, and that
    # message made them a lead. Remove it, or the owner gets their own follow-up and shows up in the summary.
    lead = repo.find_lead(session, institute.id, "telegram", str(chat_id))
    if lead is not None:
        with lock_for(lead.id):
            repo.delete_lead(session, lead)
            session.flush()
            get_checkpointer().delete_thread(str(lead.id))
    return institute


def set_whatsapp(session, slug, number_id, token) -> Institute:
    """Attach a WhatsApp number to an institute, or replace its access token (Meta's test tokens last about a day)."""
    institute = _existing(session, slug)
    number_id, token = (number_id or "").strip(), (token or "").strip()
    if not number_id:
        raise ValueError("the WhatsApp phone number ID is empty")
    if not token:
        raise ValueError("the WhatsApp access token is empty")
    other = repo.institute_by_whatsapp_number(session, number_id)
    if other is not None and other.id != institute.id:
        raise ValueError(f"WhatsApp number {number_id} is already attached to institute {other.slug!r}")
    institute.whatsapp_phone_number_id = number_id
    institute.whatsapp_token_enc = encrypt(token)
    return institute


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="leadagent.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db")
    commands.add_parser("list")
    add = commands.add_parser("add-institute")
    add.add_argument("--slug", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--facts", required=True)
    add.add_argument("--timezone", default="Asia/Kolkata")
    add.add_argument("--whatsapp-number-id")
    facts = commands.add_parser("set-facts")
    facts.add_argument("--slug", required=True)
    facts.add_argument("--facts", required=True)
    owner = commands.add_parser("set-owner")
    owner.add_argument("--slug", required=True)
    owner.add_argument("--chat-id", required=True)
    whatsapp = commands.add_parser("set-whatsapp")
    whatsapp.add_argument("--slug", required=True)
    whatsapp.add_argument("--number-id", required=True)
    webhook = commands.add_parser("set-webhook")
    webhook.add_argument("--slug", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "init-db":
            create_tables()
            print("Tables are ready.")
            return 0
        with session_scope() as session:
            if args.command == "list":
                for institute in repo.active_institutes(session):
                    print(f"{institute.id}  {institute.slug}  owner chat: {institute.owner_telegram_chat_id or 'not set'}")
            elif args.command == "add-institute":
                # Tokens are typed at a prompt so they do not end up in the shell history.
                telegram_token = getpass.getpass("Telegram bot token: ")
                whatsapp_token = getpass.getpass("WhatsApp access token: ") if args.whatsapp_number_id else None
                institute = add_institute(
                    session,
                    slug=args.slug,
                    name=args.name,
                    facts=load_facts_file(args.facts),
                    telegram_token=telegram_token,
                    timezone=args.timezone,
                    whatsapp_number_id=args.whatsapp_number_id,
                    whatsapp_token=whatsapp_token,
                )
                print(f"Added institute {institute.slug} with id {institute.id}.")
            elif args.command == "set-facts":
                set_facts(session, args.slug, load_facts_file(args.facts))
                print("Facts updated.")
            elif args.command == "set-owner":
                set_owner(session, args.slug, args.chat_id)
                print("Owner chat saved.")
            elif args.command == "set-whatsapp":
                set_whatsapp(session, args.slug, args.number_id, getpass.getpass("WhatsApp access token: "))
                print("WhatsApp number and token saved.")
            elif args.command == "set-webhook":
                base_url = get_settings().public_base_url
                if not base_url.startswith("https://"):
                    raise ValueError("set PUBLIC_BASE_URL in .env to the public https address first")
                telegram.set_webhook(_existing(session, args.slug), base_url)
                print("Telegram webhook set.")
    except (ValueError, FactsError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        # Print the error type only: the exception text holds the request URL, which contains the bot token.
        reason = "Check the bot token."
        if isinstance(exc, httpx.HTTPStatusError):
            try:  # Telegram's own explanation, such as a tunnel address it cannot resolve; it never holds the token
                reason = exc.response.json().get("description") or reason
            except ValueError:
                pass
        print(f"Error: Telegram refused the request ({type(exc).__name__}). {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

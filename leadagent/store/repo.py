from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert

from leadagent.store.models import Chunk, Document, Institute, Lead, Message, User, utcnow

LEAD_FIELDS = ("name", "student_class", "course", "phone", "notes")


def get_institute(session, institute_id):
    return session.get(Institute, institute_id)


def institute_by_slug(session, slug):
    return session.scalars(select(Institute).where(Institute.slug == slug)).one_or_none()


def institute_by_whatsapp_number(session, phone_number_id):
    if not phone_number_id:
        return None
    return session.scalars(
        select(Institute).where(Institute.whatsapp_phone_number_id == phone_number_id)
    ).one_or_none()


def active_institutes(session):
    return list(session.scalars(select(Institute).where(Institute.active.is_(True)).order_by(Institute.id)))


def get_or_create_lead(session, institute_id, channel, channel_user_id):
    session.execute(
        insert(Lead)
        .values(
            institute_id=institute_id,
            channel=channel,
            channel_user_id=channel_user_id,
            phone=channel_user_id if channel == "whatsapp" else None,
            stage="new",
            created_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["institute_id", "channel", "channel_user_id"])
    )
    return session.scalars(
        select(Lead).where(
            Lead.institute_id == institute_id,
            Lead.channel == channel,
            Lead.channel_user_id == channel_user_id,
        )
    ).one()


def find_lead(session, institute_id, channel, channel_user_id):
    return session.scalars(
        select(Lead).where(
            Lead.institute_id == institute_id,
            Lead.channel == channel,
            Lead.channel_user_id == channel_user_id,
        )
    ).one_or_none()


def get_lead(session, institute_id, lead_id):
    return session.scalars(
        select(Lead).where(Lead.id == lead_id, Lead.institute_id == institute_id)
    ).one_or_none()


def log_message(session, lead, role, text, channel_msg_id=None) -> bool:
    """Return False when this incoming message was already logged (a resent webhook)."""
    result = session.execute(
        insert(Message)
        .values(
            institute_id=lead.institute_id,
            lead_id=lead.id,
            role=role,
            text=text,
            channel_msg_id=channel_msg_id,
            created_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["institute_id", "channel_msg_id"])
        .returning(Message.id)
    )
    # RETURNING gives no row on a conflict. rowcount is not usable here: SQLAlchemy reports -1 for it.
    return result.first() is not None


def touch_user_message(session, lead, now) -> None:
    lead.last_user_msg_at = now
    if lead.stage == "new":
        lead.stage = "collecting"


def user_messages_last_24h(session, lead_id, now) -> int:
    return session.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.lead_id == lead_id,
            Message.role == "user",
            Message.created_at > now - timedelta(hours=24),
        )
    )


def recent_messages(session, lead_id, limit):
    rows = session.scalars(
        select(Message).where(Message.lead_id == lead_id).order_by(Message.id.desc()).limit(limit)
    ).all()
    return list(reversed(rows))


def sent_since(session, lead_id, text, since) -> bool:
    """Whether this exact assistant message was sent to the lead after `since`."""
    return (
        session.scalar(
            select(Message.id)
            .where(
                Message.lead_id == lead_id,
                Message.role == "assistant",
                Message.text == text,
                Message.created_at > since,
            )
            .limit(1)
        )
        is not None
    )


def _has_core_details(lead) -> bool:
    return bool(lead.name and lead.student_class and lead.course)


def save_lead_fields(session, lead, **fields):
    for key in LEAD_FIELDS:
        value = (fields.get(key) or "").strip()
        if value:
            # Cut to the column's length (None for notes, which is unbounded): an over-long value used to fail
            # the whole turn and lose the other details with it.
            setattr(lead, key, value[: Lead.__table__.c[key].type.length])
    if lead.stage in ("new", "collecting") and _has_core_details(lead):
        lead.stage = "qualified"
    return lead


def set_interest(session, lead, level, reason) -> None:
    lead.interest = level
    lead.interest_reason = reason


def hand_off(session, lead, reason) -> None:
    lead.stage = "handed_off"
    lead.handoff_reason = reason


def resume(session, lead) -> None:
    lead.stage = "qualified" if _has_core_details(lead) else "collecting"
    lead.handoff_reason = None


def delete_lead(session, lead) -> None:
    session.delete(lead)  # messages go with it through the foreign key's ON DELETE CASCADE


def _is_daytime(timezone_name, now) -> bool:
    return 9 <= now.astimezone(ZoneInfo(timezone_name)).hour < 21


def due_nudges(session, now, lead_id=None):
    """Leads that should get their one follow-up now. With lead_id, re-check just that lead."""
    query = (
        select(Lead, Institute.timezone)
        .join(Institute, Institute.id == Lead.institute_id)
        .where(
            Institute.active.is_(True),
            Lead.stage.in_(("collecting", "qualified")),
            or_(Lead.interest.is_(None), Lead.interest != "cold"),
            Lead.nudged_at.is_(None),
            Lead.last_user_msg_at <= now - timedelta(hours=2),
            Lead.last_user_msg_at >= now - timedelta(hours=20),
        )
        .order_by(Lead.id)
    )
    if lead_id is not None:
        query = query.where(Lead.id == lead_id)
    rows = session.execute(query).all()
    return [lead for lead, timezone_name in rows if _is_daytime(timezone_name, now)]


def digest_leads(session, institute_id, now):
    since = now - timedelta(hours=24)
    mine = select(Lead).where(Lead.institute_id == institute_id).order_by(Lead.id)
    new = session.scalars(mine.where(Lead.created_at > since)).all()
    hot = session.scalars(
        mine.where(Lead.interest == "hot", Lead.stage != "closed", Lead.last_user_msg_at > since)
    ).all()
    waiting = session.scalars(mine.where(Lead.stage == "handed_off")).all()
    return list(new), list(hot), list(waiting)


def add_document(session, institute_id, filename):
    document = Document(institute_id=institute_id, filename=filename, status="ready")
    session.add(document)
    session.flush()
    return document


def mark_document_failed(session, document, reason) -> None:
    document.status = "failed"
    document.error = reason


def add_chunks(session, document, texts, vectors) -> None:
    session.add_all(
        Chunk(institute_id=document.institute_id, document_id=document.id, position=i, text=text, embedding=vector)
        for i, (text, vector) in enumerate(zip(texts, vectors, strict=True))
    )


def documents_for(session, institute_id):
    return list(session.scalars(select(Document).where(Document.institute_id == institute_id).order_by(Document.id)))


def get_document(session, institute_id, document_id):
    return session.scalars(
        select(Document).where(Document.id == document_id, Document.institute_id == institute_id)
    ).one_or_none()


def documents_named(session, institute_id, filename):
    return list(
        session.scalars(select(Document).where(Document.institute_id == institute_id, Document.filename == filename))
    )


def delete_document(session, document) -> None:
    session.delete(document)  # its passages go with it through ON DELETE CASCADE


def nearest_chunks(session, institute_id, vector, k):
    """This institute's k passages closest in meaning to the vector, as (chunk, cosine distance, filename)."""
    distance = Chunk.embedding.cosine_distance(vector).label("distance")
    rows = session.execute(
        select(Chunk, distance, Document.filename)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.institute_id == institute_id, Document.status == "ready")
        .order_by(distance)
        .limit(k)
    ).all()
    return [(chunk, float(dist), filename) for chunk, dist, filename in rows]


def add_user(session, email, password_hash, role, institute_id=None):
    user = User(email=email.strip().lower(), password_hash=password_hash, role=role, institute_id=institute_id)
    session.add(user)
    session.flush()
    return user


def user_by_email(session, email):
    return session.scalars(select(User).where(User.email == email.strip().lower())).one_or_none()


def get_user(session, user_id):
    return session.get(User, user_id)

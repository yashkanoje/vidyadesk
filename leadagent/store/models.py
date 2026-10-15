from datetime import datetime, timezone

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from leadagent.rag.embed import DIMS


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Institute(Base):
    __tablename__ = "institutes"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    facts: Mapped[dict] = mapped_column(JSONB)
    telegram_bot_token_enc: Mapped[str] = mapped_column(Text)
    telegram_secret: Mapped[str] = mapped_column(String(128))
    whatsapp_phone_number_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    whatsapp_token_enc: Mapped[str | None] = mapped_column(Text)
    owner_telegram_chat_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("institute_id", "channel", "channel_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    institute_id: Mapped[int] = mapped_column(ForeignKey("institutes.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    channel_user_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(200))
    student_class: Mapped[str | None] = mapped_column(String(64))
    course: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(String(16), default="new")
    interest: Mapped[str | None] = mapped_column(String(8))
    interest_reason: Mapped[str | None] = mapped_column(Text)
    handoff_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_user_msg_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nudged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("institute_id", "channel_msg_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    institute_id: Mapped[int] = mapped_column(ForeignKey("institutes.id", ondelete="CASCADE"))
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user / assistant / owner
    text: Mapped[str] = mapped_column(Text)
    channel_msg_id: Mapped[str | None] = mapped_column(String(128))  # "tg:<update id>" or "wa:<message id>"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    institute_id: Mapped[int] = mapped_column(ForeignKey("institutes.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="ready")  # ready / failed
    error: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    institute_id: Mapped[int] = mapped_column(ForeignKey("institutes.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(DIMS))

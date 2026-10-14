from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from leadagent.settings import get_settings
from leadagent.store.models import Base

engine = create_engine(
    get_settings().database_url.replace("postgresql://", "postgresql+psycopg://", 1),
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_tables() -> None:
    # shortcut: create_all never alters an existing table, switch to Alembic before changing a column on a database with real data
    Base.metadata.create_all(engine)

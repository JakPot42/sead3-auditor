"""
database.py
===========
SQLAlchemy engine + session plumbing.

Uses a local SQLite file (see config.DATABASE_URL) so the whole application
runs with no external services -- suitable for an air-gapped host. SQLite is
fine for single-facility FSO use; swap DATABASE_URL for PostgreSQL if you
outgrow it.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import DATABASE_URL


# check_same_thread=False is required because FastAPI may touch the session
# from a different thread than the one that created it. SQLite-specific.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""
    pass


def init_db() -> None:
    """Create tables if they do not yet exist. Safe to call on every startup."""
    # Import models so they are registered on Base.metadata before create_all.
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a session and guarantees it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

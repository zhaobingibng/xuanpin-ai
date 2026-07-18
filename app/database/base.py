"""Database engine, session, and declarative base."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config.settings import get_settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


def _ensure_db_dir(db_path: str) -> None:
    """Create the parent directory for the database file if it doesn't exist."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


# ── Sync ──────────────────────────────────────────────────────

def get_engine():
    """Create and return a synchronous SQLite engine."""
    settings = get_settings()
    _ensure_db_dir(settings.db_path)
    engine = create_engine(
        settings.database_url,
        echo=settings.app_debug,
    )
    # Enable WAL mode for better concurrent read performance
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def get_session_factory(engine=None):
    """Return a sessionmaker bound to the given engine (or default)."""
    if engine is None:
        engine = get_engine()
    return sessionmaker(bind=engine, expire_on_commit=False)


# ── Async ─────────────────────────────────────────────────────

def get_async_engine():
    """Create and return an async SQLite engine (aiosqlite)."""
    settings = get_settings()
    _ensure_db_dir(settings.db_path)
    return create_async_engine(
        settings.async_database_url,
        echo=settings.app_debug,
    )


def get_async_session_factory(engine=None) -> async_sessionmaker[AsyncSession]:
    """Return an async sessionmaker bound to the given engine (or default)."""
    if engine is None:
        engine = get_async_engine()
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

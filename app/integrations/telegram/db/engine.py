"""
app/integrations/telegram/db/engine.py

[ADDITIVE] — Database engine, session factory, and schema initialization.

Uses SQLAlchemy 2.0 synchronous API with SQLite (aiosqlite available for
future async migration). The project uses synchronous FastAPI routes
with run_in_threadpool, so sync SQLAlchemy is the consistent choice.

Database file: data/storage/nexora_telegram.db (configurable via env).

Down-migration (schema rollback):
  DELETE the database file: data/storage/nexora_telegram.db
  All tables are recreated on next startup via create_all_tables().
  For production: individual DROP TABLE statements are listed in
  docs/telegram-persistence.md under "Schema Rollback".
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = str(
    Path(__file__).resolve().parents[5] / "data" / "storage" / "nexora_telegram.db"
)


@dataclass
class DatabaseSettings:
    """Configuration for the Telegram persistence database."""
    db_path: str = field(
        default_factory=lambda: os.environ.get("NEXORA_TELEGRAM_DB_PATH", _DEFAULT_DB_PATH)
    )
    echo_sql: bool = field(
        default_factory=lambda: os.environ.get("NEXORA_DB_ECHO", "false").lower() == "true"
    )
    pool_size: int = 5

    @property
    def url(self) -> str:
        db_url = os.environ.get("NEXORA_DATABASE_URL")
        if db_url:
            return db_url
        return f"sqlite:///{self.db_path}"


# Module-level singletons — initialized once
_engine = None
_SessionFactory = None


def get_engine(settings: DatabaseSettings | None = None):
    """Return the shared SQLAlchemy engine, creating it if needed."""
    global _engine
    if _engine is None:
        cfg = settings or DatabaseSettings()
        
        # Only create directories if using sqlite
        if cfg.url.startswith("sqlite"):
            Path(cfg.db_path).parent.mkdir(parents=True, exist_ok=True)
            
        _engine = create_engine(
            cfg.url,
            echo=cfg.echo_sql,
            connect_args={"check_same_thread": False} if cfg.url.startswith("sqlite") else {},
        )
        
        # Enable WAL mode for SQLite only
        if cfg.url.startswith("sqlite"):
            with _engine.connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.execute(text("PRAGMA foreign_keys=ON"))
                conn.commit()
                
        logger.info("Database engine initialized: %s", "PostgreSQL" if not cfg.url.startswith("sqlite") else cfg.db_path)
    return _engine


def get_session_factory(settings: DatabaseSettings | None = None) -> sessionmaker:
    """Return the shared session factory."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_engine(settings),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _SessionFactory


def get_session(settings: DatabaseSettings | None = None) -> Session:
    """Create and return a new database session. Caller is responsible for closing."""
    return get_session_factory(settings)()


def create_all_tables(settings: DatabaseSettings | None = None) -> None:
    """Create all ORM tables if they don't exist. Safe to call multiple times."""
    from .orm_models import Base
    engine = get_engine(settings)
    Base.metadata.create_all(bind=engine)
    logger.info("All Telegram database tables created/verified.")


def reset_engine() -> None:
    """Reset module-level singletons. Used in tests to get a clean state."""
    global _engine, _SessionFactory
    if _engine:
        _engine.dispose()
    _engine = None
    _SessionFactory = None

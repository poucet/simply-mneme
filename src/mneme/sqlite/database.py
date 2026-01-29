"""Async SQLite engine and session setup."""

from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import event, text

from .models import Base


def _set_sqlite_pragmas(dbapi_conn, connection_record):
    """Configure SQLite for performance and correctness."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB
    cursor.execute("PRAGMA mmap_size=268435456")  # 256MB
    cursor.close()


def create_engine(db_path: Path, *, echo: bool = False) -> AsyncEngine:
    """Create an async SQLAlchemy engine for the given SQLite database path."""
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url, echo=echo)

    # Set pragmas on every raw connection
    event.listen(engine.sync_engine, "connect", _set_sqlite_pragmas)

    return engine


def create_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a session factory bound to the given engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_database(engine: AsyncEngine) -> None:
    """Create all tables from ORM metadata."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_database(engine: AsyncEngine) -> None:
    """Dispose of the engine and all connections."""
    await engine.dispose()

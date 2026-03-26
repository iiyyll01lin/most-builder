"""Async SQLAlchemy engine, session factory, and declarative Base.

Usage in lifespan:
    from ddm_v2.db.database import init_db, Base
    init_db(settings.database_url)

Usage as FastAPI dependency:
    from ddm_v2.db.database import get_session
    async def my_route(session: AsyncSession = Depends(get_session)): ...
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models.

    All SQLModel / SQLAlchemy table classes must inherit from this so that
    ``Base.metadata.create_all()`` and Alembic autogeneration see every table.
    """


# Module-level singletons — populated by init_db(), consumed by get_session().
_engine: AsyncEngine | None = None
_AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None


def init_db(database_url: str) -> None:
    """Create the async engine and session factory from *database_url*.

    Call this **once** during application startup (lifespan event).

    Supported URL schemes:
    - ``postgresql+asyncpg://user:pass@host:5432/dbname``  — production
    - ``sqlite+aiosqlite:///path/to/test.db``              — lightweight tests
    """
    global _engine, _AsyncSessionLocal
    _engine = create_async_engine(
        database_url,
        echo=False,
        future=True,
        # Verify connections retrieved from the pool are live before using them.
        pool_pre_ping=True,
    )
    _AsyncSessionLocal = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a transactional async DB session.

    Commits on successful exit, rolls back on any unhandled exception.
    """
    if _AsyncSessionLocal is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    async with _AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_engine_connection() -> AsyncIterator[AsyncConnection]:
    """Yield a raw async engine connection.

    Primarily used by the Alembic migration runner (``alembic upgrade head``
    called inside the FastAPI lifespan event).
    """
    if _engine is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    async with _engine.begin() as conn:
        yield conn


def get_engine() -> AsyncEngine:
    """Return the live engine (raises if not yet initialised)."""
    if _engine is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory (raises if not yet initialised).

    Stored on ``app.state.pg_session_factory`` during lifespan startup so
    that WebSocket handlers and background tasks can create their own sessions
    independently of the normal ``get_session`` HTTP dependency.
    """
    if _AsyncSessionLocal is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _AsyncSessionLocal

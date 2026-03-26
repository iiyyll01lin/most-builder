import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Import all ORM models so Alembic autogenerate can detect every table.
# The wildcard import from ddm_v2.models.domain registers all Row classes
# with Base.metadata via their class declarations.
# ---------------------------------------------------------------------------
from ddm_v2.db.database import Base  # noqa: E402
import ddm_v2.models.domain  # noqa: E402,F401 — registers all 25 tables with Base.metadata

target_metadata = Base.metadata


def _get_url() -> str:
    """Return the database URL for Alembic.

    Priority:
    1. ``DDM_DATABASE_URL`` environment variable (set by docker-compose)
    2. Hard-coded fallback (local dev with the test postgres)

    The async engine used online requires ``asyncpg``; offline mode (SQL
    generation) uses ``psycopg2`` for dialect detection only.
    """
    return os.getenv(
        "DDM_DATABASE_URL",
        "postgresql+asyncpg://ddm:ddm_secret@localhost:5432/ddm",
    )


def _get_sync_url() -> str:
    """Synchronous driver URL for offline SQL generation."""
    return _get_url().replace("+asyncpg", "+psycopg2")

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script generation)."""
    url = _get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations online using the async engine."""
    configuration = {
        **config.get_section(config.config_ini_section, {}),
        "sqlalchemy.url": _get_url(),  # asyncpg URL for async engine
    }
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

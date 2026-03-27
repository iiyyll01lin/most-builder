"""seed_runner.py — callable as ``python -m ddm_v2.seed_runner``

Invokes the Phase 10 ultimate demo seed inside the running Docker container.
The DDM_DATABASE_URL environment variable must point to the live PostgreSQL
instance (set automatically by docker-compose.yml).

Usage (from Makefile):
    docker compose exec ddm-v2 python -m ddm_v2.seed_runner
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def _run() -> None:
    db_url = os.environ.get(
        "DDM_DATABASE_URL",
        "postgresql+asyncpg://ddm:ddm_secret@postgres:5432/ddm",
    )
    logger.info("Connecting to: %s", db_url.split("@")[-1])  # redact credentials

    # Populate Base.metadata
    import ddm_v2.models.domain  # noqa: F401

    from ddm_v2.db.database import get_session_factory, init_db
    from ddm_v2.seeds import seed_ultimate_demo

    init_db(db_url)
    sf = get_session_factory()

    async with sf() as session:
        result = await seed_ultimate_demo(session)
        await session.commit()

    if result.get("skipped"):
        logger.warning("⚠️  Seed skipped: %s", result["reason"])
    else:
        counts = result["inserted"]
        logger.info("✅ Ultimate demo data inserted:")
        for key, count in counts.items():
            logger.info("   %-22s %s", key + ":", count)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

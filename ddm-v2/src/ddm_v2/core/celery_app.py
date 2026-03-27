"""Celery application factory — Phase 6: Distributed ML Task Queue.

Architecture & PostgreSQL pool strategy
----------------------------------------
Celery uses ``prefork`` concurrency: every worker subprocess is a separate OS
process. The FastAPI ``asyncpg`` pool lives in the parent process's asyncio
event loop and **must never be shared across fork()**. Doing so would clone the
raw TCP socket file-descriptors, causing two processes to write to the same
PostgreSQL connection stream simultaneously, silently corrupting the wire-
protocol.

Our solution — lazy, per-task engine init:

1. ``@worker_process_init.connect`` fires exactly once after each worker
   *subprocess* forks.  We record the process PID but intentionally do NOT
   pre-create a pool here, because asyncio event loops are also per-process and
   one has not been started yet at that signal point.

2. Each Celery task wraps its body in ``asyncio.run(_async_body(...))``.  This
   creates a fresh event loop *and* a new ``asyncpg`` connection pool scoped to
   that single task invocation.  For a heavy ML inference task that runs for
   tens of seconds, the 2 ms overhead of loop + pool creation is negligible.

3. Pool parameters are intentionally small (``pool_size=2, max_overflow=0``):
   the analysis task needs at most 2 DB round-trips (read upload record, write
   results).  Limiting size prevents connection exhaustion when N workers run
   in parallel.

4. No URL transformation needed: ``DDM_DATABASE_URL`` already carries the
   ``postgresql+asyncpg://`` scheme, which SQLAlchemy's async engine accepts
   directly inside ``asyncio.run()``.
"""
from __future__ import annotations

import os

from celery import Celery
from celery.signals import worker_process_init

from ddm_v2.settings import get_settings

# ---------------------------------------------------------------------------
# Build the Celery application
# ---------------------------------------------------------------------------

_settings = get_settings()

celery_app = Celery(
    "ddm_v2",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=["ddm_v2.services.vision_service"],
)

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Time limits: ML inference can take a while; give it up to 10 minutes
    # before a hard-kill.
    task_soft_time_limit=480,     # 8 min — raises SoftTimeLimitExceeded (graceful)
    task_time_limit=600,          # 10 min — SIGKILL
    # Acknowledgement after task execution so a worker crash does not silently
    # drop a task mid-flight.
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # fetch one task at a time per worker process
    # Result expiry — keep results 24 h for the polling endpoint
    result_expires=86400,
    # Timezone
    timezone="UTC",
    enable_utc=True,
)


# ---------------------------------------------------------------------------
# Worker lifecycle signal: log that this subprocess is ready
# ---------------------------------------------------------------------------

@worker_process_init.connect
def _on_worker_process_init(**kwargs: object) -> None:
    """Called once in each Celery worker *process* after forking.

    We log the PID so operators can corroborate Celery worker logs with OS
    process monitors.  Database connections are intentionally NOT opened here;
    they are created fresh inside each ``asyncio.run()`` call to guarantee that
    asyncpg's transport layer is always aligned with the event loop that owns it.
    """
    pid = os.getpid()
    print(f"[DDM Celery] worker process initialised (pid={pid})")

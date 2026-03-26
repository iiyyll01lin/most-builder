from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ddm_v2.api.routes.ai import router as ai_router
from ddm_v2.api.routes.auth import router as auth_router
from ddm_v2.api.routes.bff import router as bff_router
from ddm_v2.api.routes.level import router as level_router
from ddm_v2.api.routes.master import router as master_router
from ddm_v2.api.routes.most import router as most_router
from ddm_v2.api.routes.simulation import router as simulation_router
from ddm_v2.api.routes.sop import router as sop_router
from ddm_v2.api.routes.system import router as system_router
from ddm_v2.db.database import get_session_factory, init_db
from ddm_v2.schemas import ErrorCode, ErrorDetail
from ddm_v2.settings import Settings, get_settings

_HTTP_STATUS_TO_ERROR_CODE: dict[int, ErrorCode] = {
    status.HTTP_400_BAD_REQUEST: ErrorCode.bad_request,
    status.HTTP_401_UNAUTHORIZED: ErrorCode.unauthorized,
    status.HTTP_403_FORBIDDEN: ErrorCode.forbidden,
    status.HTTP_404_NOT_FOUND: ErrorCode.not_found,
    status.HTTP_409_CONFLICT: ErrorCode.conflict,
    status.HTTP_422_UNPROCESSABLE_ENTITY: ErrorCode.validation_error,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the async database engine, run migrations, and seed master data."""
    db_url: str = app.state.database_url
    init_db(db_url)
    app.state.pg_session_factory = get_session_factory()

    import ddm_v2.models.domain  # noqa: F401
    from ddm_v2.db.database import _engine
    from ddm_v2.models.domain import Base  # noqa: F401 — ensures Base.metadata is populated

    if "sqlite" in db_url:
        # Test mode: create tables directly without Alembic to keep tests fast
        # and dependency-free.
        async with _engine.begin() as conn:  # type: ignore[union-attr]
            await conn.run_sync(Base.metadata.create_all)
    else:
        # Production / integration: run Alembic migrations idempotently so every
        # startup ensures the schema is at head revision.
        from pathlib import Path as _Path

        import alembic.command
        import alembic.config

        alembic_cfg = alembic.config.Config(str(_Path(__file__).resolve().parents[3] / "alembic.ini"))
        # Override the URL; Alembic env.py reads DDM_DATABASE_URL from os.environ
        import os as _os
        _os.environ.setdefault("DDM_DATABASE_URL", db_url)
        await asyncio.to_thread(alembic.command.upgrade, alembic_cfg, "head")

    # Seed master data on first boot (when the users table is empty).
    from sqlalchemy import func, select

    from ddm_v2.models.domain import UserRow
    from ddm_v2.repositories.postgres_store import PostgresStore

    async with app.state.pg_session_factory() as session:
        count = (await session.execute(select(func.count(UserRow.username)))).scalar_one()
        if count == 0:
            store = PostgresStore(session)
            await store._seed_from_defaults()
            await session.commit()

    yield

    # Dispose the engine on shutdown to cleanly close all pool connections.
    if _engine is not None:
        await _engine.dispose()


def create_app(
    db_path: Path | None = None,
    settings: Settings | None = None,
    database_url: str | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(title=app_settings.app_name, version=app_settings.app_version, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_allow_origins,
        allow_credentials=app_settings.cors_allow_credentials,
        allow_methods=app_settings.cors_allow_methods,
        allow_headers=app_settings.cors_allow_headers,
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        error_code = _HTTP_STATUS_TO_ERROR_CODE.get(exc.status_code, ErrorCode.internal_error)
        body = ErrorDetail(error_code=error_code, message=exc.detail, detail=None)
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(loc) for loc in err["loc"] if loc != "body"), "message": err["msg"]}
            for err in exc.errors()
        ]
        body = ErrorDetail(
            error_code=ErrorCode.validation_error,
            message="Request validation failed. Check the 'detail' field for per-field errors.",
            detail=errors,
        )
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=body.model_dump())

    app.state.settings = app_settings
    # Store a custom database URL override (used in tests with sqlite+aiosqlite://)
    app.state.database_url = database_url or app_settings.database_url

    app.include_router(ai_router)
    app.include_router(auth_router)
    app.include_router(bff_router)
    app.include_router(master_router)
    app.include_router(most_router)
    app.include_router(level_router)
    app.include_router(sop_router)
    app.include_router(simulation_router)
    app.include_router(system_router)

    app.mount("/static", StaticFiles(directory=app_settings.static_dir), name="static")

    @app.get("/")
    def root() -> FileResponse:
        return FileResponse(app_settings.static_dir / "validation_shell.html")

    @app.get("/control-console")
    def control_console() -> FileResponse:
        return FileResponse(app_settings.static_dir / "control_console.html")

    return app


app = create_app()


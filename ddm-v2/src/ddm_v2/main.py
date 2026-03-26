from __future__ import annotations

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
from ddm_v2.repositories.store import JsonStore
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


def create_app(db_path: Path | None = None, settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(title=app_settings.app_name, version=app_settings.app_version)
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
    app.state.store = JsonStore(db_path or app_settings.db_path)

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

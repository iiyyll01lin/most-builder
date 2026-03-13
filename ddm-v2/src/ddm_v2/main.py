from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ddm_v2.api.routes.auth import router as auth_router
from ddm_v2.api.routes.level import router as level_router
from ddm_v2.api.routes.master import router as master_router
from ddm_v2.api.routes.most import router as most_router
from ddm_v2.api.routes.simulation import router as simulation_router
from ddm_v2.api.routes.sop import router as sop_router
from ddm_v2.api.routes.system import router as system_router
from ddm_v2.repositories.store import JsonStore
from ddm_v2.settings import APP_NAME, APP_VERSION, DB_PATH, STATIC_DIR


def create_app(db_path: Path | None = None) -> FastAPI:
    app = FastAPI(title=APP_NAME, version=APP_VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.store = JsonStore(db_path or DB_PATH)

    app.include_router(auth_router)
    app.include_router(master_router)
    app.include_router(most_router)
    app.include_router(level_router)
    app.include_router(sop_router)
    app.include_router(simulation_router)
    app.include_router(system_router)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def root() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/control-console")
    def control_console() -> FileResponse:
        return FileResponse(STATIC_DIR / "control_console.html")

    return app


app = create_app()

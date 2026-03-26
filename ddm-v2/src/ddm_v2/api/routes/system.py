from __future__ import annotations

try:
    from datetime import UTC
except ImportError:
    import datetime as _dt
    UTC = _dt.timezone.utc
from datetime import datetime

from fastapi import APIRouter, Depends

from ddm_v2.api.dependencies import get_current_user, get_store, require_roles
from ddm_v2.repositories.postgres_store import PostgresStore
from ddm_v2.schemas import AuditAction, UserRole
from ddm_v2.settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/projects")
async def projects(store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return await store.list_collection("projects")


@router.get("/projects/{project_id}")
async def project_detail(project_id: str, store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    project = await store.find_by_id("projects", project_id)
    if project is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/audit/logs")
async def audit_logs(
    limit: int = 100,
    entity_type: str | None = None,
    page: int | None = None,
    size: int = 50,
    store: PostgresStore = Depends(get_store),
    user: dict = Depends(get_current_user),
):
    from fastapi.responses import JSONResponse

    logs = list(await store.list_collection("audit_logs"))
    if user["role"] != UserRole.manager.value:
        logs = [entry for entry in logs if entry["user_id"] == user["id"]]
    if entity_type:
        logs = [entry for entry in logs if entry["entity_type"] == entity_type]
    logs.sort(key=lambda entry: entry["timestamp"], reverse=True)
    total = len(logs)

    if page is not None:
        size = max(1, min(size, 200))
        offset = (page - 1) * size
        sliced = logs[offset : offset + size]
        import math
        pages = math.ceil(total / size) if size else 1
        return {"items": sliced, "total": total, "page": page, "size": size, "pages": pages}

    # Legacy behaviour: bare list with X-Total-Count header
    sliced = logs[:limit]
    return JSONResponse(
        content=sliced,
        headers={"X-Total-Count": str(total)},
    )


@router.get("/health")
def health():
    return {"status": "healthy", "version": get_settings().app_version, "timestamp": datetime.now(UTC).isoformat()}


@router.get("/db/status")
async def db_status(store: PostgresStore = Depends(get_store), _: dict = Depends(get_current_user)):
    counts = await store.get_collection_counts()
    return {
        "persistent_file": "postgresql",
        "file_exists": True,
        "file_size_bytes": 0,
        "last_modified": None,
        "collections": counts,
    }


@router.post("/db/save")
async def db_save(store: PostgresStore = Depends(get_store), _: dict = Depends(require_roles(UserRole.manager))):
    await store.save()
    return {"status": "success", "message": "Database saved (PostgreSQL — no-op)", "path": "postgresql"}


@router.post("/db/load")
async def db_load(store: PostgresStore = Depends(get_store), _: dict = Depends(require_roles(UserRole.manager))):
    await store.load()
    return {"status": "success", "message": "Database loaded (PostgreSQL — no-op)", "path": "postgresql"}


@router.get("/db/export")
async def db_export(store: PostgresStore = Depends(get_store), _: dict = Depends(require_roles(UserRole.manager))):
    return await store.export_state()


@router.delete("/db/reset")
async def db_reset(store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager))):
    await store.reset()
    await store.audit(user, AuditAction.reset, "database", "runtime", "Reset database to defaults")
    return {"status": "success", "message": "Database reset to defaults"}

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from ddm_v2.api.dependencies import get_current_user, get_store, require_roles
from ddm_v2.repositories.store import JsonStore
from ddm_v2.schemas import AuditAction, UserRole
from ddm_v2.settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/projects")
def projects(store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return store.list_collection("projects")


@router.get("/projects/{project_id}")
def project_detail(project_id: str, store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    project = store.find_by_id("projects", project_id)
    if project is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/audit/logs")
def audit_logs(
    limit: int = 100,
    entity_type: str | None = None,
    page: int | None = None,
    size: int = 50,
    store: JsonStore = Depends(get_store),
    user: dict = Depends(get_current_user),
):
    from fastapi.responses import JSONResponse

    logs = list(store.list_collection("audit_logs"))
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
def db_status(store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    db_path = store.db_path
    exists = db_path.exists()
    return {
        "persistent_file": str(db_path),
        "file_exists": exists,
        "file_size_bytes": db_path.stat().st_size if exists else 0,
        "last_modified": datetime.fromtimestamp(db_path.stat().st_mtime, tz=UTC).isoformat() if exists else None,
        "collections": {key: len(value) if isinstance(value, list) else len(value) for key, value in store.state.items() if isinstance(value, (list, dict))},
    }


@router.post("/db/save")
def db_save(store: JsonStore = Depends(get_store), _: dict = Depends(require_roles(UserRole.manager))):
    store.save()
    return {"status": "success", "message": "Database saved", "path": str(store.db_path)}


@router.post("/db/load")
def db_load(store: JsonStore = Depends(get_store), _: dict = Depends(require_roles(UserRole.manager))):
    store.load()
    return {"status": "success", "message": "Database loaded", "path": str(store.db_path)}


@router.get("/db/export")
def db_export(store: JsonStore = Depends(get_store), _: dict = Depends(require_roles(UserRole.manager))):
    return store.state


@router.delete("/db/reset")
def db_reset(store: JsonStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager))):
    store.reset()
    store.audit(user, AuditAction.reset, "database", "runtime", "Reset database to defaults")
    return {"status": "success", "message": "Database reset to defaults"}

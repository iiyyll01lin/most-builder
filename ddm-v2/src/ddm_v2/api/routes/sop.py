from __future__ import annotations

try:
    from datetime import UTC
except ImportError:
    import datetime as _dt
    UTC = _dt.timezone.utc
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ddm_v2.api.dependencies import get_current_user, get_store, require_roles
from ddm_v2.repositories.postgres_store import PostgresStore
from ddm_v2.schemas import (
    AuditAction,
    SOPCreateRequest,
    SOPStatus,
    SOPUpdateStatusRequest,
    UserRole,
)

router = APIRouter(prefix="/api/v1/sop", tags=["sop"])


ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    SOPStatus.draft.value: {SOPStatus.reviewed.value, SOPStatus.published.value},
    SOPStatus.reviewed.value: {SOPStatus.published.value},
    SOPStatus.published.value: set(),
}


@router.get("/versions")
async def list_versions(project_id: str | None = None, store: PostgresStore = Depends(get_store), user: dict = Depends(get_current_user)):
    versions = list(await store.list_collection("sop_versions"))
    if project_id:
        versions = [version for version in versions if version["project_id"] == project_id]
    if user["role"] == UserRole.operator.value:
        versions = [version for version in versions if version["status"] == SOPStatus.published.value]
    return versions


@router.post("/versions", status_code=201)
async def create_version(payload: SOPCreateRequest, store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer))):
    version = {
        "id": store.new_id("sop"),
        "project_id": payload.project_id,
        "version_no": payload.version_no,
        "status": SOPStatus.draft.value,
        "actions": [],
        "created_by": user["id"],
        "created_at": datetime.now(UTC).isoformat(),
        "reviewed_by": None,
        "reviewed_at": None,
        "published_by": None,
        "published_at": None,
    }
    for action in payload.actions:
        action_payload = action.model_dump()
        action_payload["id"] = action_payload.get("id") or store.new_id("act")
        version["actions"].append(action_payload)
    version = await store.upsert_collection_item("sop_versions", version)
    await store.audit(user, AuditAction.create, "sop", version["id"], f"Created SOP {version['version_no']}", new_value=version)
    return version


@router.get("/versions/{sop_id}")
async def get_version(sop_id: str, store: PostgresStore = Depends(get_store), user: dict = Depends(get_current_user)):
    version = await store.find_by_id("sop_versions", sop_id)
    if version is None:
        raise HTTPException(status_code=404, detail="SOP version not found")
    if user["role"] == UserRole.operator.value and version["status"] != SOPStatus.published.value:
        raise HTTPException(status_code=403, detail="Access denied")
    return version


@router.put("/versions/{sop_id}/status")
async def update_status(sop_id: str, payload: SOPUpdateStatusRequest, store: PostgresStore = Depends(get_store), user: dict = Depends(get_current_user)):
    version = await store.find_by_id("sop_versions", sop_id)
    if version is None:
        raise HTTPException(status_code=404, detail="SOP version not found")
    previous = version["status"]
    target = payload.status.value
    if target != previous and target not in ALLOWED_STATUS_TRANSITIONS.get(previous, set()):
        raise HTTPException(status_code=400, detail=f"Invalid SOP status transition: {previous} -> {target}")
    if payload.status == SOPStatus.reviewed and user["role"] == UserRole.operator.value:
        raise HTTPException(status_code=403, detail="Operators cannot review SOPs")
    if payload.status == SOPStatus.published and user["role"] != UserRole.manager.value:
        raise HTTPException(status_code=403, detail="Only managers can publish SOPs")
    version["status"] = target
    if payload.status == SOPStatus.reviewed:
        version["reviewed_by"] = user["id"]
        version["reviewed_at"] = datetime.now(UTC).isoformat()
    if payload.status == SOPStatus.published:
        version["published_by"] = user["id"]
        version["published_at"] = datetime.now(UTC).isoformat()
    version = await store.upsert_collection_item("sop_versions", version)
    audit_action = AuditAction.review if payload.status == SOPStatus.reviewed else AuditAction.publish
    await store.audit(user, audit_action, "sop", sop_id, f"Changed SOP status {previous} -> {payload.status.value}", old_value={"status": previous}, new_value={"status": payload.status.value})
    return version


@router.put("/versions/{sop_id}/actions")
async def update_actions(sop_id: str, payload: list[dict], store: PostgresStore = Depends(get_store), user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer))):
    version = await store.find_by_id("sop_versions", sop_id)
    if version is None:
        raise HTTPException(status_code=404, detail="SOP version not found")
    if version["status"] != SOPStatus.draft.value:
        raise HTTPException(status_code=400, detail="Only Draft SOP can be modified")
    new_actions = []
    for action in payload:
        action["id"] = action.get("id") or store.new_id("act")
        new_actions.append(action)
    version["actions"] = new_actions
    version = await store.upsert_collection_item("sop_versions", version)
    await store.audit(user, AuditAction.update, "sop", sop_id, f"Updated {len(version['actions'])} SOP actions", new_value={"count": len(version['actions'])})
    return version


from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ddm_v2.api.dependencies import get_current_user, get_store, require_roles
from ddm_v2.repositories.store import JsonStore
from ddm_v2.schemas import AuditAction, LevelSystemSaveRequest, LevelSystemSyncRequest, UserRole
from ddm_v2.services.level_service import build_level_entries, build_precedence_graph


router = APIRouter(prefix="/api/v1/level-system", tags=["level-system"])


def _project_sop_actions(store: JsonStore, project_id: str, sop_version_id: str | None = None) -> tuple[dict | None, list[dict]]:
    candidates = [version for version in store.list_collection("sop_versions") if version["project_id"] == project_id]
    if sop_version_id:
        candidates = [version for version in candidates if version["id"] == sop_version_id]
    draft_candidates = [version for version in candidates if version["status"] == "Draft"]
    target = (draft_candidates[-1] if draft_candidates else None) or (candidates[-1] if candidates else None)
    return target, list(target.get("actions", [])) if target else []


@router.get("/templates")
def templates(store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return store.list_collection("level_system_templates")


@router.get("/guidelines")
def guidelines(store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    return store.list_collection("level_guidelines")


@router.get("/{project_id}")
def get_entries(project_id: str, store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    project = store.find_by_id("projects", project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _, actions = _project_sop_actions(store, project_id)
    existing = store.state.setdefault("level_entries", {}).get(project_id, [])
    entries = build_level_entries(project_id, actions, existing)
    return {"project_id": project_id, "project_name": project["name"], "entries": entries, "total_count": len(entries)}


@router.post("/sync")
def sync_entries(
    payload: LevelSystemSyncRequest,
    store: JsonStore = Depends(get_store),
    user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer)),
):
    _, actions = _project_sop_actions(store, payload.project_id, payload.sop_version_id)
    if not actions:
        return {"message": "No SOP actions found for this project.", "project_id": payload.project_id, "total_entries": 0, "synced": 0}
    existing = store.state.setdefault("level_entries", {}).get(payload.project_id, [])
    merged = build_level_entries(payload.project_id, actions, existing)
    store.state["level_entries"][payload.project_id] = [
        {
            "id": entry["id"],
            "action_id": entry["action_id"],
            "difficulty_factor": entry["difficulty_factor"],
            "number_tag": entry["number_tag"],
            "number_count": entry["number_count"],
            "main_seq": entry["main_seq"],
            "order_seq": entry["order_seq"],
            "cub_group": entry["cub_group"],
            "machine_count": entry["machine_count"],
            "operator_count": entry["operator_count"],
            "status_label": entry["status_label"],
            "sort_order": entry["sort_order"],
        }
        for entry in merged
    ]
    store.save()
    store.audit(user, AuditAction.update, "level-system", payload.project_id, "Synced level entries", new_value={"count": len(merged)})
    return {"message": f"Synced {len(merged)} entries", "project_id": payload.project_id, "total_entries": len(merged), "synced": len(merged)}


@router.post("/save")
def save_entries(
    payload: LevelSystemSaveRequest,
    store: JsonStore = Depends(get_store),
    user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer)),
):
    target = []
    for entry in payload.entries:
        body = entry.model_dump()
        body["id"] = f"lvl-{payload.project_id}-{entry.action_id}"
        target.append(body)
    store.state.setdefault("level_entries", {})[payload.project_id] = target
    store.save()
    store.audit(user, AuditAction.update, "level-system", payload.project_id, "Saved level entries", new_value={"count": len(target)})
    return {"message": "Level System saved successfully", "project_id": payload.project_id, "updated": len(target), "created": 0}


@router.post("/generate-graph")
def generate_graph(project_id: str, store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    existing = store.state.setdefault("level_entries", {}).get(project_id, [])
    _, actions = _project_sop_actions(store, project_id)
    if not existing and not actions:
        raise HTTPException(status_code=404, detail="No level entries found")
    merged = build_level_entries(project_id, actions, existing)
    graph = build_precedence_graph(merged)
    graph["project_id"] = project_id
    return graph

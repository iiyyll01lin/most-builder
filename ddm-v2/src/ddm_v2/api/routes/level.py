from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ddm_v2.api.dependencies import get_current_user, get_store, require_roles
from ddm_v2.repositories.store import JsonStore
from ddm_v2.schemas import AuditAction, LevelSystemSaveRequest, LevelSystemSyncRequest, UserRole
from ddm_v2.services.level_service import build_level_entries, build_precedence_graph


router = APIRouter(prefix="/api/v1/level-system", tags=["level-system"])


def _level_scope_key(project_id: str, sop_version_id: str | None) -> str:
    return f"{project_id}::{sop_version_id or '__default__'}"


def _derive_level_tag(entry: dict) -> str:
    if entry.get("status_label"):
        return str(entry["status_label"])
    if entry.get("main_seq") and entry.get("order_seq"):
        return f"{entry['main_seq']}.{entry['order_seq']}"
    if entry.get("main_seq"):
        return f"MAIN-{entry['main_seq']}"
    if entry.get("cub_group"):
        return f"CUB-{entry['cub_group']}"
    if entry.get("number_tag"):
        suffix = entry.get("number_count")
        return f"{entry['number_tag']}{suffix if suffix is not None else ''}"
    return ""


def _find_workspace(store: JsonStore, project_id: str, sop_version_id: str | None) -> dict | None:
    candidates = [workspace for workspace in store.list_collection("most_workspaces") if workspace.get("project_id") == project_id]
    if sop_version_id:
        for workspace in candidates:
            if workspace.get("sop_version_id") == sop_version_id:
                return workspace
    return candidates[-1] if candidates else None


def _propagate_level_metadata(store: JsonStore, project_id: str, sop_version_id: str | None, entries: list[dict]) -> None:
    if not sop_version_id:
        return
    version = store.find_by_id("sop_versions", sop_version_id)
    if version is None:
        return

    by_action_id = {entry["action_id"]: entry for entry in entries}
    step_level_map: dict[str, dict] = {}
    for action in version.get("actions", []):
        entry = by_action_id.get(action.get("id"))
        if entry is None:
            continue
        level_tag = _derive_level_tag(entry)
        action["level_tag"] = level_tag
        params = action.setdefault("params", {})
        params["_level"] = {
            "project_id": project_id,
            "sop_version_id": sop_version_id,
            "difficulty_factor": entry.get("difficulty_factor"),
            "adjusted_ct": entry.get("adjusted_ct"),
            "effective_cub_ct": entry.get("effective_cub_ct"),
            "main_seq": entry.get("main_seq"),
            "order_seq": entry.get("order_seq"),
            "cub_group": entry.get("cub_group"),
            "number_tag": entry.get("number_tag"),
            "number_count": entry.get("number_count"),
            "status_label": entry.get("status_label"),
            "sort_order": entry.get("sort_order"),
        }
        most_meta = params.get("_most") or {}
        step_id = most_meta.get("step_id")
        if step_id:
            step_level_map[str(step_id)] = {"level_tag": level_tag, "level_meta": params["_level"]}

    workspace = _find_workspace(store, project_id, sop_version_id)
    if workspace is None:
        return

    for action in workspace.get("actions", []):
        entry = by_action_id.get(action.get("id"))
        if entry is None:
            continue
        level_tag = _derive_level_tag(entry)
        action["level_tag"] = level_tag
        params = action.setdefault("params", {})
        params["_level"] = {
            "project_id": project_id,
            "sop_version_id": sop_version_id,
            "difficulty_factor": entry.get("difficulty_factor"),
            "adjusted_ct": entry.get("adjusted_ct"),
            "effective_cub_ct": entry.get("effective_cub_ct"),
            "main_seq": entry.get("main_seq"),
            "order_seq": entry.get("order_seq"),
            "cub_group": entry.get("cub_group"),
            "number_tag": entry.get("number_tag"),
            "number_count": entry.get("number_count"),
            "status_label": entry.get("status_label"),
            "sort_order": entry.get("sort_order"),
        }
        most_meta = params.get("_most") or {}
        step_id = most_meta.get("step_id")
        if step_id:
            step_level_map[str(step_id)] = {"level_tag": level_tag, "level_meta": params["_level"]}

    for step in workspace.get("steps", []):
        step_meta = step_level_map.get(str(step.get("id")))
        if step_meta is None:
            continue
        step["level_tag"] = step_meta["level_tag"]
        step_params = step.setdefault("params", {})
        step_params["_level"] = step_meta["level_meta"]


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
def get_entries(project_id: str, sop_version_id: str | None = None, store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    project = store.find_by_id("projects", project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    target_version, actions = _project_sop_actions(store, project_id, sop_version_id)
    resolved_sop_version_id = sop_version_id or (target_version.get("id") if target_version else None)
    scope_key = _level_scope_key(project_id, resolved_sop_version_id)
    existing = store.state.setdefault("level_entries", {}).get(scope_key)
    if existing is None and sop_version_id is None:
        existing = store.state.setdefault("level_entries", {}).get(project_id, [])
    existing = existing or []
    entries = build_level_entries(project_id, actions, existing)
    return {
        "project_id": project_id,
        "project_name": project["name"],
        "sop_version_id": resolved_sop_version_id,
        "entries": entries,
        "total_count": len(entries),
    }


@router.post("/sync")
def sync_entries(
    payload: LevelSystemSyncRequest,
    store: JsonStore = Depends(get_store),
    user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer)),
):
    target_version, actions = _project_sop_actions(store, payload.project_id, payload.sop_version_id)
    if not actions:
        return {"message": "No SOP actions found for this project.", "project_id": payload.project_id, "total_entries": 0, "synced": 0}
    resolved_sop_version_id = payload.sop_version_id or (target_version.get("id") if target_version else None)
    scope_key = _level_scope_key(payload.project_id, resolved_sop_version_id)
    existing = store.state.setdefault("level_entries", {}).get(scope_key)
    if existing is None and payload.sop_version_id is None:
        existing = store.state.setdefault("level_entries", {}).get(payload.project_id, [])
    existing = existing or []
    merged = build_level_entries(payload.project_id, actions, existing)
    store.state["level_entries"][scope_key] = [
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
    _propagate_level_metadata(store, payload.project_id, resolved_sop_version_id, merged)
    store.save()
    store.audit(user, AuditAction.update, "level-system", payload.project_id, "Synced level entries", new_value={"count": len(merged), "sop_version_id": resolved_sop_version_id})
    return {"message": f"Synced {len(merged)} entries", "project_id": payload.project_id, "sop_version_id": resolved_sop_version_id, "total_entries": len(merged), "synced": len(merged)}


@router.post("/save")
def save_entries(
    payload: LevelSystemSaveRequest,
    store: JsonStore = Depends(get_store),
    user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer)),
):
    target_version, actions = _project_sop_actions(store, payload.project_id, payload.sop_version_id)
    resolved_sop_version_id = payload.sop_version_id or (target_version.get("id") if target_version else None)
    scope_key = _level_scope_key(payload.project_id, resolved_sop_version_id)
    action_seconds = {action["id"]: action.get("seconds", 0) for action in actions}
    target = []
    for entry in payload.entries:
        body = entry.model_dump()
        body["id"] = f"lvl-{payload.project_id}-{resolved_sop_version_id or 'default'}-{entry.action_id}"
        body["adjusted_ct"] = round(action_seconds.get(entry.action_id, 0) * body["difficulty_factor"], 2)
        divisor = max(body["machine_count"], body["operator_count"])
        body["effective_cub_ct"] = round(body["adjusted_ct"] / divisor, 2) if body.get("cub_group") else None
        target.append(body)
    store.state.setdefault("level_entries", {})[scope_key] = target
    _propagate_level_metadata(store, payload.project_id, resolved_sop_version_id, target)
    store.save()
    store.audit(user, AuditAction.update, "level-system", payload.project_id, "Saved level entries", new_value={"count": len(target), "sop_version_id": resolved_sop_version_id})
    return {
        "message": "Level System saved successfully",
        "project_id": payload.project_id,
        "sop_version_id": resolved_sop_version_id,
        "updated": len(target),
        "created": 0,
    }


@router.post("/generate-graph")
def generate_graph(project_id: str, sop_version_id: str | None = None, store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    target_version, actions = _project_sop_actions(store, project_id, sop_version_id)
    resolved_sop_version_id = sop_version_id or (target_version.get("id") if target_version else None)
    scope_key = _level_scope_key(project_id, resolved_sop_version_id)
    existing = store.state.setdefault("level_entries", {}).get(scope_key)
    if existing is None and sop_version_id is None:
        existing = store.state.setdefault("level_entries", {}).get(project_id, [])
    existing = existing or []
    if not existing and not actions:
        raise HTTPException(status_code=404, detail="No level entries found")
    merged = build_level_entries(project_id, actions, existing)
    graph = build_precedence_graph(merged)
    graph["project_id"] = project_id
    graph["sop_version_id"] = resolved_sop_version_id
    return graph

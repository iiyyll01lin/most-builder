from __future__ import annotations

from copy import deepcopy

from fastapi import APIRouter, Depends, HTTPException

from ddm_v2.api.dependencies import get_current_user, get_store, require_roles
from ddm_v2.repositories.store import JsonStore
from ddm_v2.schemas import (
    AuditAction,
    GloveCheckRequest,
    GloveCheckResponse,
    MINamingValidationRequest,
    MINamingValidationResponse,
    MOSTCalculateRequest,
    MOSTWorkspaceImportRequest,
    MOSTWorkspaceSaveRequest,
    UserRole,
)
from ddm_v2.services.most_workspace_service import build_workspace_snapshot
from ddm_v2.services.level_service import validate_level_tags
from ddm_v2.services.most_service import calculate_workflow


router = APIRouter(prefix="/api/v1", tags=["most"])


def _ensure_project_exists(store: JsonStore, project_id: str) -> None:
    if store.find_by_id("projects", project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")


def _find_workspace(store: JsonStore, project_id: str, sop_version_id: str | None = None) -> dict | None:
    candidates = [workspace for workspace in store.list_collection("most_workspaces") if workspace.get("project_id") == project_id]
    if sop_version_id:
        for workspace in candidates:
            if workspace.get("sop_version_id") == sop_version_id:
                return workspace
    return candidates[-1] if candidates else None


def _empty_workspace(project_id: str, sop_version_id: str | None = None) -> dict:
    return {
        "id": None,
        "project_id": project_id,
        "sop_version_id": sop_version_id,
        "saved_at": None,
        "version": 1,
        "steps": [],
        "wi_components": [],
        "selected_step_ids": [],
        "summary": {"total_tmu": 0, "total_seconds": 0.0, "step_count": 0, "component_count": 0},
        "actions": [],
    }


@router.post("/most/calculate")
def calculate(payload: MOSTCalculateRequest, _: dict = Depends(get_current_user)):
    return calculate_workflow(payload.steps)


@router.get("/most/workspaces/{project_id}")
def get_workspace(project_id: str, sop_version_id: str | None = None, store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    _ensure_project_exists(store, project_id)
    workspace = _find_workspace(store, project_id, sop_version_id)
    return deepcopy(workspace) if workspace else _empty_workspace(project_id, sop_version_id)


@router.put("/most/workspaces/{project_id}")
def save_workspace(
    project_id: str,
    payload: MOSTWorkspaceSaveRequest,
    store: JsonStore = Depends(get_store),
    user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer)),
):
    _ensure_project_exists(store, project_id)
    existing = _find_workspace(store, project_id, payload.sop_version_id)
    snapshot = build_workspace_snapshot(
        project_id=project_id,
        sop_version_id=payload.sop_version_id,
        raw_steps=payload.steps,
        raw_wi_components=payload.wi_components,
        selected_step_ids=payload.selected_step_ids,
        workspace_id=existing.get("id") if existing else store.new_id("mostws"),
        glove_rules=store.list_collection("glove_rules"),
    )
    snapshot["id"] = snapshot.get("id") or store.new_id("mostws")
    if existing:
        existing_index = store.list_collection("most_workspaces").index(existing)
        store.list_collection("most_workspaces")[existing_index] = snapshot
        action = AuditAction.update
        description = f"Updated MOST workspace for project {project_id}"
    else:
        store.list_collection("most_workspaces").append(snapshot)
        action = AuditAction.create
        description = f"Created MOST workspace for project {project_id}"
    store.save()
    store.audit(user, action, "most-workspace", snapshot["id"], description, new_value={"project_id": project_id, "step_count": len(snapshot["steps"])})
    return snapshot


@router.post("/most/workspaces/{project_id}/import")
def import_workspace(
    project_id: str,
    payload: MOSTWorkspaceImportRequest,
    store: JsonStore = Depends(get_store),
    user: dict = Depends(require_roles(UserRole.manager, UserRole.engineer)),
):
    return save_workspace(
        project_id,
        MOSTWorkspaceSaveRequest(
            sop_version_id=payload.sop_version_id,
            steps=payload.steps,
            wi_components=payload.wiComponents,
            selected_step_ids=payload.selected_step_ids,
        ),
        store,
        user,
    )


@router.get("/most/workspaces/{project_id}/export")
def export_workspace(project_id: str, sop_version_id: str | None = None, store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    _ensure_project_exists(store, project_id)
    workspace = _find_workspace(store, project_id, sop_version_id)
    return deepcopy(workspace) if workspace else _empty_workspace(project_id, sop_version_id)


def _glove_rule_specificity(rule: dict) -> int:
    """Lower score = more specific; sorted ascending so specific rules match first."""
    score = 0
    if rule.get("object_category") == "*":
        score += 2
    if rule.get("action") in ("*", None):
        score += 1
    return score


@router.post("/gloves/check", response_model=GloveCheckResponse)
def glove_check(payload: GloveCheckRequest, store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    rules = sorted(store.list_collection("glove_rules"), key=_glove_rule_specificity)
    matched = next(
        (
            rule
            for rule in rules
            if rule["object_category"] in {payload.object_category, "*"}
            and rule["action"] in {payload.action, "*", None}
        ),
        None,
    )
    return GloveCheckResponse(
        glove_type=matched["glove_type"] if matched else "General Glove",
        matched_rule_id=matched["id"] if matched else None,
        object_category=payload.object_category,
    )


@router.post("/mi-naming/validate", response_model=MINamingValidationResponse)
def validate_mi_naming(payload: MINamingValidationRequest, store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    rules = store.list_collection("mi_naming_rules")
    errors = []
    parts = []
    for rule in rules:
        key = rule["field"]
        value = (payload.fields.get(key) or "").strip()
        if rule.get("required") and not value:
            errors.append(f"{rule['label']} is required.")
        if value:
            parts.append(value)
    return MINamingValidationResponse(is_valid=not errors, errors=errors, suggested_name="__".join(parts) if parts else None)


@router.post("/most/validate-level")
def validate_level_compatibility(payload: dict, _: dict = Depends(get_current_user)):
    level = int(payload.get("level", 0) or 0)
    index_string = str(payload.get("index_string", "")).strip()
    errors = []
    if level <= 0:
        errors.append("level must be greater than zero")
    if not index_string:
        errors.append("index_string is required")
    if level >= 3 and "X" in index_string and "I" in index_string:
        errors.append("Level 3+ validation does not allow mixed X and I focus in the same compact check.")
    return {"valid": not errors, "errors": errors}


@router.post("/level-system/validate")
def validate_level_system(payload: dict, _: dict = Depends(get_current_user)):
    tags = [node.get("tag", "") for node in payload.get("nodes", [])]
    errors = validate_level_tags(tags)
    return {"is_valid": not errors, "errors": errors}

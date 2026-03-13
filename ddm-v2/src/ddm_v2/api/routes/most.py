from __future__ import annotations

from fastapi import APIRouter, Depends

from ddm_v2.api.dependencies import get_current_user, get_store
from ddm_v2.repositories.store import JsonStore
from ddm_v2.schemas import GloveCheckRequest, GloveCheckResponse, MINamingValidationRequest, MINamingValidationResponse, MOSTCalculateRequest
from ddm_v2.services.level_service import validate_level_tags
from ddm_v2.services.most_service import calculate_workflow


router = APIRouter(prefix="/api/v1", tags=["most"])


@router.post("/most/calculate")
def calculate(payload: MOSTCalculateRequest, _: dict = Depends(get_current_user)):
    return calculate_workflow(payload.steps)


@router.post("/gloves/check", response_model=GloveCheckResponse)
def glove_check(payload: GloveCheckRequest, store: JsonStore = Depends(get_store), _: dict = Depends(get_current_user)):
    rules = store.list_collection("glove_rules")
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

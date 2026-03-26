from __future__ import annotations

from copy import deepcopy

try:
    from datetime import UTC
except ImportError:
    import datetime as _dt
    UTC = _dt.timezone.utc
from datetime import datetime
from typing import Any

from ddm_v2.schemas import MOSTStep
from ddm_v2.services.most_service import calculate_workflow
from ddm_v2.settings import get_settings

MOST_STEP_KEYS = {
    "action",
    "object",
    "seq_type",
    "hand",
    "object_category",
    "from_location",
    "to_location",
    "reference_point",
    "primary_action",
    "glove_type",
    "params",
    "frequency",
    "is_simo",
    "return_a_cm",
    "is_collaborative",
    "operator_count",
    "operators",
}


def _safe_int(value: object, default: int = 1) -> int:
    """Convert value to int without raising; returns default on failure."""
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _as_most_step(raw_step: dict[str, Any]) -> MOSTStep:
    # Use direct key access (guarded by `if key in raw_step`) so the inferred
    # payload type is dict[str, Any] rather than dict[str, Any | None].
    payload: dict[str, Any] = {key: deepcopy(raw_step[key]) for key in MOST_STEP_KEYS if key in raw_step}
    payload.setdefault("params", {})
    payload.setdefault("seq_type", "GENERAL")
    payload["frequency"] = max(_safe_int(payload.get("frequency"), 1), 1)
    payload["is_simo"] = bool(payload.get("is_simo"))
    payload["return_a_cm"] = float(payload.get("return_a_cm") or 0.0)
    payload["is_collaborative"] = bool(payload.get("is_collaborative"))
    payload["operator_count"] = max(int(payload.get("operator_count") or 1), 1)
    payload["operators"] = list(payload.get("operators") or [])
    return MOSTStep(**payload)


def _normalize_step(raw_step: dict[str, Any], index: int) -> dict[str, Any]:
    step = deepcopy(raw_step)
    step_id = str(step.get("id") or f"step-{index + 1}")
    step["id"] = step_id
    step["frequency"] = max(_safe_int(step.get("frequency"), 1), 1)
    step["is_simo"] = bool(step.get("is_simo"))
    step["is_ctq"] = bool(step.get("is_ctq"))
    step["seq_type"] = str(step.get("seq_type") or "GENERAL")
    step["params"] = deepcopy(step.get("params") or {})
    step["component"] = step.get("component") or step.get("object")
    step["tool"] = step.get("tool") or "無"
    return step


def _apply_precaution_rules(action: dict[str, Any], rules: list[dict[str, Any]]) -> list[str]:
    """Return the list of precaution texts that apply to *action* based on
    the stored ``precaution_rules`` master data.

    Matching is case-insensitive substring:
    - ``trigger_type == "component"`` → checked against ``action["component"]``
    - ``trigger_type == "tool"``      → checked against ``action["tool"]``

    Existing precautions already on the action are preserved; only new texts
    (not already present) are appended so that re-running is idempotent.
    """
    existing: list[str] = list(action.get("precautions") or [])
    added: set[str] = set(existing)
    result: list[str] = list(existing)
    component = (action.get("component") or "").lower()
    tool = (action.get("tool") or "").lower()
    for rule in rules:
        trigger_type = rule.get("trigger_type", "")
        trigger_value = (rule.get("trigger_value") or "").lower()
        text: str = rule.get("text", "")
        if not trigger_value or not text or text in added:
            continue
        if trigger_type == "component" and component and trigger_value in component:
            result.append(text)
            added.add(text)
        elif trigger_type == "tool" and tool and trigger_value in tool:
            result.append(text)
            added.add(text)
    return result


def _resolve_glove_from_rules(
    object_category: str | None,
    action: str | None,
    explicit_glove: str | None,
    glove_rules: list[dict[str, Any]],
) -> str:
    """Look up glove type from the stored master-data rules (sorted by
    specificity: exact category+action wins over wildcard).  Falls back to
    'General Glove' when no rule matches.  Called only when the step has no
    explicit glove_type; the explicit value always takes precedence.
    """
    if explicit_glove:
        return explicit_glove
    rules = sorted(
        glove_rules,
        key=lambda r: (
            (1 if r.get("object_category") == "*" else 0)
            + (1 if r.get("action") in ("*", None) else 0)
        ),
    )
    for rule in rules:
        if rule.get("object_category") in {object_category, "*"} and rule.get("action") in {
            action,
            "*",
            None,
        }:
            return str(rule["glove_type"])
    return "General Glove"


def build_workspace_snapshot(
    project_id: str,
    sop_version_id: str | None,
    raw_steps: list[dict[str, Any]],
    raw_wi_components: list[dict[str, Any]],
    selected_step_ids: list[str] | None = None,
    workspace_id: str | None = None,
    glove_rules: list[dict[str, Any]] | None = None,
    precaution_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_steps = [_normalize_step(step, index) for index, step in enumerate(raw_steps)]
    result = calculate_workflow([_as_most_step(step) for step in normalized_steps])
    actions: list[dict[str, Any]] = []
    step_lookup: dict[str, dict[str, Any]] = {}

    tmu_factor = get_settings().tmu_factor
    for index, step in enumerate(normalized_steps):
        metric = result.breakdown[index]
        step["most_code"] = metric.code
        step["index_string"] = metric.index_string
        step["auto_sentence"] = metric.auto_sentence
        step["tmu"] = metric.tmu
        step["seconds"] = round(metric.tmu * tmu_factor, 2)
        step["glove_type"] = _resolve_glove_from_rules(
            step.get("object_category"),
            step.get("primary_action"),
            # Only pass the user-explicitly-set glove as explicit_glove.
            # The infer_glove fallback ("General Glove") must NOT short-circuit
            # the master-data rule lookup; pass it only when the user set it.
            step.get("glove_type") or None,
            glove_rules or [],
        ) if glove_rules else (step.get("glove_type") or metric.glove_type)
        step["component"] = step.get("component") or metric.object
        step_lookup[step["id"]] = step
        actions.append(
            {
                "id": str(step.get("action_id") or f"act-{step['id']}"),
                "seq_type": metric.seq_type,
                "description": step.get("description") or metric.auto_sentence,
                "tmu": metric.tmu,
                "seconds": round(metric.tmu * tmu_factor, 2),
                "params": {
                    **deepcopy(step.get("params") or {}),
                    "_most": {
                        "project_id": project_id,
                        "sop_version_id": sop_version_id,
                        "step_id": step["id"],
                        "most_code": metric.code,
                        "index_string": metric.index_string,
                        "auto_sentence": metric.auto_sentence,
                        "reference_point": step.get("reference_point"),
                        "from_location": metric.from_location,
                        "to_location": metric.to_location,
                        "is_collaborative": metric.is_collaborative,
                        "operator_count": metric.operator_count,
                    },
                },
                "station_id": step.get("station_id"),
                "component": step.get("component") or metric.object,
                "tool": step.get("tool") or "無",
                "image_url": step.get("image_url"),
                "is_ctq": bool(step.get("is_ctq")),
                "primary_action": step.get("primary_action") or metric.action,
                "hand": metric.hand,
                "object_category": metric.object_category,
                "glove_type": step["glove_type"],
                "frequency": metric.frequency,
                "level_tag": step.get("level_tag") or "",
                "is_simo": metric.is_simo,
                "simo_group_id": step.get("simo_group_id"),
                "precautions": _apply_precaution_rules(step, precaution_rules or []),
                "equipment_params": step.get("equipment_params") or None,
            }
        )

    wi_components: list[dict[str, Any]] = []
    for index, component in enumerate(raw_wi_components):
        step_ids = [str(step_id) for step_id in component.get("stepIds") or [] if str(step_id) in step_lookup]
        linked_steps = [step_lookup[step_id] for step_id in step_ids]
        total_tmu = sum(int(step.get("tmu") or 0) for step in linked_steps)
        total_seconds = round(sum(float(step.get("seconds") or 0) for step in linked_steps), 2)
        wi_components.append(
            {
                "id": str(component.get("id") or f"wi-{index + 1}"),
                "name": component.get("name") or "WI",
                "key_parts": component.get("key_parts") or "",
                "stepIds": step_ids,
                "createdAt": component.get("createdAt") or datetime.now(UTC).isoformat(),
                "total_tmu": total_tmu,
                "total_seconds": total_seconds,
                "step_count": len(linked_steps),
            }
        )

    return {
        "id": workspace_id,
        "project_id": project_id,
        "sop_version_id": sop_version_id,
        "saved_at": datetime.now(UTC).isoformat(),
        "version": 1,
        "steps": normalized_steps,
        "wi_components": wi_components,
        "selected_step_ids": [str(step_id) for step_id in (selected_step_ids or [])],
        "summary": {
            "total_tmu": result.total_tmu,
            "total_seconds": result.total_seconds,
            "step_count": len(normalized_steps),
            "component_count": len(wi_components),
        },
        "actions": actions,
    }

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ddm_v2.schemas import MOSTBreakdown, MOSTCalculateResponse, MOSTStep
from ddm_v2.settings import get_settings


ACTION_CODE_MAP = {
    "grab": "G",
    "place": "P",
    "fasten": "X",
    "inspect": "I",
    "scan": "X",
}

FIXED_ACTION_TMU = {
    "fasten": 6,
    "scan": 6,
    "press": 3,
}

PREFERRED_GLOVES = {
    "PCB": "ESD Glove",
    "Fastener": "Finger Cot",
}


def _lookup_a_index(distance_cm: float) -> int:
    if distance_cm <= 2.5:
        return 0
    if distance_cm <= 5:
        return 1
    if distance_cm <= 10:
        return 3
    if distance_cm <= 20:
        return 6
    if distance_cm <= 35:
        return 10
    if distance_cm <= 60:
        return 16
    if distance_cm <= 120:
        return 24
    return 32


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _derive_tmu(step: MOSTStep) -> int:
    tmu_factor = get_settings().tmu_factor
    action_key = (step.primary_action or step.action or "").strip().lower()
    if action_key in FIXED_ACTION_TMU:
        return FIXED_ACTION_TMU[action_key]

    params = step.params or {}
    if step.seq_type.upper() == "GENERAL":
        base = sum(_as_int(params.get(key), 0) for key in ("A1", "B1", "G", "A2", "B2", "P", "A3"))
        return max(base, 1)

    dynamic_x = 0
    if params.get("X_time_seconds"):
        dynamic_x = round(float(params["X_time_seconds"]) / tmu_factor)
    base = sum(_as_int(params.get(key), 0) for key in ("A1", "B1", "G", "M", "I", "A3")) + (dynamic_x or _as_int(params.get("X"), 0))
    return max(base, 1)


def generate_index_string(params: dict[str, Any], seq_type: str, return_a_cm: float = 0.0) -> str:
    if seq_type.upper() == "GENERAL":
        parts = [
            f"A{_as_int(params.get('A1'), 0)}",
            f"B{_as_int(params.get('B1'), 0)}",
            f"G{_as_int(params.get('G'), 0)}",
            f"A{_as_int(params.get('A2'), 0)}",
            f"B{_as_int(params.get('B2'), 0)}",
            f"P{_as_int(params.get('P'), 0)}",
            f"A{_as_int(params.get('A3'), _lookup_a_index(return_a_cm))}",
        ]
    else:
        parts = [
            f"A{_as_int(params.get('A1'), 0)}",
            f"B{_as_int(params.get('B1'), 0)}",
            f"G{_as_int(params.get('G'), 0)}",
            f"M{_as_int(params.get('M'), 0)}",
            f"X{_as_int(params.get('X'), 0)}",
            f"I{_as_int(params.get('I'), 0)}",
            f"A{_as_int(params.get('A3'), _lookup_a_index(return_a_cm))}",
        ]
    return " ".join(parts)


def generate_auto_sentence(step: MOSTStep) -> str:
    hand = step.hand or "Right Hand"
    target = step.object or step.object_category or "target"
    source = step.from_location or "source"
    destination = step.to_location or "destination"
    action = step.primary_action or step.action or "operate"
    sentence = f"{hand} {action} {target} from {source} to {destination}"
    if step.frequency > 1:
        sentence += f" x{step.frequency}"
    if step.is_simo:
        sentence += " [SIMO]"
    return sentence


def infer_glove(object_category: str | None, explicit_glove: str | None = None) -> str | None:
    if explicit_glove:
        return explicit_glove
    if not object_category:
        return "General Glove"
    return PREFERRED_GLOVES.get(object_category, "General Glove")


def calculate_workflow(steps: list[MOSTStep]) -> MOSTCalculateResponse:
    tmu_factor = get_settings().tmu_factor
    total_tmu = 0
    simo_groups: dict[str, list[int]] = defaultdict(list)
    collaborative_effective_tmu = 0
    breakdown: list[MOSTBreakdown] = []

    for step in steps:
        base_tmu = _derive_tmu(step)
        frequency = max(step.frequency, 1)
        tmu = base_tmu * frequency
        effective_tmu = None
        if step.is_collaborative and step.operators:
            op_values = [max((operator.individual_tmu or 0), 0) * frequency for operator in step.operators]
            if op_values:
                effective_tmu = max(op_values)
        collaborative_effective_tmu += effective_tmu if effective_tmu is not None else tmu
        total_tmu += tmu
        if step.is_simo:
            simo_groups[step.hand or "BOTH"].append(tmu)
        action_key = (step.primary_action or step.action).strip().lower()
        breakdown.append(
            MOSTBreakdown(
                action=step.primary_action or step.action,
                object=step.object or step.object_category or "-",
                tmu=tmu,
                code=ACTION_CODE_MAP.get(action_key, "X"),
                seq_type=step.seq_type,
                hand=step.hand,
                glove_type=infer_glove(step.object_category, step.glove_type),
                object_category=step.object_category,
                from_location=step.from_location,
                to_location=step.to_location,
                frequency=frequency,
                is_simo=step.is_simo,
                index_string=generate_index_string(step.params, step.seq_type, step.return_a_cm),
                auto_sentence=generate_auto_sentence(step),
                is_collaborative=step.is_collaborative,
                operator_count=step.operator_count,
                effective_tmu=effective_tmu,
            )
        )

    simo_max_tmu = max((max(values) for values in simo_groups.values()), default=None)
    simo_seconds = round(simo_max_tmu * tmu_factor, 2) if simo_max_tmu is not None else None
    total_seconds = round(total_tmu * tmu_factor, 2)
    collaborative_effective_seconds = round(collaborative_effective_tmu * tmu_factor, 2)

    return MOSTCalculateResponse(
        total_tmu=total_tmu,
        total_seconds=total_seconds,
        breakdown=breakdown,
        simo_max_tmu=simo_max_tmu,
        simo_seconds=simo_seconds,
        collaborative_effective_tmu=collaborative_effective_tmu if collaborative_effective_tmu != total_tmu else None,
        collaborative_effective_seconds=collaborative_effective_seconds if collaborative_effective_tmu != total_tmu else None,
    )

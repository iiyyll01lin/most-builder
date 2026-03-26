from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ddm_v2.ai_schemas import GenerateSopRequest, GenerateSopResponse
from ddm_v2.api.dependencies import get_current_user, get_store
from ddm_v2.repositories.store import JsonStore
from ddm_v2.services.ai_service import generate_sop_actions
from ddm_v2.services.most_workspace_service import _apply_precaution_rules

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.post("/generate-sop", response_model=GenerateSopResponse, status_code=200)
def generate_sop(
    payload: GenerateSopRequest,
    store: JsonStore = Depends(get_store),
    _user: dict = Depends(get_current_user),
) -> GenerateSopResponse:
    """Generate a list of SOPAction objects from a natural language instruction.

    The pipeline:
    1. Load current object_library, tool_library, and precaution_rules from the
       store so the AI always sees live, project-specific master data.
    2. Call ``generate_sop_actions`` — real OpenAI API when OPENAI_API_KEY is set,
       otherwise the deterministic mock generator.
    3. Assign a fresh store-issued ID to every action.
    4. Run ``_apply_precaution_rules`` on every action so auto-binding safety
       precautions (LCD handling, electric screwdriver torque, etc.) are already
       populated before the IE reviews the draft.
    5. Return the validated action list for front-end optimistic rendering.
    """
    object_library: list[dict] = list(store.list_collection("object_library"))
    tool_library: list[dict] = list(store.list_collection("tool_library"))
    precaution_rules: list[dict] = list(store.list_collection("precaution_rules"))

    try:
        raw_actions = generate_sop_actions(
            instruction=payload.instruction,
            object_library=object_library,
            tool_library=tool_library,
            precaution_rules=precaution_rules,
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"AI service could not generate valid actions: {exc}",
        ) from exc

    validated: list[dict] = []
    for action in raw_actions:
        # Assign a unique ID for optimistic rendering and future save operations
        action["id"] = store.new_id("act")
        # Apply auto-binding precaution rules (idempotent; safe to run on fresh actions)
        action["precautions"] = _apply_precaution_rules(action, precaution_rules)
        validated.append(action)

    return GenerateSopResponse(
        actions=validated,
        message=f"Generated {len(validated)} action(s) from instruction.",
    )

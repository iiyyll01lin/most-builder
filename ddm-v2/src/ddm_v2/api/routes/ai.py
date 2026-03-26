from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ddm_v2.ai_schemas import (
    GenerateSopRequest,
    GenerateSopResponse,
    SopReviewRequest,
    SopReviewResponse,
)
from ddm_v2.api.dependencies import get_current_user, get_store
from ddm_v2.repositories.store import JsonStore
from ddm_v2.services.ai_review_service import review_sop_sequence
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


@router.post("/review-sop", response_model=SopReviewResponse, status_code=200)
def review_sop(
    payload: SopReviewRequest,
    store: JsonStore = Depends(get_store),
    _user: dict = Depends(get_current_user),
) -> SopReviewResponse:
    """Audit a complete SOP version for manufacturing logic conflicts.

    The pipeline:
    1. Fetch the SOP version from the store; 404 if not found.
    2. Collect all actions in their natural list order (the order they appear in
       the SOP version's ``actions`` array).  This is the intended execution
       sequence as authored by the IE.
    3. Pass the ordered sequence to ``review_sop_sequence`` — which calls the
       OpenAI API when OPENAI_API_KEY is configured, or the deterministic mock
       generator otherwise.
    4. Return the validated ``SopReviewResponse`` containing a list of
       ``Conflict`` objects with severity, description, related action IDs, and
       a concrete fix suggestion.
    """
    sop_version = store.find_by_id("sop_versions", payload.sop_version_id)
    if sop_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SOP version '{payload.sop_version_id}' not found.",
        )

    ordered_actions: list[dict] = list(sop_version.get("actions", []))

    try:
        return review_sop_sequence(ordered_actions)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"AI review service error: {exc}",
        ) from exc

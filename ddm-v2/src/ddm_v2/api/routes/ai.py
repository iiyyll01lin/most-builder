from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ddm_v2.ai_schemas import (
    GenerateSopRequest,
    GenerateSopResponse,
    SopReviewRequest,
    SopReviewResponse,
)
from ddm_v2.api.dependencies import get_current_user, get_store
from ddm_v2.repositories.postgres_store import PostgresStore
from ddm_v2.services.ai_review_service import review_sop_sequence
from ddm_v2.services.ai_service import generate_sop_actions
from ddm_v2.services.most_workspace_service import _apply_precaution_rules

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.post("/generate-sop", response_model=GenerateSopResponse, status_code=200)
async def generate_sop(
    payload: GenerateSopRequest,
    store: PostgresStore = Depends(get_store),
    _user: dict = Depends(get_current_user),
) -> GenerateSopResponse:
    object_library: list[dict] = list(await store.list_collection("object_library"))
    tool_library: list[dict] = list(await store.list_collection("tool_library"))
    precaution_rules: list[dict] = list(await store.list_collection("precaution_rules"))

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
        action["id"] = store.new_id("act")
        action["precautions"] = _apply_precaution_rules(action, precaution_rules)
        validated.append(action)

    return GenerateSopResponse(
        actions=validated,
        message=f"Generated {len(validated)} action(s) from instruction.",
    )


@router.post("/review-sop", response_model=SopReviewResponse, status_code=200)
async def review_sop(
    payload: SopReviewRequest,
    store: PostgresStore = Depends(get_store),
    _user: dict = Depends(get_current_user),
) -> SopReviewResponse:
    sop_version = await store.find_by_id("sop_versions", payload.sop_version_id)
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
            detail=f"AI review service failed: {exc}",
        ) from exc




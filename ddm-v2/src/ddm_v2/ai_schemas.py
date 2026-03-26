from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GenerateSopRequest(BaseModel):
    instruction: str = Field(
        min_length=5,
        max_length=2000,
        description="Natural language description of the manufacturing operation to be converted into SOP actions.",
    )
    project_id: str | None = None


class GenerateSopResponse(BaseModel):
    actions: list[dict] = Field(default_factory=list)
    message: str = "Generated successfully"


# ─── SOP Conflict Review schemas ──────────────────────────────────────────────

class SopReviewRequest(BaseModel):
    """Request body for the SOP Conflict Review endpoint."""

    sop_version_id: str = Field(
        description="ID of the SOP version to audit. The backend fetches and sorts its actions."
    )


class Conflict(BaseModel):
    """A single manufacturing logic conflict detected by the AI auditor."""

    severity: Literal["High", "Medium", "Low"] = Field(
        description="Impact level: High = physically impossible, Medium = likely wrong, Low = advisory."
    )
    description: str = Field(
        description="Clear explanation of what is wrong in the sequence."
    )
    related_action_ids: list[str] = Field(
        default_factory=list,
        description="IDs of the actions involved in this conflict (for frontend highlighting).",
    )
    suggestion: str = Field(
        description="Concrete recommendation on how to fix the conflict (e.g., which steps to swap)."
    )


class SopReviewResponse(BaseModel):
    """Structured audit result returned by the SOP Conflict Review endpoint."""

    conflicts: list[Conflict] = Field(default_factory=list)
    reviewed_action_count: int = Field(
        description="Number of actions that were analysed."
    )
    summary: str = Field(
        default="Review complete.",
        description="One-line summary of the audit outcome.",
    )

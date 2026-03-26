from __future__ import annotations

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

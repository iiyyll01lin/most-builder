"""BI (Generative Business Intelligence) API route.

POST /api/v1/bi/query
    Accepts a natural-language question, runs the Text-to-SQL pipeline,
    and returns a structured JSON payload ready for server-driven UI rendering.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.api.dependencies import get_current_user
from ddm_v2.db.database import get_session
from ddm_v2.services.bi_service import generate_bi_report

router = APIRouter(prefix="/api/v1/bi", tags=["bi"])


class BIQueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=512, description="Natural language question.")


@router.post("/query", status_code=200)
async def bi_query(
    payload: BIQueryRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Translate a natural-language query into SQL, execute it, and return a
    structured BI payload that the frontend renders as a dynamic chart.

    Security: the underlying ``ReadOnlySQLExecutor`` enforces:
      1. Structural SELECT-only check (regex)
      2. DML/DDL keyword blacklist (regex)
      3. PostgreSQL ``SET TRANSACTION READ ONLY`` (database-level)
    """
    try:
        result = await generate_bi_report(payload.query, session)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"SQL validation failed: {exc}",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI service error: {exc}",
        ) from exc
    return result

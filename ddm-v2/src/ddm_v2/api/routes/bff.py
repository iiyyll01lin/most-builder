"""Backend-For-Frontend (BFF) aggregator routes.

These endpoints combine multiple data sources into a single response optimised
for specific UI views.  They are *read-only* and never mutate state.
"""

from __future__ import annotations

from copy import deepcopy

from fastapi import APIRouter, Depends, HTTPException

from ddm_v2.api.dependencies import get_current_user, get_store
from ddm_v2.repositories.postgres_store import PostgresStore
from ddm_v2.services.level_service import build_level_entries, build_precedence_graph

router = APIRouter(prefix="/api/v1/bff", tags=["bff"])


def _level_scope_key(project_id: str, sop_version_id: str | None) -> str:
    return f"{project_id}::{sop_version_id or '__default__'}"


@router.get("/dashboard/{project_id}")
async def dashboard(
    project_id: str,
    sop_version_id: str | None = None,
    store: PostgresStore = Depends(get_store),
    _: dict = Depends(get_current_user),
) -> dict:
    """Aggregate endpoint for the MOST Workspace + Level System dashboard.

    Replaces the following sequential client requests:
    1. GET /api/v1/projects/{project_id}
    2. GET /api/v1/sop/versions?project_id={id}
    3. GET /api/v1/most/workspaces/{project_id}
    4. GET /api/v1/level-system/{project_id}
    5. POST /api/v1/level-system/generate-graph

    Returns a single JSON object the UI can use to paint the entire dashboard
    in one network round trip.
    """
    project = await store.find_by_id("projects", project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # --- SOP versions (summary only — no full action list to keep payload lean) ---
    all_versions = [v for v in await store.list_collection("sop_versions") if v["project_id"] == project_id]
    sop_summaries = [
        {
            "id": v["id"],
            "version_no": v["version_no"],
            "status": v["status"],
            "action_count": len(v.get("actions", [])),
            "created_at": v.get("created_at"),
            "published_at": v.get("published_at"),
        }
        for v in all_versions
    ]

    # --- Resolve active SOP version ---
    resolved_sop_version_id = sop_version_id
    target_version: dict | None = None
    sop_actions: list[dict] = []
    if all_versions:
        if resolved_sop_version_id:
            target_version = next((v for v in all_versions if v["id"] == resolved_sop_version_id), None)
        else:
            draft_candidates = [v for v in all_versions if v["status"] == "Draft"]
            target_version = (draft_candidates[-1] if draft_candidates else None) or all_versions[-1]
            resolved_sop_version_id = target_version["id"]
        if target_version:
            sop_actions = list(target_version.get("actions", []))

    # --- MOST workspace ---
    workspace = await store.find_workspace(project_id, resolved_sop_version_id)
    workspace_payload = (
        deepcopy(workspace)
        if workspace
        else {
            "id": None,
            "project_id": project_id,
            "sop_version_id": resolved_sop_version_id,
            "saved_at": None,
            "version": 1,
            "steps": [],
            "wi_components": [],
            "selected_step_ids": [],
            "summary": {"total_tmu": 0, "total_seconds": 0.0, "step_count": 0, "component_count": 0},
            "actions": [],
        }
    )

    # --- Level system entries ---
    scope_key = _level_scope_key(project_id, resolved_sop_version_id)
    existing_entries = await store.get_level_entries(scope_key)
    if existing_entries is None and sop_version_id is None:
        existing_entries = await store.get_level_entries(project_id)
    existing_entries = existing_entries or []
    level_entries = build_level_entries(project_id, sop_actions, existing_entries)

    # --- Precedence graph (None when no data exists yet) ---
    precedence_graph: dict | None = None
    if level_entries or sop_actions:
        try:
            graph = build_precedence_graph(level_entries)
            graph["project_id"] = project_id
            graph["sop_version_id"] = resolved_sop_version_id
            precedence_graph = graph
        except Exception:  # noqa: BLE001 — graph build is best-effort in aggregate view
            precedence_graph = None

    return {
        "project": project,
        "sop_versions": sop_summaries,
        "active_sop_version_id": resolved_sop_version_id,
        "workspace": workspace_payload,
        "level_system": {
            "sop_version_id": resolved_sop_version_id,
            "entries": level_entries,
            "total_count": len(level_entries),
        },
        "precedence_graph": precedence_graph,
    }

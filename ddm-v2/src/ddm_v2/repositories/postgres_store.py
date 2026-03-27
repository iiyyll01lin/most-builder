"""Async PostgreSQL-backed store implementing the exact interface of JsonStore.

All public methods that read or write data are ``async``.  ``new_id()`` is
the sole synchronous method (UUID generation requires no I/O).

Route handlers receive plain ``dict`` values from every method, preserving
the existing API contracts without changes to response schemas.
"""

from __future__ import annotations

try:
    from datetime import UTC
except ImportError:
    import datetime as _dt
    UTC = _dt.timezone.utc

from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ddm_v2.models.domain import (
    AuditLogRow,
    ComponentLibraryRow,
    EmployeeRow,
    FromLocationRow,
    GloveRuleRow,
    IonFanBindingRow,
    LevelEntryRow,
    LevelGuidelineRow,
    LevelSystemTemplateRow,
    LocationLibraryRow,
    MINamingRuleRow,
    MostWorkspaceRow,
    ObjectLibraryRow,
    PrecautionRow,
    PrecautionRuleRow,
    ProjectRow,
    ReferencePointRow,
    SimulationResultRow,
    SopActionRow,
    SopVersionRow,
    StationRow,
    SyntaxLibraryRow,
    ToLocationRow,
    ToolLibraryRow,
    UserRow,
    VideoUploadRow,
)
from ddm_v2.schemas import AuditAction

# ---------------------------------------------------------------------------
# Generic table map — used by list_collection / find_by_id / upsert / delete
# Everything NOT in this map has a dedicated code path below.
# ---------------------------------------------------------------------------
_GENERIC_MAP: dict[str, type] = {
    "projects": ProjectRow,
    "syntax_library": SyntaxLibraryRow,
    "component_library": ComponentLibraryRow,
    "tool_library": ToolLibraryRow,
    "location_library": LocationLibraryRow,
    "object_library": ObjectLibraryRow,
    "from_locations": FromLocationRow,
    "to_locations": ToLocationRow,
    "reference_points": ReferencePointRow,
    "precautions": PrecautionRow,
    "precaution_rules": PrecautionRuleRow,
    "glove_rules": GloveRuleRow,
    "ion_fan_bindings": IonFanBindingRow,
    "mi_naming_rules": MINamingRuleRow,
    "level_system_templates": LevelSystemTemplateRow,
    "level_guidelines": LevelGuidelineRow,
    "employees": EmployeeRow,
    "stations": StationRow,
    "audit_logs": AuditLogRow,
}

# ---------------------------------------------------------------------------
# Row → dict conversion helpers
# ---------------------------------------------------------------------------


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Generic ORM row → plain dict (strips SQLAlchemy instance state)."""
    return {k: v for k, v in vars(row).items() if not k.startswith("_")}


def _sop_action_to_dict(row: SopActionRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "seq_type": row.seq_type,
        "description": row.description,
        "tmu": row.tmu,
        "seconds": row.seconds,
        "params": row.params if row.params is not None else {},
        "station_id": row.station_id,
        "component": row.component,
        "tool": row.tool,
        "image_url": row.image_url,
        "is_ctq": row.is_ctq,
        "primary_action": row.primary_action,
        "hand": row.hand,
        "object_category": row.object_category,
        "glove_type": row.glove_type,
        "frequency": row.frequency,
        "level_tag": row.level_tag,
        "is_simo": row.is_simo,
        "simo_group_id": row.simo_group_id,
        "required_skill": row.required_skill,
        "precautions": row.precautions if row.precautions is not None else [],
        "equipment_params": row.equipment_params,
        # Vision-engine timestamp anchors (None until analysis has been run)
        "video_timestamp_start": row.video_timestamp_start,
        "video_timestamp_end": row.video_timestamp_end,
    }


def _sop_version_to_dict(row: SopVersionRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "version_no": row.version_no,
        "status": row.status,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "published_by": row.published_by,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "actions": [_sop_action_to_dict(a) for a in row.sop_actions],
    }


def _workspace_to_dict(row: MostWorkspaceRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "sop_version_id": row.sop_version_id,
        **(row.data or {}),
    }


def _sim_result_to_dict(row: SimulationResultRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "timestamp": row.timestamp,
        "created_by": row.created_by,
        **(row.data or {}),
    }


def _audit_to_dict(row: AuditLogRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "timestamp": row.timestamp.isoformat() if isinstance(row.timestamp, datetime) else (row.timestamp or ""),
        "user_id": row.user_id,
        "user_name": row.user_name,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "description": row.description,
        "old_value": row.old_value,
        "new_value": row.new_value,
    }


def _level_entry_to_dict(row: LevelEntryRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "action_id": row.action_id,
        "difficulty_factor": row.difficulty_factor,
        "number_tag": row.number_tag,
        "number_count": row.number_count,
        "main_seq": row.main_seq,
        "order_seq": row.order_seq,
        "cub_group": row.cub_group,
        "machine_count": row.machine_count,
        "operator_count": row.operator_count,
        "status_label": row.status_label,
        "sort_order": row.sort_order,
    }


def _user_to_dict(row: UserRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "username": row.username,
        "password": row.password,
        "role": row.role,
        "name": row.name,
    }


def _parse_dt(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# PostgresStore
# ---------------------------------------------------------------------------


class PostgresStore:
    """Async PostgreSQL-backed replacement for ``JsonStore``.

    Constructed per-request from the ``AsyncSession`` provided by the
    ``get_store`` FastAPI dependency.  All mutating methods flush to the
    session immediately; the session's commit / rollback lifecycle is
    managed by ``get_session`` in ``db/database.py``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        # db_path kept for API compat with system.py db/status endpoint
        from pathlib import Path
        self.db_path = Path("postgresql://[managed-by-engine]")

    # ------------------------------------------------------------------
    # Synchronous utilities
    # ------------------------------------------------------------------

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:8]}"

    # ------------------------------------------------------------------
    # Generic collection operations
    # ------------------------------------------------------------------

    async def list_collection(self, key: str) -> list[dict[str, Any]]:
        if key == "sop_versions":
            return await self._list_sop_versions()
        if key == "users":
            return list((await self.get_users_dict()).values())
        if key == "most_workspaces":
            return await self._list_workspaces()
        if key == "simulation_results":
            return await self._list_sim_results()
        if key == "audit_logs":
            result = await self._session.execute(
                select(AuditLogRow).order_by(AuditLogRow.timestamp.desc())
            )
            return [_audit_to_dict(r) for r in result.scalars().all()]
        model_cls = _GENERIC_MAP.get(key)
        if model_cls is None:
            return []
        result = await self._session.execute(select(model_cls))
        return [_row_to_dict(r) for r in result.scalars().all()]

    async def find_by_id(self, key: str, item_id: str) -> dict[str, Any] | None:
        if key == "sop_versions":
            return await self._find_sop_version(item_id)
        if key == "users":
            result = await self._session.execute(
                select(UserRow).where(UserRow.id == item_id)
            )
            row = result.scalar_one_or_none()
            return _user_to_dict(row) if row else None
        if key == "most_workspaces":
            row = await self._session.get(MostWorkspaceRow, item_id)  # type: ignore[arg-type]
            return _workspace_to_dict(row) if row else None  # type: ignore[arg-type]
        if key == "simulation_results":
            row = await self._session.get(SimulationResultRow, item_id)  # type: ignore[arg-type]
            return _sim_result_to_dict(row) if row else None  # type: ignore[arg-type]
        if key == "audit_logs":
            row = await self._session.get(AuditLogRow, item_id)  # type: ignore[arg-type]
            return _audit_to_dict(row) if row else None  # type: ignore[arg-type]
        model_cls = _GENERIC_MAP.get(key)
        if model_cls is None:
            return None
        row = await self._session.get(model_cls, item_id)
        return _row_to_dict(row) if row else None

    async def upsert_collection_item(self, key: str, item: dict[str, Any]) -> dict[str, Any]:
        """Insert or fully replace a record for the given collection key."""
        if key == "sop_versions":
            return await self._upsert_sop_version(item)
        if key == "most_workspaces":
            return await self._upsert_workspace(item)
        if key == "simulation_results":
            return await self._upsert_sim_result(item)
        if key == "audit_logs":
            return await self._upsert_audit_log(item)
        model_cls = _GENERIC_MAP.get(key)
        if model_cls is None:
            return item
        item_id = item.get("id")
        row = await self._session.get(model_cls, item_id) if item_id else None  # type: ignore[func-returns-value]
        if row is None:
            row = model_cls()
            self._session.add(row)
        for k, v in item.items():
            if hasattr(row, k):
                setattr(row, k, v)
        await self._session.flush()
        return _row_to_dict(row)

    # Alias kept for routes that use the "append then save" pattern
    async def insert_item(self, key: str, item: dict[str, Any]) -> dict[str, Any]:
        return await self.upsert_collection_item(key, item)

    async def delete_collection_item(self, key: str, item_id: str) -> dict[str, Any] | None:
        existing = await self.find_by_id(key, item_id)
        if existing is None:
            return None
        if key == "sop_versions":
            await self._session.execute(delete(SopVersionRow).where(SopVersionRow.id == item_id))
        elif key == "simulation_results":
            await self._session.execute(delete(SimulationResultRow).where(SimulationResultRow.id == item_id))
        else:
            model_cls = _GENERIC_MAP.get(key)
            if model_cls is None:
                return None
            await self._session.execute(delete(model_cls).where(model_cls.id == item_id))  # type: ignore[attr-defined]
        await self._session.flush()
        return existing

    # ------------------------------------------------------------------
    # User-specific operations
    # ------------------------------------------------------------------

    async def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(UserRow).where(UserRow.username == username)
        )
        row = result.scalar_one_or_none()
        return _user_to_dict(row) if row else None

    async def get_users_dict(self) -> dict[str, dict[str, Any]]:
        """Return ``{username: user_dict}`` mirroring ``store.state["users"]``."""
        result = await self._session.execute(select(UserRow))
        return {row.username: _user_to_dict(row) for row in result.scalars().all()}

    # ------------------------------------------------------------------
    # Level entries (keyed by scope_key, not by id)
    # ------------------------------------------------------------------

    async def get_level_entries(self, scope_key: str) -> list[dict[str, Any]] | None:
        """Return ``[entry_dict, ...]`` or ``None`` if scope has no entries."""
        result = await self._session.execute(
            select(LevelEntryRow)
            .where(LevelEntryRow.scope_key == scope_key)
            .order_by(LevelEntryRow.sort_order.nulls_last(), LevelEntryRow.id)
        )
        rows = result.scalars().all()
        return [_level_entry_to_dict(r) for r in rows] if rows else None

    async def set_level_entries(self, scope_key: str, entries: list[dict[str, Any]]) -> None:
        """Replace all level entries for *scope_key* atomically."""
        await self._session.execute(
            delete(LevelEntryRow).where(LevelEntryRow.scope_key == scope_key)
        )
        for entry in entries:
            row = LevelEntryRow(
                id=entry.get("id") or self.new_id("lvl"),
                scope_key=scope_key,
                action_id=entry["action_id"],
                difficulty_factor=entry.get("difficulty_factor", 1.0),
                number_tag=entry.get("number_tag"),
                number_count=entry.get("number_count"),
                main_seq=entry.get("main_seq"),
                order_seq=entry.get("order_seq"),
                cub_group=entry.get("cub_group"),
                machine_count=entry.get("machine_count", 1),
                operator_count=entry.get("operator_count", 1),
                status_label=entry.get("status_label"),
                sort_order=entry.get("sort_order"),
            )
            self._session.add(row)
        await self._session.flush()

    # ------------------------------------------------------------------
    # No-op compatibility stubs (JsonStore persistence methods)
    # ------------------------------------------------------------------

    async def save(self) -> None:  # noqa: D401
        """No-op: PostgreSQL session commits are handled by the request dependency."""

    async def load(self) -> None:  # noqa: D401
        """No-op: PostgreSQL is always live."""

    async def reset(self) -> None:
        """Truncate all tables (FK-safe order) then re-seed from DEFAULT_STATE."""
        await self._session.execute(delete(AuditLogRow))
        await self._session.execute(delete(SimulationResultRow))
        await self._session.execute(delete(LevelEntryRow))
        await self._session.execute(delete(MostWorkspaceRow))
        await self._session.execute(delete(SopActionRow))
        await self._session.execute(delete(SopVersionRow))
        await self._session.execute(delete(StationRow))
        await self._session.execute(delete(EmployeeRow))
        await self._session.execute(delete(ProjectRow))
        await self._session.execute(delete(UserRow))
        for model_cls in (
            SyntaxLibraryRow, ComponentLibraryRow, ToolLibraryRow,
            LocationLibraryRow, ObjectLibraryRow, FromLocationRow,
            ToLocationRow, ReferencePointRow, PrecautionRow,
            PrecautionRuleRow, GloveRuleRow, IonFanBindingRow,
            MINamingRuleRow, LevelSystemTemplateRow, LevelGuidelineRow,
        ):
            await self._session.execute(delete(model_cls))
        await self._seed_from_defaults()
        await self._session.flush()

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    async def audit(
        self,
        user: dict[str, Any],
        action: AuditAction,
        entity_type: str,
        entity_id: str,
        description: str,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry_id = self.new_id("audit")
        now = datetime.now(UTC)
        action_val = action.value if hasattr(action, "value") else str(action)
        row = AuditLogRow(
            id=entry_id,
            timestamp=now,
            user_id=user["id"],
            user_name=user["name"],
            action=action_val,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            old_value=deepcopy(old_value),
            new_value=deepcopy(new_value),
        )
        self._session.add(row)
        await self._session.flush()
        return {
            "id": entry_id,
            "timestamp": now.isoformat(),
            "user_id": user["id"],
            "user_name": user["name"],
            "action": action_val,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "description": description,
            "old_value": old_value,
            "new_value": new_value,
        }

    # ------------------------------------------------------------------
    # System / admin helpers
    # ------------------------------------------------------------------

    async def get_collection_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        all_models: list[tuple[str, type]] = list(_GENERIC_MAP.items()) + [
            ("sop_versions", SopVersionRow),
            ("sop_actions", SopActionRow),
            ("most_workspaces", MostWorkspaceRow),
            ("simulation_results", SimulationResultRow),
            ("level_entries", LevelEntryRow),
            ("users", UserRow),
        ]
        for key, model_cls in all_models:
            result = await self._session.execute(select(func.count()).select_from(model_cls))
            counts[key] = result.scalar_one()
        return counts

    async def export_state(self) -> dict[str, Any]:
        """Build a JSON-serialisable snapshot of the entire database state."""
        state: dict[str, Any] = {}
        for key in _GENERIC_MAP:
            state[key] = await self.list_collection(key)
        state["users"] = await self.get_users_dict()
        state["sop_versions"] = await self.list_collection("sop_versions")
        state["most_workspaces"] = await self.list_collection("most_workspaces")
        state["simulation_results"] = await self.list_collection("simulation_results")
        # Level entries grouped by scope_key
        le_result = await self._session.execute(select(LevelEntryRow))
        le_grouped: dict[str, list] = {}
        for row in le_result.scalars().all():
            le_grouped.setdefault(row.scope_key, []).append(_level_entry_to_dict(row))
        state["level_entries"] = le_grouped
        state["audit_logs"] = await self.list_collection("audit_logs")
        return state

    # ------------------------------------------------------------------
    # Private SOP version helpers
    # ------------------------------------------------------------------

    async def _list_sop_versions(self) -> list[dict[str, Any]]:
        stmt = (
            select(SopVersionRow)
            .options(selectinload(SopVersionRow.sop_actions))
            .order_by(SopVersionRow.created_at.nulls_last())
        )
        result = await self._session.execute(stmt)
        return [_sop_version_to_dict(r) for r in result.scalars().all()]

    async def _find_sop_version(self, sop_id: str) -> dict[str, Any] | None:
        row = await self._session.get(
            SopVersionRow,
            sop_id,
            options=[selectinload(SopVersionRow.sop_actions)],
        )
        return _sop_version_to_dict(row) if row else None

    async def _upsert_sop_version(self, version_dict: dict[str, Any]) -> dict[str, Any]:
        ver_id = version_dict.get("id")
        row = await self._session.get(
            SopVersionRow,
            ver_id,
            options=[selectinload(SopVersionRow.sop_actions)],
        )
        if row is None:
            row = SopVersionRow(id=ver_id)
            self._session.add(row)

        row.project_id = version_dict["project_id"]
        row.version_no = version_dict["version_no"]
        row.status = version_dict.get("status", "Draft")
        row.created_by = version_dict.get("created_by")
        row.created_at = _parse_dt(version_dict.get("created_at"))
        row.reviewed_by = version_dict.get("reviewed_by")
        row.reviewed_at = _parse_dt(version_dict.get("reviewed_at"))
        row.published_by = version_dict.get("published_by")
        row.published_at = _parse_dt(version_dict.get("published_at"))

        # Full replace of actions via ORM cascade
        row.sop_actions.clear()
        for idx, action_dict in enumerate(version_dict.get("actions", [])):
            row.sop_actions.append(
                SopActionRow(
                    id=action_dict.get("id") or self.new_id("act"),
                    sop_version_id=ver_id,
                    sort_idx=idx,
                    seq_type=action_dict.get("seq_type", "GENERAL"),
                    description=action_dict.get("description", ""),
                    tmu=action_dict.get("tmu", 0),
                    seconds=action_dict.get("seconds", 0.0),
                    params=action_dict.get("params") or {},
                    station_id=action_dict.get("station_id"),
                    component=action_dict.get("component"),
                    tool=action_dict.get("tool"),
                    image_url=action_dict.get("image_url"),
                    is_ctq=action_dict.get("is_ctq", False),
                    primary_action=action_dict.get("primary_action"),
                    hand=action_dict.get("hand"),
                    object_category=action_dict.get("object_category"),
                    glove_type=action_dict.get("glove_type"),
                    frequency=action_dict.get("frequency", 1),
                    level_tag=action_dict.get("level_tag"),
                    is_simo=action_dict.get("is_simo", False),
                    simo_group_id=action_dict.get("simo_group_id"),
                    required_skill=action_dict.get("required_skill"),
                    precautions=action_dict.get("precautions") or [],
                    equipment_params=action_dict.get("equipment_params"),
                )
            )
        await self._session.flush()
        # Re-load the relationship after flush (flush expires lazy-loaded collections in async sessions)
        await self._session.refresh(row, attribute_names=["sop_actions"])
        return _sop_version_to_dict(row)

    # ------------------------------------------------------------------
    # Private workspace helpers
    # ------------------------------------------------------------------

    async def _list_workspaces(self) -> list[dict[str, Any]]:
        result = await self._session.execute(select(MostWorkspaceRow))
        return [_workspace_to_dict(r) for r in result.scalars().all()]

    async def _upsert_workspace(self, workspace_dict: dict[str, Any]) -> dict[str, Any]:
        ws_id = workspace_dict.get("id")
        row = await self._session.get(MostWorkspaceRow, ws_id) if ws_id else None
        if row is None:
            row = MostWorkspaceRow(id=ws_id or self.new_id("mostws"))
            self._session.add(row)
        row.project_id = workspace_dict["project_id"]
        row.sop_version_id = workspace_dict.get("sop_version_id")
        # Store everything except the three scalar columns in the data blob
        scalar_keys = {"id", "project_id", "sop_version_id"}
        row.data = {k: v for k, v in workspace_dict.items() if k not in scalar_keys}
        await self._session.flush()
        return _workspace_to_dict(row)

    async def find_workspace(
        self, project_id: str, sop_version_id: str | None = None
    ) -> dict[str, Any] | None:
        """Find workspace by (project_id, sop_version_id) — used by route helpers."""
        stmt = select(MostWorkspaceRow).where(MostWorkspaceRow.project_id == project_id)
        if sop_version_id is not None:
            stmt = stmt.where(MostWorkspaceRow.sop_version_id == sop_version_id)
        else:
            stmt = stmt.where(MostWorkspaceRow.sop_version_id.is_(None))
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        if not rows:
            # Fallback: last workspace for project (matches JsonStore behaviour)
            stmt2 = select(MostWorkspaceRow).where(MostWorkspaceRow.project_id == project_id)
            result2 = await self._session.execute(stmt2)
            rows2 = result2.scalars().all()
            return _workspace_to_dict(rows2[-1]) if rows2 else None
        return _workspace_to_dict(rows[0])

    # ------------------------------------------------------------------
    # Private simulation result helpers
    # ------------------------------------------------------------------

    async def _list_sim_results(self) -> list[dict[str, Any]]:
        result = await self._session.execute(select(SimulationResultRow))
        return [_sim_result_to_dict(r) for r in result.scalars().all()]

    async def _upsert_sim_result(self, d: dict[str, Any]) -> dict[str, Any]:
        sim_id = d.get("id")
        row = await self._session.get(SimulationResultRow, sim_id) if sim_id else None
        if row is None:
            row = SimulationResultRow(id=sim_id or self.new_id("sim"))
            self._session.add(row)
        row.project_id = d.get("project_id", "")
        row.timestamp = d.get("timestamp")
        row.created_by = d.get("created_by")
        scalar_keys = {"id", "project_id", "timestamp", "created_by"}
        row.data = {k: v for k, v in d.items() if k not in scalar_keys}
        await self._session.flush()
        return _sim_result_to_dict(row)

    # ------------------------------------------------------------------
    # Private audit log helpers
    # ------------------------------------------------------------------

    async def _upsert_audit_log(self, d: dict[str, Any]) -> dict[str, Any]:
        row = await self._session.get(AuditLogRow, d.get("id"))
        if row is None:
            row = AuditLogRow(id=d.get("id") or self.new_id("audit"))
            self._session.add(row)
        row.timestamp = _parse_dt(d.get("timestamp"))
        row.user_id = d.get("user_id", "")
        row.user_name = d.get("user_name", "")
        row.action = d.get("action", "")
        row.entity_type = d.get("entity_type", "")
        row.entity_id = d.get("entity_id", "")
        row.description = d.get("description", "")
        row.old_value = d.get("old_value")
        row.new_value = d.get("new_value")
        await self._session.flush()
        return _audit_to_dict(row)

    # ------------------------------------------------------------------
    # Seed helper (used by reset())
    # ------------------------------------------------------------------

    async def _seed_from_defaults(self) -> None:
        """Insert the default state (from seeds.py) into all tables."""
        from ddm_v2.seeds import DEFAULT_STATE

        # Users (dict[username, dict])
        for uname, u in DEFAULT_STATE["users"].items():  # type: ignore[attr-defined]
            self._session.add(UserRow(
                username=uname, id=u["id"], password=u["password"],
                role=u["role"], name=u["name"],
            ))

        # Generic flat collections
        _generic_seed_map: dict[str, tuple[type, str]] = {
            "projects": (ProjectRow, ""),
            "syntax_library": (SyntaxLibraryRow, ""),
            "component_library": (ComponentLibraryRow, ""),
            "tool_library": (ToolLibraryRow, ""),
            "location_library": (LocationLibraryRow, ""),
            "object_library": (ObjectLibraryRow, ""),
            "from_locations": (FromLocationRow, ""),
            "to_locations": (ToLocationRow, ""),
            "reference_points": (ReferencePointRow, ""),
            "precautions": (PrecautionRow, ""),
            "precaution_rules": (PrecautionRuleRow, ""),
            "glove_rules": (GloveRuleRow, ""),
            "ion_fan_bindings": (IonFanBindingRow, ""),
            "mi_naming_rules": (MINamingRuleRow, ""),
            "level_system_templates": (LevelSystemTemplateRow, ""),
            "level_guidelines": (LevelGuidelineRow, ""),
            "employees": (EmployeeRow, ""),
            "stations": (StationRow, ""),
        }
        for key, (model_cls, _) in _generic_seed_map.items():
            for item in DEFAULT_STATE.get(key, []):
                row = model_cls()
                for k, v in item.items():  # type: ignore[attr-defined]
                    if hasattr(row, k):
                        setattr(row, k, v)
                self._session.add(row)

        # SOP versions (with nested actions)
        for version in DEFAULT_STATE.get("sop_versions", []):
            await self._upsert_sop_version(version)  # type: ignore[arg-type]

        await self._session.flush()

    # -----------------------------------------------------------------------
    # Video Uploads — Phase 5 Vision Engine
    # -----------------------------------------------------------------------

    def _video_upload_to_dict(self, row: VideoUploadRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "sop_version_id": row.sop_version_id,
            "project_id": row.project_id,
            "original_filename": row.original_filename,
            "stored_filename": row.stored_filename,
            "file_size": row.file_size,
            "duration_seconds": row.duration_seconds,
            "width": row.width,
            "height": row.height,
            "fps": row.fps,
            "status": row.status,
            "uploaded_by": row.uploaded_by,
            "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
            "error_message": row.error_message,
        }

    async def create_video_upload(self, data: dict[str, Any]) -> dict[str, Any]:
        """Persist a new ``VideoUploadRow`` from *data* (as returned by
        ``VideoService.save_and_record``) and return the resulting dict.
        """
        row = VideoUploadRow(
            id=data["id"],
            sop_version_id=data["sop_version_id"],
            project_id=data["project_id"],
            original_filename=data["original_filename"],
            stored_filename=data["stored_filename"],
            file_size=data.get("file_size"),
            duration_seconds=data.get("duration_seconds"),
            width=data.get("width"),
            height=data.get("height"),
            fps=data.get("fps"),
            status=data.get("status", "ready"),
            uploaded_by=data.get("uploaded_by"),
            uploaded_at=_parse_dt(data.get("uploaded_at")),
            error_message=data.get("error_message"),
        )
        self._session.add(row)
        await self._session.flush()
        return self._video_upload_to_dict(row)

    async def get_video_upload(self, upload_id: str) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(VideoUploadRow).where(VideoUploadRow.id == upload_id)
        )
        row = result.scalar_one_or_none()
        return self._video_upload_to_dict(row) if row else None

    async def list_video_uploads(self, sop_version_id: str) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(VideoUploadRow)
            .where(VideoUploadRow.sop_version_id == sop_version_id)
            .order_by(VideoUploadRow.uploaded_at)
        )
        return [self._video_upload_to_dict(r) for r in result.scalars().all()]

    async def delete_video_upload(self, upload_id: str) -> bool:
        """Delete the DB record.  Returns True if a row was deleted."""
        result = await self._session.execute(
            select(VideoUploadRow).where(VideoUploadRow.id == upload_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    async def update_video_upload_status(
        self,
        upload_id: str,
        status: str,
        error_message: str | None = None,
    ) -> dict[str, Any] | None:
        """Update the lifecycle ``status`` (and optionally ``error_message``) on a
        ``VideoUploadRow``.  Returns the updated dict or ``None`` when not found.
        """
        result = await self._session.execute(
            select(VideoUploadRow).where(VideoUploadRow.id == upload_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.status = status
        if error_message is not None:
            row.error_message = error_message
        await self._session.flush()
        return self._video_upload_to_dict(row)

    async def update_sop_action_timestamps(
        self, patches: list[dict[str, Any]]
    ) -> int:
        """Bulk-update ``video_timestamp_start`` / ``video_timestamp_end`` on
        ``SopAction`` rows from *patches*.

        Each patch dict must contain ``action_id`` and optionally
        ``video_timestamp_start`` / ``video_timestamp_end``.

        Returns the count of rows that were actually updated.
        """
        updated = 0
        for patch in patches:
            action_id = patch.get("action_id")
            if not action_id:
                continue
            result = await self._session.execute(
                select(SopActionRow).where(SopActionRow.id == action_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                continue
            if "video_timestamp_start" in patch:
                row.video_timestamp_start = patch["video_timestamp_start"]
            if "video_timestamp_end" in patch:
                row.video_timestamp_end = patch["video_timestamp_end"]
            updated += 1
        if updated:
            await self._session.flush()
        return updated

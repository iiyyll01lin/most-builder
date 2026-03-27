"""SQLAlchemy 2.0 ORM table models for all DDM v2 entities.

These classes are the authoritative DB-schema definition consumed by Alembic
for migration autogeneration. Route handlers NEVER touch these objects
directly — they receive and return plain ``dict`` values via ``PostgresStore``.

Mapping decisions (see Phase 1 architecture doc):
- JSONB / JSON columns: params, precautions, equipment_params, certifications,
  and all large nested payloads (workspace data, simulation data).
- Separate tables: sop_actions (FK → sop_versions), level_entries (scope_key).
- Soft FKs (no DB constraint): station_id in sop_actions, employee_id in stations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from ddm_v2.db.database import Base

# ────────────────────────────────────────────────────────────────────────────
#  Auth / Users
# ────────────────────────────────────────────────────────────────────────────


class UserRow(Base):
    """Application users.  PK is ``username`` (the natural lookup key)."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(255), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


# ────────────────────────────────────────────────────────────────────────────
#  Projects
# ────────────────────────────────────────────────────────────────────────────


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    process_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    factory: Mapped[str | None] = mapped_column(String(64), nullable=True)


# ────────────────────────────────────────────────────────────────────────────
#  SOP Versions & Actions
# ────────────────────────────────────────────────────────────────────────────


class SopVersionRow(Base):
    __tablename__ = "sop_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_no: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Eager-loaded via selectin so that list_collection("sop_versions") returns
    # fully-populated dicts without an N+1 query.
    sop_actions: Mapped[list[SopActionRow]] = relationship(
        "SopActionRow",
        back_populates="sop_version",
        cascade="all, delete-orphan",
        order_by="SopActionRow.sort_idx",
        lazy="selectin",
    )


class SopActionRow(Base):
    """Individual SOP action.

    ``sort_idx`` preserves the list order of actions within a version.
    ``params``, ``precautions``, and ``equipment_params`` are JSONB columns —
    they are always accessed atomically with the parent action row.
    """

    __tablename__ = "sop_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sop_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sop_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    seq_type: Mapped[str] = mapped_column(String(64), nullable=False, default="GENERAL")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tmu: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # JSONB columns — store arbitrary nested dicts / lists
    params: Any = Column(JSON, nullable=False, default=dict)
    precautions: Any = Column(JSON, nullable=False, default=list)
    equipment_params: Any = Column(JSON, nullable=True)
    # Scalar searchable fields
    station_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    component: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tool: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_ctq: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    primary_action: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hand: Mapped[str | None] = mapped_column(String(32), nullable=True)
    object_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    glove_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    level_tag: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_simo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    simo_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    required_skill: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Vision-engine anchor columns: ground-truth wall-clock seconds within the
    # linked VideoUpload file.  NULL until a Vision analysis has been run.
    video_timestamp_start: Mapped[float | None] = mapped_column(Float, nullable=True)
    video_timestamp_end: Mapped[float | None] = mapped_column(Float, nullable=True)

    sop_version: Mapped[SopVersionRow] = relationship("SopVersionRow", back_populates="sop_actions")


# ────────────────────────────────────────────────────────────────────────────
#  Video Uploads
# ────────────────────────────────────────────────────────────────────────────


class VideoUploadRow(Base):
    """Stores metadata for a workstation video uploaded against a SOP version.

    A ``SopVersion`` can have many associated uploads (different operators,
    camera angles, etc.).  The Vision Engine annotates each ``SopAction`` with
    ``video_timestamp_start`` / ``video_timestamp_end`` that refer to seconds
    within this file.
    """

    __tablename__ = "video_uploads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sop_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sop_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Original filename from the client's filesystem (for display only).
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    # UUID-based stored filename to avoid path-traversal and collisions.
    stored_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Extracted by VideoService; NULL when extraction is pending or failed.
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Lifecycle: pending → processing → ready | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    uploaded_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


# ────────────────────────────────────────────────────────────────────────────
#  Master Data — Library Tables
# ────────────────────────────────────────────────────────────────────────────


class SyntaxLibraryRow(Base):
    __tablename__ = "syntax_library"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action_verb: Mapped[str] = mapped_column(String(128), nullable=False)
    code_most: Mapped[str] = mapped_column(String(16), nullable=False)
    parameter_range: Mapped[str] = mapped_column(String(64), nullable=False)
    tmu_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ComponentLibraryRow(Base):
    __tablename__ = "component_library"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name_cn: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)


class ToolLibraryRow(Base):
    __tablename__ = "tool_library"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    spec: Mapped[str] = mapped_column(String(255), nullable=False)
    bit: Mapped[str | None] = mapped_column(String(64), nullable=True)


class LocationLibraryRow(Base):
    __tablename__ = "location_library"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class ObjectLibraryRow(Base):
    __tablename__ = "object_library"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    sub_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    glove_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ctq: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FromLocationRow(Base):
    __tablename__ = "from_locations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class ToLocationRow(Base):
    __tablename__ = "to_locations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class ReferencePointRow(Base):
    __tablename__ = "reference_points"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class PrecautionRow(Base):
    __tablename__ = "precautions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    process: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class PrecautionRuleRow(Base):
    __tablename__ = "precaution_rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_value: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(128), nullable=False, default="")


class GloveRuleRow(Base):
    __tablename__ = "glove_rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_category: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    glove_type: Mapped[str] = mapped_column(String(128), nullable=False)


class IonFanBindingRow(Base):
    __tablename__ = "ion_fan_bindings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_category: Mapped[str] = mapped_column(String(128), nullable=False)
    object_name: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")


class MINamingRuleRow(Base):
    __tablename__ = "mi_naming_rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class LevelSystemTemplateRow(Base):
    __tablename__ = "level_system_templates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class LevelGuidelineRow(Base):
    __tablename__ = "level_guidelines"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")


# ────────────────────────────────────────────────────────────────────────────
#  Employees & Stations
# ────────────────────────────────────────────────────────────────────────────


class EmployeeRow(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    station_type: Mapped[str] = mapped_column(String(64), nullable=False)
    skill_level: Mapped[str] = mapped_column(String(32), nullable=False)
    efficiency_factor: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    # JSONB: list[str] — always loaded atomically with the employee row
    certifications: Any = Column(JSON, nullable=False, default=list)


class StationRow(Base):
    __tablename__ = "stations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Soft FK — no DB constraint; validated by service layer
    employee_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


# ────────────────────────────────────────────────────────────────────────────
#  Level System Entries
# ────────────────────────────────────────────────────────────────────────────


class LevelEntryRow(Base):
    """Per-action level system metadata scoped by ``scope_key``.

    ``scope_key`` = ``"{project_id}::{sop_version_id or '__default__'}"``
    The unique constraint prevents duplicate entries for the same
    (scope, action) pair.
    """

    __tablename__ = "level_entries"
    __table_args__ = (UniqueConstraint("scope_key", "action_id", name="uq_level_entry_scope_action"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action_id: Mapped[str] = mapped_column(String(64), nullable=False)
    difficulty_factor: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    number_tag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    number_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    main_seq: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_seq: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cub_group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    machine_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    operator_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)


# ────────────────────────────────────────────────────────────────────────────
#  MOST Workspaces
# ────────────────────────────────────────────────────────────────────────────


class MostWorkspaceRow(Base):
    """MOST workspace scratchpad for a (project, sop_version) scope.

    The scalar ``id``, ``project_id``, and ``sop_version_id`` columns allow
    WHERE-clause lookups; all other workspace fields live in the ``data`` JSON
    blob and are always loaded as a unit.
    """

    __tablename__ = "most_workspaces"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sop_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Everything else (steps, wi_components, selected_step_ids, summary, actions)
    data: Any = Column(JSON, nullable=False, default=dict)


# ────────────────────────────────────────────────────────────────────────────
#  Simulation Results
# ────────────────────────────────────────────────────────────────────────────


class SimulationResultRow(Base):
    """Persisted line-balance simulation snapshots.

    Only ``id``, ``project_id``, ``timestamp``, and ``created_by`` are scalar
    columns; the full result payload lives in ``data``.
    """

    __tablename__ = "simulation_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timestamp: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data: Any = Column(JSON, nullable=False, default=dict)


# ────────────────────────────────────────────────────────────────────────────
#  Audit Logs
# ────────────────────────────────────────────────────────────────────────────


class AuditLogRow(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_name: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    old_value: Any = Column(JSON, nullable=True)
    new_value: Any = Column(JSON, nullable=True)

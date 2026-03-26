from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, model_validator

T = TypeVar("T")


class ErrorCode(str, Enum):
    not_found = "NOT_FOUND"
    forbidden = "FORBIDDEN"
    unauthorized = "UNAUTHORIZED"
    validation_error = "VALIDATION_ERROR"
    invalid_transition = "INVALID_STATUS_TRANSITION"
    conflict = "CONFLICT"
    bad_request = "BAD_REQUEST"
    internal_error = "INTERNAL_ERROR"


class ErrorDetail(BaseModel):
    error_code: ErrorCode
    message: str
    detail: Any = None


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int


class UserRole(str, Enum):
    manager = "Manager"
    engineer = "Engineer"
    operator = "Operator"


class SkillLevel(str, Enum):
    novice = "Novice"
    proficient = "Proficient"
    expert = "Expert"


class SOPStatus(str, Enum):
    draft = "Draft"
    reviewed = "Reviewed"
    published = "Published"


class AuditAction(str, Enum):
    create = "CREATE"
    update = "UPDATE"
    delete = "DELETE"
    review = "REVIEW"
    publish = "PUBLISH"
    reset = "RESET"


class LoginRequest(BaseModel):
    username: str
    password: str


class UserSummary(BaseModel):
    id: str
    username: str
    role: UserRole
    name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserSummary


class SimpleCatalogEntry(BaseModel):
    id: str | None = None
    name: str


class SyntaxEntry(BaseModel):
    id: str | None = None
    action_verb: str
    code_most: str
    parameter_range: str
    tmu_value: int = Field(ge=0)


class ComponentEntry(BaseModel):
    id: str | None = None
    name_cn: str
    name_en: str
    category: str


class ToolEntry(BaseModel):
    id: str | None = None
    name: str
    spec: str
    bit: str | None = None


class LocationEntry(BaseModel):
    id: str | None = None
    name: str


class ObjectEntry(BaseModel):
    id: str | None = None
    name: str
    category: str
    sub_category: str | None = None
    glove_type: str | None = None
    ctq: bool = False


class EmployeeEntry(BaseModel):
    id: str | None = None
    name: str
    station_type: str
    skill_level: SkillLevel
    efficiency_factor: float = Field(ge=0.5, le=1.5)
    certifications: list[str] = Field(default_factory=list)


class StationEntry(BaseModel):
    id: str
    name: str
    employee_id: str | None = None


class GloveCheckRequest(BaseModel):
    object_name: str | None = None
    object_category: str | None = None
    action: str | None = None


class GloveCheckResponse(BaseModel):
    glove_type: str | None
    matched_rule_id: str | None = None
    object_category: str | None = None


class MINamingValidationRequest(BaseModel):
    fields: dict[str, str | None] = Field(default_factory=dict)


class MINamingValidationResponse(BaseModel):
    is_valid: bool
    errors: list[str]
    suggested_name: str | None = None


class LevelNode(BaseModel):
    action_id: str
    tag: str


class LevelSystemValidateRequest(BaseModel):
    nodes: list[LevelNode]


class LevelSystemValidateResponse(BaseModel):
    is_valid: bool
    errors: list[str]


class LevelEntryUpdate(BaseModel):
    action_id: str
    difficulty_factor: float = Field(default=1.0, ge=0.5, le=3.0)
    number_tag: str | None = None
    number_count: int | None = Field(default=None, ge=1)
    main_seq: str | None = None
    order_seq: str | None = None
    cub_group: str | None = None
    machine_count: int = Field(default=1, ge=1)
    operator_count: int = Field(default=1, ge=1)
    status_label: str | None = None
    sort_order: int | None = Field(default=None, ge=0)


class LevelEntryResponse(BaseModel):
    id: str
    action_id: str
    row_no: int
    description: str
    ct_seconds: float
    frequency: int = 1
    difficulty_factor: float
    adjusted_ct: float
    number_tag: str | None = None
    number_count: int | None = None
    main_seq: str | None = None
    order_seq: str | None = None
    cub_group: str | None = None
    machine_count: int = 1
    operator_count: int = 1
    status_label: str | None = None
    effective_cub_ct: float | None = None
    sort_order: int | None = None


class LevelSystemSaveRequest(BaseModel):
    project_id: str
    sop_version_id: str | None = None
    entries: list[LevelEntryUpdate]


class LevelSystemSyncRequest(BaseModel):
    project_id: str
    sop_version_id: str | None = None


class OperatorTime(BaseModel):
    employee_id: str | None = None
    individual_tmu: int | None = None


class MOSTStep(BaseModel):
    action: str
    object: str | None = None
    seq_type: str = "GENERAL"
    hand: str | None = None
    object_category: str | None = None
    from_location: str | None = None
    to_location: str | None = None
    reference_point: str | None = None
    primary_action: str | None = None
    glove_type: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    frequency: int = 1
    is_simo: bool = False
    simo_group_id: str | None = None
    return_a_cm: float = 0.0
    is_collaborative: bool = False
    operator_count: int = 1
    operators: list[OperatorTime] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_collaborative_semantics(self) -> "MOSTStep":
        if self.is_collaborative and self.operator_count < 2:
            raise ValueError(
                f"Collaborative step '{self.action}' requires operator_count >= 2 "
                f"(got {self.operator_count}). A two-person simultaneous assembly "
                "must define at least 2 operators. Increase operator_count or "
                "disable is_collaborative."
            )
        if self.is_collaborative and 0 < len(self.operators) < 2:
            raise ValueError(
                f"Collaborative step '{self.action}' lists {len(self.operators)} "
                "operator(s), but at least 2 are required for a valid two-person "
                "assembly step. Add the missing operator's individual_tmu or "
                "disable is_collaborative."
            )
        return self


class MOSTCalculateRequest(BaseModel):
    steps: list[MOSTStep]


class MOSTBreakdown(BaseModel):
    action: str
    object: str
    tmu: int
    code: str
    seq_type: str
    hand: str | None = None
    glove_type: str | None = None
    object_category: str | None = None
    from_location: str | None = None
    to_location: str | None = None
    frequency: int = 1
    is_simo: bool = False
    index_string: str | None = None
    auto_sentence: str | None = None
    is_collaborative: bool = False
    operator_count: int = 1
    effective_tmu: int | None = None


class MOSTCalculateResponse(BaseModel):
    total_tmu: int
    total_seconds: float
    breakdown: list[MOSTBreakdown]
    simo_max_tmu: int | None = None
    simo_seconds: float | None = None
    # SIMO-adjusted totals: replaces total_tmu/total_seconds when simultaneous
    # motions are present, taking only the bottleneck hand per SIMO group.
    simo_adjusted_total_tmu: int | None = None
    simo_adjusted_total_seconds: float | None = None
    collaborative_effective_tmu: int | None = None
    collaborative_effective_seconds: float | None = None


class MOSTWorkspaceSaveRequest(BaseModel):
    sop_version_id: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    wi_components: list[dict[str, Any]] = Field(default_factory=list)
    selected_step_ids: list[str] = Field(default_factory=list)


class MOSTWorkspaceImportRequest(BaseModel):
    sop_version_id: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    wiComponents: list[dict[str, Any]] = Field(default_factory=list)
    selected_step_ids: list[str] = Field(default_factory=list)


class SOPAction(BaseModel):
    id: str | None = None
    seq_type: str
    description: str
    tmu: int
    seconds: float
    params: dict[str, Any] = Field(default_factory=dict)
    station_id: str | None = None
    component: str | None = None
    tool: str | None = None
    image_url: str | None = None
    is_ctq: bool = False
    primary_action: str | None = None
    hand: str | None = None
    object_category: str | None = None
    glove_type: str | None = None
    frequency: int = 1
    level_tag: str | None = None
    is_simo: bool = False
    simo_group_id: str | None = None
    required_skill: str | None = None


class SOPVersion(BaseModel):
    id: str | None = None
    project_id: str
    version_no: str
    status: SOPStatus = SOPStatus.draft
    actions: list[SOPAction] = Field(default_factory=list)
    created_by: str | None = None
    created_at: datetime | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    published_by: str | None = None
    published_at: datetime | None = None


class SOPCreateRequest(BaseModel):
    project_id: str
    version_no: str
    actions: list[SOPAction] = Field(default_factory=list)


class SOPUpdateStatusRequest(BaseModel):
    status: SOPStatus
    comment: str | None = None


class StationAssignment(BaseModel):
    id: str
    sop_ids: list[str] = Field(default_factory=list)
    employee_id: str | None = None
    machine_count: int = Field(default=1, ge=1, description="Number of machines this operator runs simultaneously (1P2M = 2)")


class LineBalanceRequest(BaseModel):
    project_id: str
    stations: list[StationAssignment]
    takt_time: float = Field(gt=0, description="Takt time in seconds; must be greater than zero")


class StationResult(BaseModel):
    id: str
    name: str
    operator: str
    skill_level: SkillLevel
    efficiency_factor: float
    standard_time: float
    actual_time: float
    machine_count: int = 1
    machine_effective_time: float | None = None
    actions: list[dict[str, Any]]
    is_overloaded: bool
    required_gloves: list[str] = Field(default_factory=list)
    ctq_actions: list[str] = Field(default_factory=list)
    ion_fan_required: bool = False
    ion_fan_targets: list[str] = Field(default_factory=list)
    skill_alerts: list[str] = Field(default_factory=list)


class BalanceReport(BaseModel):
    """Line balance efficiency KPIs — IE/PE summary of how evenly work is
    distributed across stations.

    Efficiency = ΣCT / (n × CT_max) × 100
    Loss      = 100 − Efficiency
    """

    balance_efficiency_pct: float = Field(
        description="Efficiency = ΣCT / (n × CT_max) × 100; 100% = perfectly balanced"
    )
    balance_loss_pct: float = Field(
        description="Balance loss = 100 − efficiency; >15% triggers redistribution review"
    )
    bottleneck_station_id: str = Field(
        description="Station ID with the longest effective cycle time"
    )


class LineBalanceResponse(BaseModel):
    bottleneck_station: str
    cycle_time: float
    uph: int
    balance_rate: float
    alerts: list[str]
    station_results: list[StationResult]
    balance_report: BalanceReport | None = None


class ActionReassignRequest(BaseModel):
    action_id: str
    from_station_id: str
    to_station_id: str


class AuditLogEntry(BaseModel):
    id: str
    timestamp: datetime
    user_id: str
    user_name: str
    action: AuditAction
    entity_type: str
    entity_id: str
    description: str
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None

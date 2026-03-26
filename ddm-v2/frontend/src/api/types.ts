// ─── Error contract ───────────────────────────────────────────────────────────

export type ErrorCode =
  | 'NOT_FOUND'
  | 'FORBIDDEN'
  | 'UNAUTHORIZED'
  | 'VALIDATION_ERROR'
  | 'INVALID_STATUS_TRANSITION'
  | 'CONFLICT'
  | 'BAD_REQUEST'
  | 'INTERNAL_ERROR'

export interface ValidationErrorItem {
  field: string
  message: string
}

export interface ApiErrorBody {
  error_code: ErrorCode
  message: string
  detail: ValidationErrorItem[] | null
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export type UserRole = 'Manager' | 'Engineer' | 'Operator'

export interface UserSummary {
  id: string
  username: string
  role: UserRole
  name: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: UserSummary
}

export interface LoginRequest {
  username: string
  password: string
}

// ─── SOP ──────────────────────────────────────────────────────────────────────

export type SOPStatus = 'Draft' | 'Reviewed' | 'Published'

export interface SOPAction {
  id?: string
  seq_type: string
  description: string
  tmu: number
  seconds: number
  params: Record<string, unknown>
  station_id?: string
  component?: string
  tool?: string
  image_url?: string
  is_ctq: boolean
  primary_action?: string
  hand?: string
  object_category?: string
  glove_type?: string
  frequency: number
  level_tag?: string
  is_simo: boolean
  simo_group_id?: string
  required_skill?: string
  /** Auto-binding precautions from the rule engine (LCD handling, electric screwdriver, etc.) */
  precautions?: string[]
  /** Equipment dynamic parameters for pressing tools: air_pressure_mpa, force_n_cm2 */
  equipment_params?: Record<string, string> | null
}

export interface SOPVersion {
  id?: string
  project_id: string
  version_no: string
  status: SOPStatus
  actions: SOPAction[]
  created_by?: string
  created_at?: string
  reviewed_by?: string
  reviewed_at?: string
  published_by?: string
  published_at?: string
}

export interface SOPVersionSummary {
  id: string
  version_no: string
  status: SOPStatus
  action_count: number
  created_at?: string
  published_at?: string
}

// ─── Level System ─────────────────────────────────────────────────────────────

export interface LevelEntryResponse {
  id: string
  action_id: string
  row_no: number
  description: string
  ct_seconds: number
  frequency: number
  difficulty_factor: number
  adjusted_ct: number
  number_tag?: string
  number_count?: number
  main_seq?: string
  order_seq?: string
  cub_group?: string
  machine_count: number
  operator_count: number
  status_label?: string
  effective_cub_ct?: number
  sort_order?: number
}

// ─── Precedence Graph ─────────────────────────────────────────────────────────

export interface PrecedenceNode {
  id: string
  description: string
  original_ct: number
  difficulty_factor: number
  adjusted_ct: number
  effective_ct: number
  main_seq?: string
  order_seq?: string
  cub_group?: string
  number_tag?: string
  number_count?: number
  machine_count: number
  operator_count: number
  status_label?: string
}

export interface PrecedenceEdge {
  from: string
  to: string
  type: string
}

export interface PrecedenceGraph {
  project_id: string
  sop_version_id?: string
  nodes: PrecedenceNode[]
  precedence_edges: PrecedenceEdge[]
  cub_groups: Record<string, string[]>
  number_constraints: Record<string, { limit: number; actions: string[] }>
  total_adjusted_ct: number
  total_effective_ct: number
  cycle_errors: string[]
}

// ─── BFF Dashboard ────────────────────────────────────────────────────────────

export interface WorkspaceSummary {
  id?: string
  project_id: string
  sop_version_id?: string
  saved_at?: string
  version: number
  steps: unknown[]
  wi_components: unknown[]
  selected_step_ids: string[]
  summary: {
    total_tmu: number
    total_seconds: number
    step_count: number
    component_count: number
  }
  actions: unknown[]
}

export interface DashboardResponse {
  project: Record<string, unknown>
  sop_versions: SOPVersionSummary[]
  active_sop_version_id?: string
  workspace: WorkspaceSummary
  level_system: {
    sop_version_id?: string
    entries: LevelEntryResponse[]
    total_count: number
  }
  precedence_graph?: PrecedenceGraph
}

// ─── Simulation ───────────────────────────────────────────────────────────────

export type SkillLevel = 'Novice' | 'Proficient' | 'Expert'

export interface StationAssignment {
  id: string
  sop_ids: string[]
  employee_id?: string
  machine_count?: number
}

export interface LineBalanceRequest {
  project_id: string
  stations: StationAssignment[]
  takt_time: number
}

export interface StationResult {
  id: string
  name: string
  operator: string
  skill_level: SkillLevel
  efficiency_factor: number
  standard_time: number
  actual_time: number
  actions: Record<string, unknown>[]
  is_overloaded: boolean
  required_gloves: string[]
  ctq_actions: string[]
  ion_fan_required: boolean
  ion_fan_targets: string[]
  machine_count?: number
  machine_effective_time?: number | null
  skill_alerts?: string[]
  /** Aggregated auto-binding precaution texts for all actions at this station */
  precautions?: string[]
}

// ─── Master Data ──────────────────────────────────────────────────────────────

export interface EmployeeEntry {
  id: string
  name: string
  skill_level: SkillLevel
  efficiency_factor: number
  certifications: string[]
}

export interface ObjectEntry {
  id: string
  name: string
  category: string
  glove_type?: string
  is_ctq?: boolean
  required_skill?: string
}

export interface StationEntry {
  id: string
  name: string
  employee_id?: string
}

// ─── MI Naming ────────────────────────────────────────────────────────────────

export interface MINamingValidateRequest {
  fields: Record<string, string>
}

export interface MINamingValidateResponse {
  is_valid: boolean
  errors: string[]
  suggested_name: string | null
}

export interface LineBalanceResponse {
  bottleneck_station: string
  cycle_time: number
  uph: number
  balance_rate: number
  alerts: string[]
  station_results: StationResult[]
  balance_report?: BalanceReport
}

/** Line Balance Efficiency KPIs returned by the balancing algorithm. */
export interface BalanceReport {
  /** Efficiency = ΣCT / (n × CT_max) × 100 */
  balance_efficiency_pct: number
  /** Balance loss = 100 − efficiency */
  balance_loss_pct: number
  /** Station ID with the longest effective cycle time */
  bottleneck_station_id: string
}

export interface AsyncJobResponse {
  job_id: string
  status: string
}

export interface SimProgressEvent {
  progress: number
  status: string
  result?: LineBalanceResponse & {
    id: string
    timestamp: string
    project_id: string
    created_by: string
  }
  error?: string
}

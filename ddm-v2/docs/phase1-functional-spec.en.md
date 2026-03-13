# DDM Phase 1 Functional Specification

## 1. Purpose

This document describes the complete functional scope of the legacy DDM Phase 1 system implemented in the files below:

- `/tmp-ddm/ddm_p1_full.html`
- `/tmp-ddm/backend/main.py`
- `/tmp-ddm/docker-compose.yml`
- `/tmp-ddm/Dockerfile`
- `/tmp-ddm/nginx.conf`
- `/tmp-ddm/start.sh`

The target audience is software engineers redesigning and rebuilding the system in a maintainable, testable codebase.

## 2. Product Intent

The system is an industrial engineering platform used to:

1. Build MiniMOST actions and time studies.
2. Compose those actions into SOP steps.
3. Maintain level-system metadata required for line balancing constraints.
4. Simulate line balancing across stations and employees.
5. Maintain supporting master data.
6. Persist operational data and expose audit history.

## 3. Legacy Architecture Summary

### 3.1 Frontend

- Single HTML file using CDN-hosted Tailwind CSS, React 18 UMD, ReactDOM 18 UMD, and Babel standalone.
- All UI logic, state, business logic helpers, rendering, and API access are embedded in one script block.
- No build pipeline, no linting, no module boundaries, no frontend tests.

### 3.2 Backend

- Single FastAPI module containing configuration, data seeds, domain logic, persistence helpers, Pydantic models, and all API routes.
- JSON-file persistence stored in `data/db_persistent.json`.
- JWT-style token login with in-memory seeded demo users.
- Static file serving for the single-page frontend.

### 3.3 Deployment

- Nginx serves frontend and reverse-proxies `/api/` to local Uvicorn.
- Docker image packages nginx, backend, and static frontend in one container.

## 4. Actors and Roles

### 4.1 Roles

- Manager
- Engineer
- Operator

### 4.2 Role Intent

- Manager: full administrative access, including destructive actions and publication.
- Engineer: can author and update operational data but cannot perform manager-only deletes or publish workflows.
- Operator: read-only or heavily restricted access, limited to published or assigned operational views.

## 5. Functional Modules

## 5.1 Authentication and Session

### User-visible behavior

- Login screen with prefilled demo credentials.
- Token-based authenticated API usage.
- Logout clears client state.

### Backend behavior

- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`

### Rules

- Invalid credentials return 401.
- Token includes username, role, and expiry.
- Most endpoints require bearer token authentication.

## 5.2 Global Context Selection

### User-visible behavior

- User can select a project.
- User can select a SOP version scoped to that project.
- The selected project/version drives MOST save behavior, level-system loading, and SOP context.

### Data involved

- Projects
- SOP versions

### Rules

- If no project is selected, MOST authoring cannot be committed into SOP context.
- Default SOP version selection prefers Draft when available.

## 5.3 Dashboard

### User-visible behavior

- Summary cards for projects, SOP versions, and recent audit logs.

### Purpose

- High-level operational overview only.

## 5.4 MOST Engine

This is the core authoring module.

### 5.4.1 Sequence authoring

Users can create MiniMOST steps using two sequence types:

- General Move: `A B G A B P A`
- Controlled Move: `A B G M X I A`

### 5.4.2 Parameter editing

The system supports parameter entry for:

- Reach/move indexes
- Body motion indexes
- Grasp indexes
- Placement indexes
- Controlled move indexes
- Process time indexes
- Inspection/alignment indexes
- Return distance
- Frequency multiplier
- SIMO flag
- Hand selection
- Collaborative operator metadata

### 5.4.3 Input helpers

- Distance lookup tables for A and M indexes.
- Tool-action mappings.
- P-modifier toggles.
- Auto-generated index string.
- Auto-generated Chinese MI sentence.
- JSON-based advanced parameter input with validation.

### 5.4.4 Object and context selection

- Object picker with search and category filtering.
- Multiple object selection.
- From-location, to-location, and reference-point selection.
- Automatic glove recommendation preview based on object/action.

### 5.4.5 Action template library

- Built-in common action templates.
- User-authored action templates.
- Template editing and drag/drop into composer.

### 5.4.6 Composer

- Drag/drop sequence assembly.
- Timeline and list views.
- Step editing and deletion.
- Step reordering.
- Step frequency adjustment.
- CTQ toggle.
- SIMO toggle.

### 5.4.7 MI output area

- Displays generated MI sentences.
- Displays TMU/seconds summaries.
- Displays WI component library built from selected steps.
- Supports WI component export/import as JSON.

### 5.4.8 MOST calculation service

Backend endpoint:

- `POST /api/v1/most/calculate`

Supported calculation concerns:

- TMU derivation from parameters.
- Fixed TMU actions.
- Dynamic X-time conversion from seconds to TMU.
- I-action out-of-sight handling.
- Frequency multiplication.
- SIMO summary calculation.
- Collaborative effective time using max operator time.
- Auto sentence and index string generation.
- Glove inference.

### 5.4.9 Save to SOP

- MOST steps can be converted into SOP actions.
- If no Draft SOP exists for the selected project, the UI attempts to create one automatically.
- Save operation also syncs level-system entries.

## 5.5 Level System

### User-visible behavior

- Load project-specific level entries derived from SOP actions.
- Edit level metadata per MI action.
- Drag/drop reorder level rows.
- Save or upload the level-system state.

### Editable fields

- Difficulty factor
- Adjusted CT
- Number tag
- Number count
- Main sequence
- Order sequence
- Cub group
- Machine count
- Operator count
- Status label
- Sort order

### Backend endpoints

- `GET /api/v1/level-system/templates`
- `GET /api/v1/level-system/guidelines`
- `POST /api/v1/level-system/validate`
- `GET /api/v1/level-system/{project_id}`
- `POST /api/v1/level-system/sync`
- `POST /api/v1/level-system/save`
- `POST /api/v1/level-system/generate-graph`

### Intended logic

- Synchronize existing SOP actions into level entries.
- Preserve user-edited metadata for scheduling logic.
- Support Cub effective CT calculation using machine/operator divisor.
- Support precedence graph generation for line-balance optimization.

## 5.6 SOP Studio

### User-visible behavior

- Display selected SOP version metadata.
- Display a video player for time-study workflow.
- Display a SOP timeline with step images.
- Export SOP content.
- Advance SOP status to Reviewed or Published.

### Backend endpoints

- `GET /api/v1/sop/versions`
- `POST /api/v1/sop/versions`
- `GET /api/v1/sop/versions/{sop_id}`
- `PUT /api/v1/sop/versions/{sop_id}/status`
- `PUT /api/v1/sop/versions/{sop_id}/actions`

### Workflow rules

- Draft can move to Reviewed.
- Reviewed can move to Published.
- Manager can directly publish from Draft.
- Only Draft SOPs can have actions updated.
- Operators should only access Published SOPs.

## 5.7 Line Balance Simulation

### User-visible behavior

- Configure station assignments.
- Assign employees to stations.
- Drag/drop actions across stations.
- Run line-balance simulation.
- View overloaded stations, bottleneck, cycle time, UPH, balance rate, alerts, glove requirements, CTQ indicators, and ion-fan requirements.
- Display Yamazumi chart.
- View simulation history.
- Export line report.

### Backend endpoints

- `GET /api/v1/master/stations`
- `POST /api/v1/master/stations`
- `PUT /api/v1/master/stations/{station_id}`
- `DELETE /api/v1/master/stations/{station_id}`
- `POST /api/v1/simulation/line-balance`
- `POST /api/v1/simulation/reassign-action`
- `GET /api/v1/simulation/history`
- `GET /api/v1/simulation/history/{sim_id}`
- `DELETE /api/v1/simulation/history/{sim_id}`
- `DELETE /api/v1/simulation/history`

### Simulation logic

- Aggregate SOP actions by station.
- Compute standard time from action seconds.
- Apply employee efficiency factor to derive actual time.
- Flag takt overloads.
- Detect CTQ skill mismatches for novice employees.
- Accumulate glove and ion-fan requirements.
- Compute bottleneck, cycle time, UPH, and balance rate.
- Persist simulation snapshots in history.

## 5.8 Master Data Management

### Managed entities

- Syntax library
- Component library
- Tool library
- Location library
- Object library
- Employee library
- Station library

### Reference data exposed read-only

- From-locations
- To-locations
- Reference points
- Precautions
- Glove rules
- Ion-fan bindings
- MI naming rules
- Level templates
- Level guidelines

### Backend endpoints

- `/api/v1/master/syntax`
- `/api/v1/master/components`
- `/api/v1/master/tools`
- `/api/v1/master/locations`
- `/api/v1/master/objects`
- `/api/v1/master/employees`
- `/api/v1/master/stations`
- `/api/v1/master/from-locations`
- `/api/v1/master/to-locations`
- `/api/v1/master/reference-points`
- `/api/v1/master/precautions`
- `/api/v1/master/glove-rules`
- `/api/v1/master/ion-fan-bindings`
- `/api/v1/master/mi-naming`

### Role constraints

- Operators cannot create or update master data.
- Deletes are often manager-only.

## 5.9 MI Naming Validation

### User-visible behavior

- Form-driven naming fields generated from rules.
- Explicit validation action.
- Suggested output name.

### Backend endpoint

- `POST /api/v1/mi-naming/validate`

## 5.10 Glove Recommendation

### User-visible behavior

- Preview glove recommendation during MOST authoring.
- Display glove requirements in line-balance results.

### Backend endpoint

- `POST /api/v1/gloves/check`

## 5.11 Audit Trail

### User-visible behavior

- Dashboard and audit tab expose recent or filtered audit records.

### Backend endpoint

- `GET /api/v1/audit/logs`

### Rules

- Managers can inspect broader audit scope.
- Non-managers are restricted to their own actions.

## 5.12 Database Persistence and Export

### User-visible behavior

- View persistence status.
- Trigger manual save.
- Export current database snapshot.

### Backend endpoints

- `POST /api/v1/db/save`
- `POST /api/v1/db/load`
- `GET /api/v1/db/status`
- `DELETE /api/v1/db/reset`
- `GET /api/v1/db/export`

### Rules

- Persistence is JSON-file based.
- Some operations are manager-only.

## 6. Data Domains

Primary persisted domains in the legacy system:

- Users
- Projects
- Syntax library
- Component library
- Tool library
- Location library
- Object library
- Employees
- Stations
- SOP versions
- Level entries
- Audit logs
- Simulation results
- Reference catalogs for gloves, ion-fan bindings, MI naming, and guidelines

## 7. Non-Functional Characteristics of the Legacy System

### Strengths

- Fast to prototype.
- Full workflow exists in one deployable artifact.
- Business rules are largely embedded in executable code.

### Risks

- Frontend and backend are both monolithic.
- Business logic duplicated between frontend and backend.
- No type-safe boundary between UI and API.
- Missing module boundaries and weak testability.
- Heavy client-side state coupling.
- Persistence is file-based and non-transactional.
- No formal schema migration story.
- No release-grade automated tests.

## 8. Known Gaps and Legacy Inconsistencies

These are important for redesign because they represent either defects or architectural debt:

1. The frontend calls `/api/v1/most/validate-level`, but no matching backend route exists.
2. Some delete endpoints appear incorrectly nested in the backend source and may never be registered as intended.
3. Frontend contains disabled logic related to MI naming auto-validation due to previous infinite-call behavior.
4. Similar domain logic exists in both frontend and backend, creating divergence risk.
5. Station state is partly managed locally in the UI and partly persisted on the backend.
6. The legacy app mixes view logic, orchestration logic, domain calculation, and persistence triggers in the same files.

## 9. Rebuild Requirements Derived From the Legacy System

The replacement codebase must preserve these capabilities:

1. Authenticated role-aware access.
2. MOST step authoring with sequence-specific parameter handling.
3. Accurate TMU/time calculation, including frequency, SIMO, and collaborative cases.
4. SOP versioning and status workflow.
5. Level-system synchronization, editing, and graph generation.
6. Line-balance simulation with employee efficiency and alert generation.
7. Master-data CRUD and reference catalogs.
8. Auditability and persistence.
9. Import/export workflows required by engineers.

The replacement should additionally provide:

1. Modular architecture.
2. Clear domain boundaries.
3. Automated tests at unit, functional, E2E, and regression levels.
4. Reproducible local setup.
5. Release-ready quality gates.

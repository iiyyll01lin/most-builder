# DDM v2 — Architecture Deep Dive

> This document covers internal architecture, data flows, AI/ML algorithms, and deployment topology for contributors and technical evaluators.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Backend Stack](#backend-stack)
3. [Frontend Stack](#frontend-stack)
4. [AI / LLM Pipeline](#ai--llm-pipeline)
5. [Computer Vision Pipeline](#computer-vision-pipeline)
6. [Generative BI & Text-to-SQL Sandbox](#generative-bi--text-to-sql-sandbox)
7. [Real-Time IoT Layer](#real-time-iot-layer)
8. [Domain Rule Engine](#domain-rule-engine)
9. [Deployment Model](#deployment-model)
10. [Database Schema](#database-schema)
11. [Security Model](#security-model)

---

## System Overview

```
                         ┌──────────────────────────────┐
                         │       Browser (React 18)      │
                         │  Zustand · RQ · R3F · Recharts│
                         └──────────┬───────────┬────────┘
                  REST / JSON       │           │  WebSocket
          ┌────────────────────────▼───┐   ┌───▼────────────────┐
          │    FastAPI (Uvicorn async) │   │  /ws/telemetry      │
          │  JWT RBAC · Pydantic v2   │   │  (fan-out broker)   │
          │  SQLAlchemy 2.0 async ORM │   └────────┬───────────┘
          └──┬──────┬────────┬────────┘            │ subscribe
             │      │        │                ┌────▼────────────┐
        asyncpg  Celery    OpenAI             │ Mosquitto MQTT  │
             │   task     GPT-4o-mini         │  (IoT devices)  │
    ┌────────▼─┐  │                           └────────────────┘
    │ PostgreSQL│  │ worker
    │    15     │  │
    └──────────┘ ┌▼──────────────────────────────┐
                 │       Celery Worker            │
                 │  MediaPipe · OpenCV · TMU algo │
                 └───────────────────────────────┘
```

All services are co-located in a single `docker-compose.yml` for development and distributed across signed Kubernetes manifests for production.

---

## Backend Stack

### FastAPI Application (`src/ddm_v2/main.py`)

The application follows the **lifespan pattern** introduced in FastAPI 0.93+. On startup it:

1. Calls `init_db()` to run Alembic migrations in-process and seed default data.
2. Initialises the `AsyncEngine` (asyncpg dialect for production, aiosqlite for tests).
3. Registers all routers under `/api/v1/`.

All request handlers receive an `AsyncSession` via `Depends(get_db)` — a per-request scoped session that is committed or rolled back within the same coroutine.

### Database & ORM

| Component | Choice | Reason |
|---|---|---|
| ORM | SQLAlchemy 2.0 async | Native `async with session.begin()`, avoids N+1 via `selectinload` |
| Driver | asyncpg (prod) / aiosqlite (test) | Non-blocking I/O; test isolation with `pytest-asyncio` |
| Migrations | Alembic (auto-generate) | Schema diff tracked alongside code |
| Repo pattern | `postgres_store.py` | Decouples service logic from ORM; testable with in-memory SQLite |

### Celery Task Queue (`src/ddm_v2/core/celery_app.py`)

Vision video analysis is dispatched as a Celery task and polled by the frontend via a `GET /api/v1/video/status/{job_id}` endpoint. This prevents the HTTP request from timing out on large uploads (tested to ~1.2 GB).

Workers run in the same Docker network and share the PostgreSQL DSN via environment variable; results are stored in the Redis backend.

### Alembic Migrations

Migrations live in `alembic/versions/`. Running `make db-upgrade` (or `alembic upgrade head` in the container) applies all pending migrations. The `env.py` imports `Base.metadata` from `src/ddm_v2/models/domain.py` to support auto-generation.

---

## Frontend Stack

### Technology Choices

| Library | Role |
|---|---|
| React 18 + TypeScript | UI framework with Strict Mode |
| Vite | Sub-second HMR dev server; `vite build` for production |
| Tailwind CSS | Utility-first styling, dark mode toggle |
| Zustand | Lightweight global state (auth token, active view) |
| TanStack Query (React Query) | Server-state cache; automatic background re-fetches for simulation history |
| React Three Fiber + Three.js | Declarative 3D scene for the Digital Twin view |
| @react-three/drei | Orbit controls, HTML labels, Sphere/Box primitives |
| @xyflow/react | DAG renderer for SOP precedence graphs |
| Recharts | BI chart rendering (BarChart, LineChart, PieChart, ScatterChart) |

### Key Pages / Views

```
App.tsx
├── ProjectDashboard       (SOP Workspace — default view)
│   ├── SopEditor          (MOST action table, AI generation, approval workflow)
│   ├── DigitalTwinView    (React Three Fiber live 3D station floor)
│   ├── SimulationPanel    (Line-balance chart, bottleneck heatmap)
│   └── VideoSopWorkspace  (Video Player + timestamp-anchored SOP review)
└── FactoryManagerDashboard (Factory Manager AI — Generative BI chat feed)
    ├── Suggestion chips
    ├── ChatEntry[]         (user + assistant messages)
    └── DynamicChartRenderer (auto-selects BarChart / LineChart / PieChart / Grid)
```

### WebSocket Client

`digital_twin_view.tsx` connects to `ws://<host>/ws/telemetry` and dispatches incoming `TelemetryEvent` payloads into the Zustand store. The 3D scene reacts to `station_id` → colour transition (green pulse for OK, red for fault) in fewer than two render cycles.

---

## AI / LLM Pipeline

### SOP Co-Pilot (GPT-4o-mini, Function Calling)

```
User clicks "Generate SOP"
        │
        ▼
ai_service.generate_sop_actions()
        │
        ├─ Builds system prompt with:
        │    • Project context (product, takt time)
        │    • Station constraints (ESD zone, glove rule, CTQ flags)
        │    • Certified sub-operation catalogue
        │    • MOST syntax whitelist
        │
        ├─ OpenAI function call → structured JSON (list of SOPAction)
        │
        ├─ Post-process: bind precautions, normalise TMU, set CTQ flags
        │
        └─ Return List[SOPActionCreate] to route handler
```

GPT-4o-mini is called with `tool_choice="required"` and a single tool schema (`create_sop_actions`) so the output is always valid JSON without regex parsing.

### AI SOP Review

`ai_service.review_sop()` batches all published actions for a station and calls GPT-4 again with a `review_sop` function schema. The response includes per-action `severity` (`ok | warning | error`), `remark`, and an overall `score`. Results are stored in the `SOPReviewResult` table and surfaced in the SOP editor UI.

### Offline / Mock Mode

When `OPENAI_API_KEY` is not set, `ai_service.py` detects the absence and returns deterministic mock payloads. This allows all 124 unit tests to pass without network access or API credits.

---

## Computer Vision Pipeline

### Overview

```
Video Upload (MP4/AVI)
        │
Celery Task: analyze_video()
        │
        ├─ Frame extraction (OpenCV VideoCapture)
        │
        ├─ TimelineSegmenter
        │    • Sliding window energy accumulation
        │    • _IDLE_THRESHOLD = 0.12  (frames below this → idle boundary)
        │    • _MIN_SEGMENT_DURATION = 0.20 s
        │    • _MIN_SEGMENT_GAP = 0.30 s
        │
        ├─ ActionClassifier (per segment)
        │    • motion_bias = "central" | "lateral"
        │      – central  → Grasp (G) + Place (P) candidates
        │      – lateral  → Reach (A) + Move (A) candidates
        │    • mean_energy → A-index via _snap_to_most_index()
        │
        └─ VisionService.build_subcycles()
             • Emits 4-step MOST subcycle per segment:
               Reach-A → Grasp-G → Move-A → Place-P
             • Returns List[ActionCandidate] with video_timestamp_seconds
```

### Motion Density → TMU Algorithm

```python
_MOST_INDICES = (0, 1, 3, 6, 10, 16, 24, 32)  # discrete A-index values
_TMU_FACTOR   = 0.036                           # seconds per TMU at normal pace

def _snap_to_most_index(value: int) -> int:
    """Snap a raw A-index to the nearest legal MOST A-index."""
    return min(_MOST_INDICES, key=lambda x: abs(x - value))

def _duration_to_a_index(duration_seconds: float) -> int:
    raw = round(duration_seconds / _TMU_FACTOR)
    return _snap_to_most_index(raw)
```

Each `ActionCandidate` carries:
- `sop_sequence_hint` — the matched SOP action sequence number (matched by `station_id + action_order`)
- `tmu_estimate` — the computed TMU value
- `video_timestamp_seconds` — playback offset for the frontend Video SOP Workspace

The Vision Engine operates in two modes:
- `"opencv"` — frame differencing only (no GPU required, safe for CI)
- `"mediapipe"` — body pose + hand landmark detection via MediaPipe (higher accuracy, CPU-intensive)

---

## Generative BI & Text-to-SQL Sandbox

### End-to-End Flow

```
User types: "Show total TMU by station for Project Alpha"
        │
POST /api/v1/bi/query  (JWT required)
        │
bi_service.generate_bi_report(query, session)
        │
        ├─ 1. schema_inspector.get_bi_schema_ddl()
        │       • Reads SQLAlchemy Base.metadata
        │       • Filters to 13 BI-safe tables (excludes users, most_workspaces)
        │       • Returns compact CREATE TABLE DDL strings
        │
        ├─ 2. _call_llm(query, schema_ddl)
        │       • OpenAI function call (mode: "sql_query_result")
        │       • Returns raw SQL string
        │       • Falls back to _mock_llm_bi_response() if no API key
        │
        ├─ 3. validate_select_only(sql)  ← THREE LAYERS
        │       Layer 1: re.compile(r"^\s*(?:with|select)\b")
        │                Must start with SELECT or WITH
        │       Layer 2: _DANGEROUS_KEYWORDS regex (30+ patterns)
        │                Blocks INSERT, UPDATE, DELETE, DROP, EXEC, COPY, etc.
        │       Layer 3: Applied at execution time by ReadOnlySQLExecutor
        │                "SET TRANSACTION READ ONLY" before every query (PostgreSQL)
        │
        ├─ 4. ReadOnlySQLExecutor.execute(sql)
        │       • Auto-appends LIMIT 1000 if no LIMIT present
        │       • Executes inside an explicit read-only transaction
        │       • Returns rows + column names
        │
        └─ 5. Build BIPayload
               {
                 "type": "bar" | "line" | "pie" | "table" | "metric",
                 "data": [...],
                 "columns": [...],
                 "xAxis": "station_name",
                 "yAxis": "total_tmu",
                 "insight": "Station ST-3 accounts for 34% of total TMU.",
                 "sql_query": "SELECT ..."
               }
```

### DynamicChartRenderer (Frontend)

The component receives a `BIPayload` and delegates to the correct Recharts primitive:

```typescript
switch (payload.type) {
  case 'bar':    return <BarChart  data={payload.data} />;
  case 'line':   return <LineChart data={payload.data} />;
  case 'pie':    return <PieChart  data={payload.data} />;
  case 'table':  return <DataGrid  rows={payload.data} columns={payload.columns} />;
  case 'metric': return <MetricCard value={payload.data[0]?.value} />;
}
```

A 10-colour TABLEAU palette is applied consistently across all chart types for visual coherence.

---

## Real-Time IoT Layer

### Architecture

```
IoT Device / Demo Orchestrator
        │  MQTT publish
        ▼
Eclipse Mosquitto 2  (port 1883)
        │
aiomqtt subscriber task  (started in FastAPI lifespan)
        │
telemetry_service.handle_mqtt_message()
        │  parse + enrich
        ▼
ConnectionManager.broadcast(json_payload)
        │  asyncio fan-out
        ▼
All connected WebSocket clients (/ws/telemetry)
```

### Event Schema

```json
{
  "station_id": "ALPHA-ST-2a",
  "event_type": "fasten_ok",
  "operator_id": "EMP-001",
  "sop_action_id": 7,
  "timestamp": "2026-01-14T10:23:45.123Z",
  "metadata": { "torque_nm": 2.4, "1p2m_peer": "ALPHA-ST-2b" }
}
```

### 1P2M Layout

The demo seed includes a **1 Operator / 2 Machine** station pair (`ALPHA-ST-2a` / `ALPHA-ST-2b`). The demo orchestrator fires two MQTT events 300 ms apart to simulate the operator pivoting between machines. The 3D Digital Twin renders both machines simultaneously, illustrating the ergonomic and takt-time implications of the layout.

---

## Domain Rule Engine

### MOST Calculation Engine (`services/most_service.py`)

MOST (Maynard Operation Sequence Technique) is an industrial engineering method for predicting task time. Each action is encoded as a sequence of lettered parameters with numeric indices:

```
Sequence Category A (General Move):  A? B? G? A? B? P? A?
Sequence Category B (Controlled):    A? B? G? M? X? I? A?
Sequence Category C (Tool Use):      A? B? G? A? B? P? A? + tool params
```

The `calculate_tmu(sequence_code)` function:
1. Parses the sequence string with a strict regex
2. Validates every index is in the legal discrete set for its letter
3. Sums all letter-index products by the official TMU lookup table
4. Returns `(tmu_value, breakdown_dict, validation_errors[])`

### Constraint Engine

When generating SOPs, the AI service injects the following hard constraints from station metadata:

| Constraint | Source | Effect |
|---|---|---|
| `requires_esd_protection` | Station model | Adds ESD precaution to every action at that station |
| `required_glove_type` | Station model | Adds glove-change precaution if switching between stations |
| `ctq_flag` | Action model | Marks the action as Critical-to-Quality; review score penalty if missing |
| `required_skill_level` | Action model | Gate: operator's `skill_level` must be ≥ action requirement |
| `required_tool_ids` | Action model | Validates tool is available in station's tooling list |

---

## Deployment Model

### Docker Compose (Development / Single-Node)

```yaml
services:
  postgres:     image: postgres:15-alpine
  redis:        image: redis:7-alpine
  mosquitto:    build: mosquitto/
  ddm-v2:       build: .             # FastAPI backend; also serves frontend dist
  celery_worker: build: .            # CMD: celery worker
  frontend:     build: frontend/    # Vite dev server (dev mode only)
```

The backend Dockerfile is multi-stage: a `builder` stage installs wheels from `docker-wheels/` (offline-capable), and the `runtime` stage copies only the installed site-packages, keeping the final image under 400 MB.

### Kubernetes (Production)

Manifests in `k8s/`:

| File | Resource |
|---|---|
| `namespace.yaml` | `ddm-v2` namespace |
| `configmap.yaml` | Non-secret env vars (DB host, MQTT host) |
| `secrets.yaml` | Base64-encoded `DATABASE_URL`, `SECRET_KEY`, `OPENAI_API_KEY` |
| `postgres-statefulset.yaml` | PostgreSQL 15 StatefulSet with PVC |
| `redis.yaml` | Redis Deployment |
| `mosquitto.yaml` | Mosquitto MQTT Deployment |
| `backend-deployment.yaml` | 2-replica Deployment, non-root (UID 1001), rolling update |
| `celery-worker.yaml` | Celery worker Deployment |
| `frontend.yaml` | Nginx-served SPA Deployment |
| `ingress.yaml` | Nginx Ingress: `/api/*` → backend, `/*` → frontend |

**Production-grade features:**
- Rolling update: `maxSurge: 1 / maxUnavailable: 0` (zero-downtime deploys)
- Non-root security context: `runAsUser: 1001 / runAsNonRoot: true`
- WebSocket support: `proxy-read-timeout: 86400` on ingress annotations
- TLS-ready: `cert-manager.io/cluster-issuer` annotation pre-configured
- Liveness and readiness probes on `GET /health` (5 s interval)

### Makefile Targets

```
make demo          # Full one-command demo (down → build → seed → orchestrate)
make up            # docker compose up --build -d
make down          # docker compose down
make seed          # Load Project Alpha seed data into running stack
make test          # pytest tests/unit
make test-all      # pytest tests/
make build         # docker compose build
make logs          # docker compose logs -f
make shell         # exec into backend container
make clean         # Prompt for confirmation, then tear down all volumes
```

---

## Database Schema

Core tables (simplified; see `src/ddm_v2/models/domain.py` for full definition):

```
projects ──< stations ──< sop_versions ──< sop_actions
                │                              │
                │                         level_entries
                │
                ├──< video_uploads ──< vision_action_candidates
                │
                └──< simulation_results

employees ──< sop_actions (created_by, approved_by)
users ──< audit_log_entries
```

All tables include `created_at / updated_at` timestamps managed by SQLAlchemy event listeners. Soft-delete is implemented via `is_deleted` boolean on mutable entities.

---

## Security Model

### Authentication

JWT tokens are issued at `POST /api/v1/auth/login` with a 24-hour expiry. The secret is set via `SECRET_KEY` environment variable (never hardcoded). All non-public endpoints require `Authorization: Bearer <token>`.

### Role-Based Access Control

```
Manager  → full CRUD + publish/archive SOPs + view BI + admin endpoints
Engineer → create/edit SOPs + run AI generation + upload videos
Operator → read-only access to published SOPs
```

RBAC is enforced via `Depends(require_role(...))` FastAPI dependencies at the route level.

### BI SQL Sandbox (3-Layer Defence-in-Depth)

See [Generative BI section](#generative-bi--text-to-sql-sandbox) for details. The three layers are independent: bypassing the regex check (Layer 1/2) does not allow mutations because every query executes inside a `SET TRANSACTION READ ONLY` database transaction (Layer 3).

### Input Validation

All incoming data is validated by Pydantic v2 models before reaching service or ORM layers. Sequence codes are parsed by a strict regex before any TMU calculation. File uploads are validated for MIME type and checked for maximum size before being passed to Celery.

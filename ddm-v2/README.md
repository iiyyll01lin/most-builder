# DDM v2 — Digital Decision Manufacturing

> **An Integrated Cyber-Physical Intelligence Platform for Smart Factories**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Celery](https://img.shields.io/badge/Celery-5.4-37814A?logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![MQTT](https://img.shields.io/badge/Mosquitto-MQTT-660066?logo=eclipsemosquitto&logoColor=white)](https://mosquitto.org/)
[![MediaPipe](https://img.shields.io/badge/MediaPipe-Vision-FF6F00?logo=google&logoColor=white)](https://mediapipe.dev/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-Ready-326CE5?logo=kubernetes&logoColor=white)](k8s/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## What is DDM v2?

DDM v2 is a **production-grade, cloud-native manufacturing intelligence platform** that fuses Industrial Engineering domain expertise with modern AI, real-time IoT data pipelines, and Generative BI — all in a single `docker compose up`.

At its core is a structured Work Measurement engine (MOST/TMU) that generates rigorously validated Standard Operating Procedures, augmented by a **GPT-4–powered SOP Copilot** that injects station-level constraints — glove rules, CTQ flags, ESD precautions, required operator certifications — directly into every AI-generated action. A multi-phase approval workflow (Draft → Under Review → Published) with a full audit trail ensures complete traceability. An interactive **3D Digital Twin** (React Three Fiber) renders every station in real time as IoT MQTT events arrive, giving supervisors an instant visual pulse of the live production line.

The AI capabilities extend beyond SOP authorship. A **Celery-distributed Vision Engine** processes uploaded workstation videos, aligns detected operator motions to SOP actions with sub-second video timestamps, and exposes those anchors through a full-featured Video SOP Workspace. A real-time IoT telemetry bridge (Mosquitto MQTT → WebSocket) fans out `fasten_ok / scan_ok / error` events to every connected 3D Twin client in under 50 ms. The platform also delivers a complete **Generative BI pipeline**: users type natural-language manufacturing questions into the "Factory Manager AI" dashboard; the backend translates them into secure, read-only PostgreSQL queries through a three-layer SQL sandbox and returns structured JSON payloads that the frontend automatically renders as bar charts, line charts, pie charts, or data grids using Recharts — zero frontend code per new question.

---

## ✨ Key Features

| | Feature | Description |
|---|---|---|
| 🧠 | **AI & Generative BI** | GPT-4 SOP Copilot, AI SOP Review, Text-to-SQL BI dashboard with 3-layer SQL sandbox |
| 👁️ | **Computer Vision Pipeline** | MediaPipe + OpenCV motion-density analysis, MOST TMU extraction from video |
| 🏭 | **Cyber-Physical Digital Twin** | React Three Fiber 3D viz, live MQTT telemetry, 1P2M (1 Operator / 2 Machines) layout |
| ⚙️ | **Domain Rule Engine** | MOST TMU calculations, ESD / glove constraints, CTQ flags, skill gates, precaution auto-binding |
| 📊 | **Line-Balance Simulation** | Multi-station takt-time optimization, bottleneck detection, 30-day history |
| 🔐 | **Enterprise Security** | JWT RBAC (Manager / Engineer / Operator), audit trail, read-only DB sandbox |
| ⚡ | **Distributed Task Queue** | Celery + Redis for long-running video analysis, async result polling |
| 📡 | **IoT Integration** | Mosquitto MQTT broker, real-time WebSocket broadcast, factory event simulation |
| ☸️ | **Kubernetes Ready** | Full `k8s/` manifests with rolling updates, health probes, and Nginx Ingress |

---

## 🚀 One-Command Demo

> **Prerequisites:** Docker, Docker Compose, Python 3.10+, `paho-mqtt` (`pip install paho-mqtt`)

```bash
cd ddm-v2
make demo
```

**What happens in the next 60 seconds:**

1. 🧹 **Tear-down** — any existing containers and volumes are removed cleanly
2. 🔨 **Build & Start** — the full 6-container stack builds and boots
3. ⏳ **Health check** — the Makefile polls the API until it responds (no manual waiting)
4. 🌱 **Seed** — "Project Alpha: Smart Speaker Assembly" data loads:
   - 5-station assembly line with a **1P2M (1 Operator / 2 Machine)** layout
   - 2 SOP versions (V1.0 Published + V2.0 Under Review) with 23 actions
   - 1 historical video upload pre-linked to vision timestamps
   - **101 simulation results** spanning 30 days of line-efficiency history
5. 📡 **Orchestrate** — the IoT Demo Orchestrator begins publishing scripted MQTT events

**Open your browser to `http://localhost:8000` and watch:**

- The **3D Digital Twin** flash green as station events arrive in real time
- The **1P2M moment**: stations ST-2A and ST-2B light up 300 ms apart, proving one operator drives two machines in parallel
- The **Factory Manager AI** chat dashboard — ask it *"Show total TMU by station"* and a bar chart appears instantly

---

## 🏗️ Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                        React 18 Frontend                        │
│  Zustand • React Query • React Three Fiber • Recharts • Tailwind│
└───────────────────────────┬─────────────────────────────────────┘
                            │  REST + WebSocket
┌───────────────────────────▼─────────────────────────────────────┐
│                    FastAPI Backend (Uvicorn)                     │
│  JWT RBAC • Pydantic v2 • SQLAlchemy async • Alembic migrations │
└──────┬────────────┬───────────────┬──────────────┬──────────────┘
       │            │               │              │
  PostgreSQL     Redis          Mosquitto       Celery
  (Async ORM)  (Broker +       (MQTT IoT       Worker
               Result)          Bridge)      (Vision AI)
```

> For the complete deep-dive — data flow, SQL sandbox layers, Vision-to-MOST algorithm, and Kubernetes topology — see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 🖥️ Stack

| Layer | Technology |
|---|---|
| **API** | FastAPI 0.135, Uvicorn, Pydantic v2 |
| **Database** | PostgreSQL 15 (async via asyncpg + SQLAlchemy 2.0), Alembic |
| **Task Queue** | Celery 5.4 + Redis 7 |
| **IoT Broker** | Eclipse Mosquitto 2 (MQTT 5) |
| **AI / LLM** | OpenAI GPT-4o-mini (function-calling mode); deterministic mock for offline dev |
| **Vision** | MediaPipe, OpenCV-headless, custom Motion-Density-to-TMU sliding window |
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS, Zustand, TanStack Query |
| **3D Twin** | React Three Fiber, Three.js, @react-three/drei |
| **BI Charts** | Recharts (BarChart, LineChart, PieChart, DataGrid) |
| **Containers** | Docker, Docker Compose; multi-stage Dockerfiles |
| **Orchestration** | Kubernetes (manifests in `k8s/`) |

---

## ⚡ Quick Start (Development)

```bash
# 1. Clone and enter the project
git clone https://github.com/iiyyll01lin/most-builder.git
cd most-builder/ddm-v2

# 2. Backend (Python 3.11+)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. Frontend
cd frontend && npm install && npm run dev
# → http://localhost:5173

# 4. Run the full stack with Docker
make up

# 5. Run tests
make test
```

---

## 🔑 Demo Accounts

| Role | Username | Password | Capabilities |
|---|---|---|---|
| Manager | `admin` | `admin123` | Full system access, publish SOPs, view BI |
| Engineer | `Avery` | `avery` | Create/edit SOPs, run AI generation, upload videos |
| Operator | `operator1` | `op123` | View published SOPs, read-only |

---

## 🧪 Testing

```bash
make test          # unit tests only (fast, no Docker required)
make test-all      # unit + functional + e2e + regression

# Or directly:
pytest tests/unit -v --tb=short
pytest tests/ -v -m "unit or functional"
```

**Test coverage:** 124 unit tests across AI service, BI SQL sandbox (28 security cases), simulation, vision, MOST engine, and level system.

---

## 📁 Project Layout

```text
ddm-v2/
├── Makefile                       # make demo / test / build / clean
├── docker-compose.yml             # Full 6-container stack
├── k8s/                           # Kubernetes deployment manifests
├── alembic/                       # Database migration scripts
├── frontend/                      # React 18 + Vite SPA
│   └── src/
│       ├── components/bi/         # DynamicChartRenderer (Recharts factory)
│       ├── components/            # DigitalTwinView, SimulationPanel, VideoPlayer…
│       └── pages/                 # FactoryManagerDashboard, ProjectDashboard…
├── scripts/
│   ├── demo_orchestrator.py       # Phase 10: scripted IoT narrative loop
│   └── simulate_iot_factory.py    # Random factory event simulator
├── src/ddm_v2/
│   ├── api/routes/                # FastAPI routers (ai, bi, sop, video, telemetry…)
│   ├── db/                        # database.py, schema_inspector.py
│   ├── models/domain.py           # SQLAlchemy ORM models (authoritative schema)
│   ├── repositories/postgres_store.py
│   ├── services/                  # ai, bi, vision, simulation, telemetry…
│   ├── seed_runner.py             # python -m ddm_v2.seed_runner
│   └── seeds.py                   # DEFAULT_STATE + seed_ultimate_demo()
└── tests/
    ├── unit/                      # 124 tests including BI sandbox security suite
    ├── functional/
    ├── e2e/
    └── regression/
```

---

## 🤝 Contributing

1. Fork the repository and create a feature branch
2. Run `make test` to verify your changes pass all unit tests
3. Open a pull request — the CI pipeline will run the full test matrix

---

## 📖 Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — Deep architectural dive
- [QUICKSTART.md](QUICKSTART.md) — Fast-path setup guide (Traditional Chinese)
- [docs/phase1-functional-spec.en.md](docs/phase1-functional-spec.en.md) — Full functional specification
- [docs/api-design-ux-enablement.md](docs/api-design-ux-enablement.md) — API design and UX enablement

---

## 📄 License

MIT © 2026 DDM v2 Contributors
- The persistence layer is intentionally file-based in this release candidate to keep deployment simple while the domain model stabilizes.
- The root path now serves the legacy-compatible validation UI so workflow checks can be performed against the rebuilt backend.

## Runtime Configuration

These environment variables are supported for deployment hardening:

- `DDM_SECRET_KEY`: JWT signing secret.
- `DDM_DB_PATH`: runtime database file path.
- `DDM_DATA_DIR`: base data directory when `DDM_DB_PATH` is not set.
- `DDM_CORS_ALLOW_ORIGINS`: comma-separated allowed origins.
- `DDM_CORS_ALLOW_METHODS`: comma-separated allowed HTTP methods.
- `DDM_CORS_ALLOW_HEADERS`: comma-separated allowed headers.
- `DDM_CORS_ALLOW_CREDENTIALS`: `true` or `false`.

## Docker Deploy

This repo now includes a single-container deployment setup for server validation.

Build and start it with Docker Compose:

```bash
cd ddm-v2
cp .env.example .env
docker compose up -d --build
```

Open the app at `http://127.0.0.1:8000` locally, or replace the host with your server IP/domain.

Useful commands:

```bash
docker compose ps
docker compose logs -f
docker compose down
```

Notes:

- Runtime data is stored in the named volume `ddm-v2-data` and mapped to `/app/data` inside the container.
- The image runs the source tree directly with `uvicorn ... --app-dir src` so the static UI files and local path-based settings keep working.
- For server deployment, update `DDM_SECRET_KEY` and `DDM_CORS_ALLOW_ORIGINS` in `.env` before exposing the service publicly.
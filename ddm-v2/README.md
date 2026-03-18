# DDM v2

Refactored release-candidate codebase for the legacy DDM Phase 1 workflow. The application keeps the original core capabilities, but restructures them into a modular FastAPI backend with a lightweight static control console and a full automated test suite.

## Scope

DDM v2 covers these functional areas:

- authentication and role-based access
- master-data management for syntax, objects, tools, locations, employees, and project metadata
- MOST calculation and validation workflows
- SOP versioning and action editing
- level-system synchronization, editing, and graph generation
- line-balance simulation and history
- audit logging and SQLite-backed persistence

## Prerequisites

- Python 3.10+

## Quick Start

Create a local virtual environment and install the app with development dependencies:

```bash
cd ddm-v2
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
```

Run the application:

```bash
cd ddm-v2
. .venv/bin/activate
uvicorn ddm_v2.main:app --reload --app-dir src
```

Build the validation frontend bundle before opening the root UI:

```bash
cd ddm-v2/frontend
npm install
npm run build
```

Open the full validation UI at `http://127.0.0.1:8000`.

If you only want the lightweight API smoke-test console, open `http://127.0.0.1:8000/control-console`.

The validation UI is now served through a buildable React/Vite frontend in `frontend/`, which compiles into `src/ddm_v2/static/frontend-build/`. The original extracted UI logic remains in `src/ddm_v2/static/legacy_ui/app.jsx`, but it is now bundled instead of executed through Babel/UMD/CDN scripts.

## Demo Accounts

- Manager: `admin` / `admin123`
- Engineer: `engineer1` / `eng123`
- Operator: `operator1` / `op123`

## Running Tests

Run the full suite:

```bash
cd ddm-v2
. .venv/bin/activate
PYTHONPATH=src pytest -q
```

Run by layer:

```bash
PYTHONPATH=src pytest -q -m unit
PYTHONPATH=src pytest -q -m functional
PYTHONPATH=src pytest -q -m e2e
PYTHONPATH=src pytest -q -m regression
```

## Project Layout

```text
ddm-v2/
├── data/                  # runtime SQLite database output
├── docs/                  # English and Chinese specifications
├── frontend/              # Vite/Tailwind frontend build project
├── src/ddm_v2/
│   ├── api/routes/        # HTTP endpoints
│   ├── repositories/      # SQLite persistence abstraction
│   ├── services/          # domain logic
│   ├── static/            # built frontend assets, legacy UI source, and control console
│   ├── main.py            # FastAPI app factory
│   ├── schemas.py         # Pydantic schemas and enums
│   └── seeds.py           # default seed data
└── tests/
    ├── unit/
    ├── functional/
    ├── e2e/
    └── regression/
```

## Notes

- The runtime database is stored at `ddm-v2/data/runtime-db.sqlite3` when the app runs normally.
- Tests inject a temporary database path through the app factory so each run is isolated.
- Existing JSON runtime payloads are migrated into SQLite on first load and preserved as `*.legacy-json.json` backups.
- The root path now serves the legacy-compatible validation UI through built static assets so workflow checks can be performed without Babel/CDN runtime dependencies.

## Runtime Configuration

These environment variables are supported for deployment hardening:

- `DDM_SECRET_KEY`: JWT signing secret.
- `DDM_DB_PATH`: runtime database file path.
- `DDM_DATA_DIR`: base data directory when `DDM_DB_PATH` is not set.
- `DDM_CORS_ALLOW_ORIGINS`: comma-separated allowed origins.
- `DDM_CORS_ALLOW_METHODS`: comma-separated allowed HTTP methods.
- `DDM_CORS_ALLOW_HEADERS`: comma-separated allowed headers.
- `DDM_CORS_ALLOW_CREDENTIALS`: `true` or `false`.
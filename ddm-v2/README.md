# DDM v2

Refactored release-candidate codebase for the legacy DDM Phase 1 workflow. The application keeps the original core capabilities, but restructures them into a modular FastAPI backend with a lightweight static control console and a full automated test suite.

Additional onboarding and RC validation docs:

- `QUICKSTART.md`
- `docs/release-candidate-test-coverage.zh-TW.md`

## Scope

DDM v2 covers these functional areas:

- authentication and role-based access
- master-data management for syntax, objects, tools, locations, employees, and project metadata
- MOST calculation and validation workflows
- SOP versioning and action editing
- level-system synchronization, editing, and graph generation
- line-balance simulation and history
- audit logging and JSON-backed persistence

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

Open the full validation UI at `http://127.0.0.1:8000`.

If you only want the lightweight API smoke-test console, open `http://127.0.0.1:8000/control-console`.

The validation UI is now split into a shell page plus external legacy assets under `src/ddm_v2/static/legacy_ui/`, with the root path serving `validation_shell.html` instead of a single embedded HTML file.

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
├── data/                  # runtime JSON persistence output
├── docs/                  # English and Chinese specifications
├── src/ddm_v2/
│   ├── api/routes/        # HTTP endpoints
│   ├── repositories/      # JSON persistence abstraction
│   ├── services/          # domain logic
│   ├── static/            # validation shell, legacy UI assets, and control console
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

- The runtime database is stored at `ddm-v2/data/runtime-db.json` when the app runs normally.
- Tests inject a temporary database path through the app factory so each run is isolated.
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
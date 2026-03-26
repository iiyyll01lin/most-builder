# DDM v2 — Developer Guide

This guide assumes you have **Docker and Docker Compose** installed.  
No Python, Node.js, or any other runtime needs to be installed on your machine.

---

## Table of Contents

1. [Architecture overview](#architecture-overview)
2. [Production stack](#production-stack)
3. [Dockerized CLI Tools & Tasks](#dockerized-cli-tools--tasks)
   - [First-time setup](#first-time-setup)
   - [Running Python tests](#running-python-tests)
   - [Static analysis (lint)](#static-analysis-lint)
   - [Building the React frontend](#building-the-react-frontend)
   - [Frontend Vite dev server](#frontend-vite-dev-server)
   - [Playwright E2E browser tests](#playwright-e2e-browser-tests)
   - [Database backup](#database-backup)
4. [Tooling reference card](#tooling-reference-card)
5. [Troubleshooting](#troubleshooting)

---

## Architecture overview

```text
docker-compose.yml          Production stack (FastAPI backend + built static assets)
docker-compose.test.yml     Integrated E2E stack (backend + Nginx/React frontend)
docker-compose.tools.yml    Developer tooling (tests, lint, build, backup, dev-server)
Dockerfile                  Production image (installs app, serves via uvicorn)
Dockerfile.backend          Backend-only image used by the E2E stack
Dockerfile.dev              Developer image — same as backend but with [dev] extras
                            (pytest, httpx, ruff, mypy)
frontend/Dockerfile.frontend  Multi-stage Node→Nginx image for the React frontend
```

---

## Production stack

Start / stop the single-container production server:

```bash
cd ddm-v2
cp .env.example .env          # first time only — edit DDM_SECRET_KEY
docker compose up -d --build  # build and start
docker compose logs -f        # tail logs
docker compose down           # stop
```

Health check:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

---

## Dockerized CLI Tools & Tasks

All developer tooling lives in `docker-compose.tools.yml`.  
Services are gated behind Compose **profiles** (`tools` / `dev`) so they never
start automatically with a generic `docker compose up`.

### First-time setup

Build the Python developer image (shared by `pytest` and `lint`):

```bash
docker compose -f docker-compose.tools.yml build pytest
```

> This is the only step that requires network access (downloads pip packages or
> uses the offline wheels cache in `docker-wheels/`). Subsequent runs reuse the
> cached image unless `pyproject.toml` or `docker-wheels/` changes.

---

### Running Python tests

The `pytest` service mounts the host `tests/` tree read-write and runs all
three non-browser test layers: **unit**, **functional**, and **regression**.

```bash
# Run the full Python test suite
docker compose -f docker-compose.tools.yml run --rm pytest

# Run only a single layer
docker compose -f docker-compose.tools.yml run --rm pytest tests/unit
docker compose -f docker-compose.tools.yml run --rm pytest tests/functional
docker compose -f docker-compose.tools.yml run --rm pytest tests/regression

# Run a specific test by keyword
docker compose -f docker-compose.tools.yml run --rm pytest -k test_auth

# Run with extra verbosity and stop on first failure
docker compose -f docker-compose.tools.yml run --rm pytest tests/unit -v -x
```

**What it does internally:**
- Uses `Dockerfile.dev` image (`ddm-v2-dev:latest`)
- `PYTHONPATH=src` — resolves `ddm_v2.*` imports from `src/`
- `pyproject.toml` `[tool.pytest.ini_options]` configures markers and test paths
- Each test run gets an isolated `tmp_path` database — no shared state

---

### Static analysis (lint)

Runs **ruff** (style, import order) followed by **mypy** (type checking).  
Exits non-zero on any finding, making it safe to use as a pre-commit gate.

```bash
docker compose -f docker-compose.tools.yml run --rm lint
```

To run only one tool:

```bash
# ruff only
docker compose -f docker-compose.tools.yml run --rm lint sh -c "ruff check src/"

# mypy only
docker compose -f docker-compose.tools.yml run --rm lint sh -c "mypy src/"
```

---

### Building the React frontend

The `frontend-build` service installs Node dependencies, runs `vite build`, and
copies the compiled assets into `src/ddm_v2/static/frontend-build/` so the
FastAPI backend can serve them at `/static/frontend-build/`.

```bash
docker compose -f docker-compose.tools.yml run --rm frontend-build
```

**What it does internally:**
1. `npm ci` — install dependencies (stored in Docker volume `ddm-v2-tools_frontend_nm`, not on the host)
2. `npm run build` — Vite produces `frontend/dist/`
3. `rm -rf /output/* && cp -r dist/. /output/` — copies artifacts to the bind-mounted output directory

> The first run takes ~60 s to download `npm ci` packages. Subsequent runs reuse
> the `frontend_nm` volume cache and take only a few seconds.

---

### Frontend Vite dev server

The `frontend-dev` service starts the Vite hot-reload server for active frontend
development. It uses `network_mode: host` so Vite's built-in proxy can forward
`/api/*` requests to the backend running on `localhost:8000`.

**Step 1** — start the production backend:
```bash
docker compose up -d
```

**Step 2** — start the dev server:
```bash
docker compose -f docker-compose.tools.yml --profile dev up frontend-dev
```

Open the frontend at **http://localhost:5173**.  
API calls are proxied to `http://localhost:8000` automatically (configured in
`frontend/vite.config.ts`).

To stop the dev server:
```bash
docker compose -f docker-compose.tools.yml --profile dev down
```

> **Linux only:** `network_mode: host` works natively on Linux.  
> On macOS or Windows with Docker Desktop, update `vite.config.ts` to use
> `http://host.docker.internal:8000` as the proxy target and remove
> `network_mode: host` from the service definition.

---

### Playwright E2E browser tests

The `playwright` service runs the full Playwright browser suite against the
containerized E2E stack. It uses the official
`mcr.microsoft.com/playwright:v1.52.0-jammy` image (ships Chromium).

**Step 1** — start the E2E stack (leave it running in the background):

```bash
docker compose -f docker-compose.test.yml up -d --build
```

Wait until both services are healthy:

```bash
docker compose -f docker-compose.test.yml ps
# backend: healthy
# frontend: healthy
```

**Step 2** — run the Playwright tests:

```bash
docker compose -f docker-compose.tools.yml run --rm playwright
```

**Step 3** — view the HTML report (on your host machine):

```bash
# If you have Node installed locally:
npx playwright show-report e2e/playwright-report

# Or open the file directly:
open e2e/playwright-report/index.html
```

**Step 4** — tear down the E2E stack when done:

```bash
docker compose -f docker-compose.test.yml down --volumes
```

**How it works:**
- `E2E_SKIP_DOCKER=true` — tells `global-setup.ts` to skip launching Docker
  (the stack is already running)
- `E2E_BASE_URL=http://frontend` — points Playwright at the frontend service
  inside the shared `ddm-v2-e2e_app_net` bridge network
- The `playwright` container joins that network so `http://frontend` and
  `http://backend:8000` are reachable by service-name hostname
- Test artifacts and the HTML report are written to `e2e/playwright-report/`
  on the host via bind mount

---

### Database backup

The `db-backup` service attaches to the production data volume (read-only) and
writes a timestamped JSON snapshot to `backups/` on the host. The production
backend does **not** need to be stopped — the JsonStore uses atomic file
replacement so live snapshots are safe.

```bash
# Take a backup
docker compose -f docker-compose.tools.yml run --rm db-backup

# List existing backups
ls -lh backups/
# runtime-db-20260326T142500.json
# runtime-db-20260327T090000.json
```

To restore a backup, copy it back into the volume:

```bash
docker compose cp backups/runtime-db-20260326T142500.json ddm-v2:/app/data/runtime-db.json
docker compose restart ddm-v2
```

> Backup files are excluded from git via `.gitignore` (`backups/runtime-db-*.json`).
> Only the `backups/.gitkeep` placeholder is tracked.

---

## Tooling reference card

| Task | Command |
|------|---------|
| Build dev image | `docker compose -f docker-compose.tools.yml build pytest` |
| Run all Python tests | `docker compose -f docker-compose.tools.yml run --rm pytest` |
| Run unit tests only | `docker compose -f docker-compose.tools.yml run --rm pytest tests/unit` |
| Run a specific test | `docker compose -f docker-compose.tools.yml run --rm pytest -k test_auth` |
| Lint (ruff + mypy) | `docker compose -f docker-compose.tools.yml run --rm lint` |
| Build React frontend | `docker compose -f docker-compose.tools.yml run --rm frontend-build` |
| Start Vite dev server | `docker compose -f docker-compose.tools.yml --profile dev up frontend-dev` |
| Run Playwright E2E | `docker compose -f docker-compose.test.yml up -d --build` then `docker compose -f docker-compose.tools.yml run --rm playwright` |
| Back up production DB | `docker compose -f docker-compose.tools.yml run --rm db-backup` |

---

## Troubleshooting

**`prod_data` volume not found when running `db-backup`**  
The production stack must have been run at least once to create the volume.
```bash
docker compose up -d  # creates the ddm-v2_ddm-v2-data volume
docker compose down   # stop backend if not needed
docker compose -f docker-compose.tools.yml run --rm db-backup
```

**`ddm-v2-e2e_app_net` network not found when running `playwright`**  
The E2E test stack must be running first.
```bash
docker compose -f docker-compose.test.yml up -d --build
```

**`ddm-v2-dev:latest` image not found when running `lint`**  
The image must be built first (it's defined on the `pytest` service).
```bash
docker compose -f docker-compose.tools.yml build pytest
```

**Frontend dev server proxy returns 502**  
The production backend is not running. Start it first:
```bash
docker compose up -d
```

**node_modules cache stale after `package.json` change**  
Remove the named volume to force a clean `npm ci`:
```bash
docker volume rm ddm-v2-tools_frontend_nm
docker compose -f docker-compose.tools.yml run --rm frontend-build
```

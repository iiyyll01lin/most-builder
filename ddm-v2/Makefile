# DDM v2 — Developer Makefile
#
# Targets:
#   make demo    — Full end-to-end showcase: tear down, rebuild, seed, orchestrate
#   make build   — Build Docker images without starting containers
#   make up      — Start the full stack (no rebuild)
#   make down    — Stop and remove containers (keeps volumes)
#   make clean   — Stop containers AND destroy all volumes (destructive)
#   make test    — Run the unit test suite (uses the venv Python)
#   make logs    — Tail live container logs
#   make shell   — Open a shell inside the DDM app container
#   make help    — Print this help

.PHONY: demo build up down clean test logs shell seed help

# ── Configuration ─────────────────────────────────────────────────────────────

COMPOSE       := docker compose
APP_CONTAINER := ddm-v2
API_URL       := http://localhost:${DDM_PORT:-8000}/api/v1/auth/login
VENV_PYTHON   := python3
SCRIPTS_DIR   := scripts

# Wait-for-API: poll every 3 s for up to 90 s using only stdlib (no curl/wget dep)
define WAIT_FOR_API
	@$(VENV_PYTHON) - <<'_PY_EOF'
import sys, time, urllib.request, urllib.error
url = "http://localhost:8000/api/v1/auth/login"
print("⏳  Waiting for API to become healthy  (up to 90 s) …")
for attempt in range(30):
    try:
        # POST with empty body — 422 means the server is up and validating
        req = urllib.request.Request(url, data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3)
        print("✅  API is healthy.")
        sys.exit(0)
    except urllib.error.HTTPError as e:
        if e.code in (422, 401, 400):   # server replied → it is up
            print("✅  API is healthy (HTTP %d)." % e.code)
            sys.exit(0)
    except Exception:
        pass
    time.sleep(3)
print("❌  API did not become healthy within 90 s.  Check logs: make logs")
sys.exit(1)
_PY_EOF
endef

# ── demo ─────────────────────────────────────────────────────────────────────

demo: ## Tear down, rebuild, seed ultimate demo data, and start IoT orchestrator
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════════════╗"
	@echo "║  DDM v2  ·  Phase 10: Ultimate Showcase                         ║"
	@echo "║  Project Alpha: Smart Speaker Assembly                          ║"
	@echo "╚══════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Step 1/5  Tearing down existing containers and volumes …"
	@$(COMPOSE) down -v --remove-orphans 2>/dev/null || true
	@echo ""
	@echo "Step 2/5  Building and starting the full stack …"
	$(COMPOSE) up -d --build
	@echo ""
	@echo "Step 3/5  Waiting for PostgreSQL and API to be ready …"
	$(WAIT_FOR_API)
	@echo ""
	@echo "Step 4/5  Seeding ultimate demo data (Project Alpha) …"
	$(COMPOSE) exec -T $(APP_CONTAINER) python -m ddm_v2.seed_runner
	@echo ""
	@echo "Step 5/5  Starting IoT Demo Orchestrator …"
	@echo "          Open http://localhost:8000 in your browser to see the"
	@echo "          3D Digital Twin respond to live telemetry events."
	@echo ""
	$(VENV_PYTHON) $(SCRIPTS_DIR)/demo_orchestrator.py \
		--host localhost \
		--port $${MQTT_PORT:-1883} \
		--cycle-time $${DEMO_CYCLE_TIME:-14.0}

# ── build ─────────────────────────────────────────────────────────────────────

build: ## Build all Docker images (no containers started)
	$(COMPOSE) build

# ── up / down ─────────────────────────────────────────────────────────────────

up: ## Start the full stack without rebuilding
	$(COMPOSE) up -d

down: ## Stop containers (volumes preserved)
	$(COMPOSE) down

# ── clean ─────────────────────────────────────────────────────────────────────

clean: ## DESTRUCTIVE: remove containers + ALL volumes (wipes the database)
	@echo "⚠️   This will delete all database volumes.  Type 'yes' to confirm: "
	@read CONFIRM && [ "$$CONFIRM" = "yes" ] || (echo "Aborted."; exit 1)
	$(COMPOSE) down -v --remove-orphans

# ── test ─────────────────────────────────────────────────────────────────────

test: ## Run the unit test suite (requires venv: pip install -e ".[dev]")
	$(VENV_PYTHON) -m pytest tests/unit -v --tb=short -q

test-all: ## Run the full test suite (unit + functional)
	$(VENV_PYTHON) -m pytest tests/ -v --tb=short

# ── seed ─────────────────────────────────────────────────────────────────────

seed: ## Re-run the ultimate demo seed against the running stack (idempotent)
	$(COMPOSE) exec -T $(APP_CONTAINER) python -m ddm_v2.seed_runner

# ── logs / shell ─────────────────────────────────────────────────────────────

logs: ## Tail logs from the DDM app container
	$(COMPOSE) logs -f $(APP_CONTAINER)

logs-all: ## Tail logs from all containers
	$(COMPOSE) logs -f

shell: ## Open a bash shell inside the DDM app container
	$(COMPOSE) exec $(APP_CONTAINER) bash

# ── help ─────────────────────────────────────────────────────────────────────

help: ## Print available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo ""

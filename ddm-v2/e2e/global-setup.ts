/**
 * Playwright globalSetup — boots the docker-compose.test.yml stack and
 * seeds the test database volume, then waits until both services are healthy.
 *
 * Runs once before any test file and is paired with globalTeardown.
 */
import { execSync, spawnSync } from 'child_process'
import * as fs from 'fs'
import * as path from 'path'

// Root of ddm-v2/  (global-setup.ts lives in ddm-v2/e2e/)
const COMPOSE_DIR = path.resolve(__dirname, '..')
const COMPOSE_FILE = path.join(COMPOSE_DIR, 'docker-compose.test.yml')
const SOURCE_DB = path.join(COMPOSE_DIR, 'data', 'runtime-db.json')
const SEED_CONTAINER = 'ddm-v2-backend-test'
const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000'
const BACKEND_HEALTH = 'http://localhost:8000/api/v1/health'

function run(cmd: string, opts: { cwd?: string } = {}) {
  console.log(`[setup] ${cmd}`)
  execSync(cmd, { cwd: opts.cwd ?? COMPOSE_DIR, stdio: 'inherit' })
}

async function waitForUrl(url: string, timeoutMs = 60_000): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url)
      if (res.ok) return
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 1_500))
  }
  throw new Error(`[setup] Timed out waiting for ${url} after ${timeoutMs}ms`)
}

export default async function globalSetup() {
  // Skip if the stack is already running (e.g. in interactive dev mode)
  if (process.env.E2E_SKIP_DOCKER === 'true') {
    console.log('[setup] E2E_SKIP_DOCKER=true — skipping docker compose up')
    return
  }

  if (!fs.existsSync(COMPOSE_FILE)) {
    throw new Error(`[setup] Compose file not found: ${COMPOSE_FILE}`)
  }

  // Pull / build images, then start in detached mode
  run(`docker compose -f ${COMPOSE_FILE} up --build -d`)

  // Copy the seed DB into the named volume via the (already running) backend container.
  // We wait for the container to exist before copying.
  console.log('[setup] Seeding test database…')
  await new Promise((r) => setTimeout(r, 3_000))

  if (fs.existsSync(SOURCE_DB)) {
    const result = spawnSync('docker', [
      'cp',
      SOURCE_DB,
      `${SEED_CONTAINER}:/app/data/runtime-db.json`,
    ])
    if (result.status !== 0) {
      console.warn('[setup] DB seed copy failed — tests will use the container-bundled data')
    }
  }

  // Wait for backend health endpoint
  console.log('[setup] Waiting for backend to be healthy…')
  await waitForUrl(BACKEND_HEALTH, 90_000)

  // Wait for the frontend Nginx to be ready
  console.log('[setup] Waiting for frontend to be ready…')
  await waitForUrl(BASE_URL, 30_000)

  console.log('[setup] Stack is healthy — running E2E suite')
}

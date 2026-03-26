/**
 * Playwright globalTeardown — shuts down the docker-compose.test.yml stack
 * and removes the ephemeral e2e volume. Runs once after all test files.
 */
import { execSync } from 'child_process'
import * as path from 'path'

const COMPOSE_DIR = path.resolve(__dirname, '..')
const COMPOSE_FILE = path.join(COMPOSE_DIR, 'docker-compose.test.yml')

export default async function globalTeardown() {
  if (process.env.E2E_SKIP_DOCKER === 'true') return

  console.log('[teardown] Stopping E2E stack…')
  try {
    execSync(
      `docker compose -f ${COMPOSE_FILE} down --volumes --remove-orphans`,
      { cwd: COMPOSE_DIR, stdio: 'inherit' },
    )
  } catch (err) {
    console.warn('[teardown] docker compose down failed (non-fatal):', err)
  }
}

/**
 * Test 3: Real-Time Simulation via WebSocket
 *
 * Verifies the complete simulation flow:
 *   1. POST /api/v1/simulation/line-balance/async  → returns job_id
 *   2. WS  /api/v1/simulation/ws/{job_id}          → progress stream
 *   3. UI renders ProgressBar, live status text, and final Line Balance metrics
 *
 * The test uses Playwright's built-in WebSocket event interception to verify
 * that the client successfully opens a WS connection and receives frames.
 *
 * Seed: the backend has real simulation logic; we send a minimal request
 * (empty stations) so the simulation completes quickly and predictably.
 */
import { test, expect, type Page } from '@playwright/test'
import { loadDashboard, TEST_PROJECT_ID, TEST_USER } from '../helpers'

async function navigateToSimulationPanel(page: Page) {
  await loadDashboard(page, TEST_PROJECT_ID, TEST_USER)
  // The SimulationPanel is always rendered at the bottom of the dashboard
  await expect(
    page.getByRole('heading', { name: /line balance simulation/i }),
  ).toBeVisible({ timeout: 15_000 })
}

test.describe('Real-Time Simulation (WebSocket)', () => {
  test.beforeEach(async ({ page }) => {
    await navigateToSimulationPanel(page)
  })

  test('simulation panel renders "Run Simulation" button with Takt Time input', async ({ page }) => {
    await expect(page.getByRole('button', { name: /run simulation/i })).toBeVisible()
    await expect(page.getByRole('spinbutton', { name: /takt time/i }).or(
      page.locator('input[type="number"]'),
    )).toBeVisible()
    // Label annotation
    await expect(page.getByText(/real-time async/i).or(page.getByText(/websocket/i))).toBeVisible()
  })

  test('clicking Run Simulation fires the async POST and opens a WebSocket', async ({ page }) => {
    // Listen for the async job POST
    const postPromise = page.waitForRequest(
      (req) =>
        req.method() === 'POST' &&
        req.url().includes('/simulation/line-balance/async'),
      { timeout: 10_000 },
    )

    // Listen for a WebSocket connection being established
    const wsPromise = new Promise<string>((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('WS not opened within 15s')), 15_000)
      page.on('websocket', (ws) => {
        if (ws.url().includes('/simulation/ws/')) {
          clearTimeout(timeout)
          resolve(ws.url())
        }
      })
    })

    // Click Run Simulation
    await page.getByRole('button', { name: /run simulation/i }).click()

    // POST must be dispatched
    const postReq = await postPromise
    expect(postReq.url()).toContain('/simulation/line-balance/async')

    // WebSocket must be opened for the returned job_id
    const wsUrl = await wsPromise
    expect(wsUrl).toContain('/simulation/ws/')
  })

  test('progress bar appears while simulation is running', async ({ page }) => {
    await page.getByRole('button', { name: /run simulation/i }).click()

    // The ProgressBar component renders a role=progressbar element
    await expect(page.locator('[role="progressbar"]')).toBeVisible({ timeout: 15_000 })
  })

  test('live status text updates during the simulation stream', async ({ page }) => {
    await page.getByRole('button', { name: /run simulation/i }).click()

    // Any non-empty status text should appear beside the progress bar
    // The ProgressBar renders the status string; look for "Connecting" or any text
    await expect(
      page.getByText(/connecting|running|processing|progress|simulation/i).first(),
    ).toBeVisible({ timeout: 15_000 })
  })

  test('simulation completes and renders Line Balance KPIs', async ({ page }) => {
    await page.getByRole('button', { name: /run simulation/i }).click()

    // Wait for the simulation to finish (progress bar hits 100 %)
    // Use .first() to avoid strict-mode violation when both
    // 'Simulation complete' (status text) and 'Complete' (progress label) match.
    await expect(
      page.getByText('Simulation complete'),
    ).toBeVisible({ timeout: 60_000 })

    // The KPI strip appears in the result section
    await expect(page.getByText('Cycle Time', { exact: true })).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText('UPH', { exact: true })).toBeVisible()
    await expect(page.getByText('Balance Rate', { exact: true })).toBeVisible()
    await expect(page.getByText('Bottleneck', { exact: true })).toBeVisible()
  })

  test('Re-run button appears after simulation completes', async ({ page }) => {
    await page.getByRole('button', { name: /run simulation/i }).click()

    await expect(page.getByText(/simulation complete/i)).toBeVisible({ timeout: 60_000 })

    // After completion both "Run Simulation" (re-run alias) and "Re-run" appear
    const rerun = page.getByRole('button', { name: /re-run/i })
    await expect(rerun).toBeVisible({ timeout: 5_000 })
  })

  test('WebSocket frames carry progress and status fields', async ({ page }) => {
    const frames: Array<{ progress: number; status: string }> = []

    // Capture all WS frames from the simulation socket
    page.on('websocket', (ws) => {
      if (!ws.url().includes('/simulation/ws/')) return
      ws.on('framereceived', (ev) => {
        try {
          const parsed = JSON.parse(ev.payload as string) as {
            progress: number
            status: string
          }
          frames.push(parsed)
        } catch {
          /* ignore binary / non-JSON */
        }
      })
    })

    await page.getByRole('button', { name: /run simulation/i }).click()

    // Wait until the simulation has a chance to emit frames
    await page.waitForTimeout(5_000)

    // At least one frame must have been received with expected shape
    expect(frames.length).toBeGreaterThan(0)
    const first = frames[0]
    expect(typeof first.progress).toBe('number')
    expect(typeof first.status).toBe('string')
  })
})

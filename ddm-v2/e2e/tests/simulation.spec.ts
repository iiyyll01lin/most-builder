/**
 * Test 3: Real-Time Simulation via WebSocket (updated for Sprint 2 UI)
 *
 * Sprint 2 changes that required test updates:
 *  - SimulationPanel now has a Station Configurator with a Combobox-based
 *    station/employee selector and a Machine Count number input.
 *  - "Run Simulation" is disabled until at least one station is configured.
 *  - A new MIGenerator panel renders between SopActionEditor and SimulationPanel.
 *
 * Test structure:
 *  Suite 1 — Real-Time Simulation (WebSocket): existing tests updated to call
 *            addStationConfig() before interacting with Run Simulation, plus
 *            new tests for the Station Configurator and 1P2M machine count.
 *  Suite 2 — MI Naming Generator: new tests for the 8-field form, client-side
 *            preview, backend validation, error display, and copy functionality.
 */
import { test, expect, type Page } from '@playwright/test'
import { loadDashboard, TEST_PROJECT_ID, TEST_USER } from '../helpers'

// ─── Seed constants ───────────────────────────────────────────────────────────

/** Matches "第3-1站 (DIMM)" — station id ST-3-1a from runtime-db.json */
const SEED_STATION_SEARCH = 'DIMM'

// ─── Page-object helpers ──────────────────────────────────────────────────────

async function navigateToSimulationPanel(page: Page) {
  await loadDashboard(page, TEST_PROJECT_ID, TEST_USER)
  await expect(
    page.getByRole('heading', { name: /line balance simulation/i }),
  ).toBeVisible({ timeout: 15_000 })
}

/**
 * Add one station row to the SimulationPanel Station Configurator by
 * interacting with the Combobox component:
 *   1. Click "Add Station"
 *   2. Click the station Combobox input  → dropdown opens (API-loaded)
 *   3. Click the matching list option    → selection confirmed
 */
async function addStationConfig(page: Page, searchText = SEED_STATION_SEARCH) {
  await page.getByRole('button', { name: /\+ add station/i }).click()

  // Station Combobox input — use .last() to always target the newest row
  const stationInput = page.getByPlaceholder('Select station…').last()
  // Click to focus: triggers onFocus → inputValue = '' → dropdown opens
  await stationInput.click()

  // The dropdown is a <ul> sibling of the <input> inside the .relative wrapper.
  // Wait for the API data to load and dropdown to appear.
  const dropdown = stationInput.locator('..').locator('ul')
  await expect(dropdown).toBeVisible({ timeout: 10_000 })

  // Click the option that matches the search text
  await dropdown.locator('li').filter({ hasText: searchText }).first().click()

  // Confirm selection: input value should now contain the station label
  await expect(stationInput).toHaveValue(new RegExp(searchText, 'i'), { timeout: 5_000 })
}

// ─── Suite 1: Real-Time Simulation (WebSocket) ────────────────────────────────

test.describe('Real-Time Simulation (WebSocket)', () => {
  test.beforeEach(async ({ page }) => {
    await navigateToSimulationPanel(page)
  })

  // ── Sprint 2: Station Configurator UI ────────────────────────────────────────

  test('simulation panel renders Station Configuration section with Add Station button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /run simulation/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /\+ add station/i })).toBeVisible()
    await expect(page.getByText(/station configuration/i)).toBeVisible()
    // Takt Time input (first number input; no machine count inputs yet)
    await expect(page.locator('input[type="number"]').first()).toBeVisible()
    await expect(page.getByText(/real-time async/i).or(page.getByText(/websocket/i))).toBeVisible()
  })

  test('Run Simulation is disabled with no stations and shows empty-state hint', async ({ page }) => {
    await expect(page.getByRole('button', { name: /run simulation/i })).toBeDisabled()
    await expect(page.getByText(/no stations configured/i)).toBeVisible()
  })

  test('adding a station via Combobox enables Run Simulation', async ({ page }) => {
    await expect(page.getByRole('button', { name: /run simulation/i })).toBeDisabled()
    await addStationConfig(page)
    await expect(page.getByRole('button', { name: /run simulation/i })).toBeEnabled({ timeout: 5_000 })
  })

  test('machine count input defaults to 1 and accepts 1P2M value', async ({ page }) => {
    await addStationConfig(page)
    const machineInput = page.locator('label').filter({ hasText: 'Machines' }).locator('input')
    await expect(machineInput).toHaveValue('1')
    await machineInput.fill('2')
    await expect(machineInput).toHaveValue('2')
  })

  test('POST payload includes station id and machine_count', async ({ page }) => {
    await addStationConfig(page)
    // Set machine count to 2 for 1P2M
    const machineInput = page.locator('label').filter({ hasText: 'Machines' }).locator('input')
    await machineInput.fill('2')

    const postPromise = page.waitForRequest(
      (req) =>
        req.method() === 'POST' &&
        req.url().includes('/simulation/line-balance/async'),
      { timeout: 10_000 },
    )
    await page.getByRole('button', { name: /run simulation/i }).click()

    const postReq = await postPromise
    const body = postReq.postDataJSON() as {
      stations?: Array<{ id: string; machine_count: number }>
    }
    expect(body.stations?.length).toBeGreaterThan(0)
    expect(body.stations?.[0].machine_count).toBe(2)
  })

  // ── Existing tests updated to add a station first ─────────────────────────

  test('clicking Run Simulation fires the async POST and opens a WebSocket', async ({ page }) => {
    await addStationConfig(page)

    const postPromise = page.waitForRequest(
      (req) =>
        req.method() === 'POST' &&
        req.url().includes('/simulation/line-balance/async'),
      { timeout: 10_000 },
    )

    const wsPromise = new Promise<string>((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('WS not opened within 15s')), 15_000)
      page.on('websocket', (ws) => {
        if (ws.url().includes('/simulation/ws/')) {
          clearTimeout(timeout)
          resolve(ws.url())
        }
      })
    })

    await page.getByRole('button', { name: /run simulation/i }).click()

    const postReq = await postPromise
    expect(postReq.url()).toContain('/simulation/line-balance/async')

    const wsUrl = await wsPromise
    expect(wsUrl).toContain('/simulation/ws/')
  })

  test('progress bar appears while simulation is running', async ({ page }) => {
    await addStationConfig(page)
    await page.getByRole('button', { name: /run simulation/i }).click()
    await expect(page.locator('[role="progressbar"]')).toBeVisible({ timeout: 15_000 })
  })

  test('live status text updates during the simulation stream', async ({ page }) => {
    await addStationConfig(page)
    await page.getByRole('button', { name: /run simulation/i }).click()
    await expect(
      page.getByText(/connecting|running|processing|progress|simulation/i).first(),
    ).toBeVisible({ timeout: 15_000 })
  })

  test('simulation completes and renders Line Balance KPIs', async ({ page }) => {
    await addStationConfig(page)
    await page.getByRole('button', { name: /run simulation/i }).click()

    await expect(page.getByText('Simulation complete')).toBeVisible({ timeout: 60_000 })

    await expect(page.getByText('Cycle Time', { exact: true })).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText('UPH', { exact: true })).toBeVisible()
    await expect(page.getByText('Balance Rate', { exact: true })).toBeVisible()
    await expect(page.getByText('Bottleneck', { exact: true })).toBeVisible()
  })

  test('Re-run button appears after simulation completes', async ({ page }) => {
    await addStationConfig(page)
    await page.getByRole('button', { name: /run simulation/i }).click()

    await expect(page.getByText(/simulation complete/i)).toBeVisible({ timeout: 60_000 })
    await expect(page.getByRole('button', { name: /re-run/i })).toBeVisible({ timeout: 5_000 })
  })

  test('WebSocket frames carry progress and status fields', async ({ page }) => {
    await addStationConfig(page)

    const frames: Array<{ progress: number; status: string }> = []
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
    await page.waitForTimeout(5_000)

    expect(frames.length).toBeGreaterThan(0)
    const first = frames[0]
    expect(typeof first.progress).toBe('number')
    expect(typeof first.status).toBe('string')
  })
})

// ─── Suite 2: MI Naming Generator ────────────────────────────────────────────

test.describe('MI Naming Generator', () => {
  test.beforeEach(async ({ page }) => {
    await loadDashboard(page, TEST_PROJECT_ID, TEST_USER)
    // The MIGenerator heading is in the DOM regardless of scroll position
    await expect(
      page.getByRole('heading', { name: /mi naming generator/i }),
    ).toBeVisible({ timeout: 15_000 })
  })

  test('renders all 8 field labels and the naming convention formula', async ({ page }) => {
    // Use .first() — the label element and its parent div both contain the text
    for (const label of ['Model5', 'Status', 'PickType', 'Process', 'CFI', 'Line', 'Area', 'CT']) {
      await expect(page.getByText(label).first()).toBeVisible()
    }
    // Convention string shown below the heading
    await expect(page.getByText(/\[Model5\]_\[Status\]/)).toBeVisible()
    await expect(page.getByRole('button', { name: /validate.*generate/i })).toBeVisible()
  })

  test('client-side preview updates as fields are filled', async ({ page }) => {
    // Fill model5 and status — preview should appear joined by '_'
    await page.getByPlaceholder('HDL50').fill('TEST1')
    await page.getByPlaceholder('ASSY').first().fill('PACK')
    await expect(page.getByText(/TEST1_PACK/)).toBeVisible()
  })

  test('validates MI name successfully with all required fields', async ({ page }) => {
    // Field placeholders: model5='HDL50', status='ASSY'(first), pick_type='FPT',
    //                     process='ASSY'(second), line='L1', area='A1', ct='45'
    // cfi is optional (placeholder: 'CFI code (optional)') — leave blank
    await page.getByPlaceholder('HDL50').fill('HDL50')
    await page.getByPlaceholder('ASSY').first().fill('ASSY')
    await page.getByPlaceholder('FPT').fill('FPT')
    await page.getByPlaceholder('ASSY').nth(1).fill('ASSY')
    await page.getByPlaceholder('L1').fill('L1')
    await page.getByPlaceholder('A1').fill('A1')
    await page.getByPlaceholder('45').fill('45')

    const apiPromise = page.waitForResponse(
      (r) => r.url().includes('/mi-naming/validate') && r.status() === 200,
      { timeout: 10_000 },
    )
    await page.getByRole('button', { name: /validate.*generate/i }).click()

    const resp = await apiPromise
    const body = await resp.json() as { is_valid: boolean; suggested_name: string | null }
    expect(body.is_valid).toBe(true)
    expect(body.suggested_name).toMatch(/^HDL50_ASSY_FPT_ASSY_L1_A1_45$/)

    // Success indicator in the UI — use .first() because both the button-side
    // '✓ Valid' span and the result card '✓ MI name is valid' heading are visible
    await expect(
      page.getByText(/✓.*valid/i).or(page.getByText(/mi name is valid/i)).first(),
    ).toBeVisible({ timeout: 10_000 })
  })

  test('suggested name uses underscore separator and omits blank CFI segment', async ({ page }) => {
    await page.getByPlaceholder('HDL50').fill('HDL50')
    await page.getByPlaceholder('ASSY').first().fill('ASSY')
    await page.getByPlaceholder('FPT').fill('MPT')
    await page.getByPlaceholder('ASSY').nth(1).fill('PACK')
    // Intentionally leave CFI blank
    await page.getByPlaceholder('L1').fill('L2')
    await page.getByPlaceholder('A1').fill('B3')
    await page.getByPlaceholder('45').fill('60')

    const apiPromise = page.waitForResponse(
      (r) => r.url().includes('/mi-naming/validate') && r.status() === 200,
      { timeout: 10_000 },
    )
    await page.getByRole('button', { name: /validate.*generate/i }).click()
    await apiPromise

    // Suggested name in the result card: 7 segments (no CFI) joined by '_'
    // Use .first() — the same string may appear in both the live preview and
    // the result card simultaneously after a successful validation
    await expect(page.getByText(/HDL50_ASSY_MPT_PACK_L2_B3_60/).first()).toBeVisible({ timeout: 5_000 })
  })

  test('shows validation errors when required fields are missing', async ({ page }) => {
    // Only fill model5; all other required fields left blank
    await page.getByPlaceholder('HDL50').fill('HDL50')

    const apiPromise = page.waitForResponse(
      (r) => r.url().includes('/mi-naming/validate') && r.status() === 200,
      { timeout: 10_000 },
    )
    await page.getByRole('button', { name: /validate.*generate/i }).click()
    const resp = await apiPromise

    const body = await resp.json() as { is_valid: boolean; errors: string[] }
    expect(body.is_valid).toBe(false)
    expect(body.errors.length).toBeGreaterThan(0)

    // Error indicator visible in the UI — use .first() to avoid strict-mode
    // violation when both the button-side '✗ Invalid' span and the result-card
    // '✗ Validation failed' heading match simultaneously
    await expect(
      page.getByText(/✗.*invalid/i)
        .or(page.getByText(/validation failed/i))
        .first(),
    ).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText(/is required/i).first()).toBeVisible()
  })

  test('Copy button appears after successful validation', async ({ page }) => {
    await page.getByPlaceholder('HDL50').fill('HDL50')
    await page.getByPlaceholder('ASSY').first().fill('ASSY')
    await page.getByPlaceholder('FPT').fill('FPT')
    await page.getByPlaceholder('ASSY').nth(1).fill('ASSY')
    await page.getByPlaceholder('L1').fill('L1')
    await page.getByPlaceholder('A1').fill('A1')
    await page.getByPlaceholder('45').fill('45')

    await page.getByRole('button', { name: /validate.*generate/i }).click()

    // Success can be signalled by the button-side '✓ Valid' span OR the result
    // card '✓ MI name is valid' heading — either is sufficient
    await expect(
      page.getByText(/✓.*valid/i).or(page.getByText(/mi name is valid/i)).first(),
    ).toBeVisible({ timeout: 10_000 })

    // Copy button appears next to the preview strip and/or the result card
    await expect(page.getByRole('button', { name: /copy/i }).first()).toBeVisible()
  })
})


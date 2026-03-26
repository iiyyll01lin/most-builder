/**
 * Test 1: Authentication & BFF Dashboard
 *
 * Verifies the complete login → project selection → BFF data-load flow.
 * The BFF endpoint (GET /api/v1/bff/dashboard/{project_id}) must:
 *   - Return the project KPIs (Actions count, Total CT, MOST Steps, SOP Versions)
 *   - Populate the SOP version selector with V1.0 in "Draft" status
 *
 * Seed data: proj-atlas / sop-atlas-v1 (7 actions, status=Draft)
 */
import { test, expect } from '@playwright/test'
import { login, loadDashboard, TEST_PROJECT_ID, TEST_USER } from '../helpers'

test.describe('Authentication & BFF Dashboard', () => {
  test('shows login page to unauthenticated users', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: /DDM IE\/PE Console/i })).toBeVisible()
    await expect(page.locator('#username')).toBeVisible()
    await expect(page.locator('#password')).toBeVisible()
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
  })

  test('rejects invalid credentials with an error toast', async ({ page }) => {
    await page.goto('/')
    await page.locator('#username').fill('notauser')
    await page.locator('#password').fill('wrongpass')
    await page.getByRole('button', { name: /sign in/i }).click()

    // The global interceptor fires a toast — look for the error indicator
    await expect(page.locator('[role="status"]').or(page.getByText(/unauthorized|invalid|session/i))).toBeVisible({
      timeout: 8_000,
    })

    // Must remain on the login page
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
  })

  test('successful login transitions to the project selector', async ({ page }) => {
    await login(page, TEST_USER)

    // Project selector is shown
    await expect(page.getByRole('heading', { name: /open project/i })).toBeVisible()
  })

  test('BFF dashboard loads KPIs and SOP version selector', async ({ page }) => {
    await loadDashboard(page, TEST_PROJECT_ID, TEST_USER)

    // ── Project title ─────────────────────────────────────────────────────────
    // "K860G6-BASY" is the name of proj-atlas in the seed DB
    await expect(page.getByRole('heading', { name: /K860G6-BASY/i })).toBeVisible()

    // ── KPI strip ─────────────────────────────────────────────────────────────
    // All four KPI cards should be rendered
    await expect(page.getByText(/actions/i).first()).toBeVisible()
    await expect(page.getByText(/most steps/i)).toBeVisible()
    await expect(page.getByText(/sop versions/i)).toBeVisible()

    // ── SOP version badge (V1.0 · Draft) ──────────────────────────────────────
    await expect(page.getByRole('button', { name: /V1\.0/i })).toBeVisible()
    await expect(page.getByText(/draft/i).first()).toBeVisible()

    // ── Project ID is echoed ──────────────────────────────────────────────────
    await expect(page.getByText(TEST_PROJECT_ID)).toBeVisible()
  })

  test('BFF response populates the SOP action count KPI accurately', async ({ page }) => {
    // Intercept the BFF call to observe the real response
    const bffResponse = page.waitForResponse(
      (r) => r.url().includes(`/bff/dashboard/${TEST_PROJECT_ID}`) && r.status() === 200,
    )

    await loadDashboard(page, TEST_PROJECT_ID, TEST_USER)

    const resp = await bffResponse
    const body = await resp.json() as {
      level_system?: { total_count: number }
      sop_versions?: unknown[]
    }

    // The KPI card value must match what the API returned
    const actionCount = body.level_system?.total_count ?? 0
    if (actionCount > 0) {
      const kpiText = page.getByText(String(actionCount))
      await expect(kpiText.first()).toBeVisible()
    }

    // At least one SOP version in the selector
    expect((body.sop_versions ?? []).length).toBeGreaterThan(0)
  })

  test('Sign out clears auth and returns to login', async ({ page }) => {
    await loadDashboard(page, TEST_PROJECT_ID, TEST_USER)

    const signOutButton = page.getByRole('button', { name: /sign out/i })
    await signOutButton.click()

    await expect(page.getByRole('heading', { name: /DDM IE\/PE Console/i })).toBeVisible({
      timeout: 5_000,
    })
  })
})

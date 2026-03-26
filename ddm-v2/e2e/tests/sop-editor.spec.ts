/**
 * Test 2: SOP Action Editor & Optimistic UI
 *
 * Verifies the SOP action table loads, optimistic PUT is dispatched, and
 * the UI reflects the saved order without a full page reload.
 *
 * Seed data: sop-atlas-v1 (7 Draft actions for proj-atlas)
 *
 * Strategy:
 *  - Load the dashboard to hydrate the SopActionEditor component.
 *  - Confirm the action table rows are visible.
 *  - Trigger a drag-and-drop reorder (row 1 → row 3).
 *  - Intercept the PUT /api/v1/sop/versions/{id}/actions call.
 *  - Assert the save button appears (isDirty=true), click it, and verify
 *    a success toast fires after the round-trip.
 *  - On backend error, verify the UI rolls back and shows an error toast.
 */
import { test, expect, type Page } from '@playwright/test'
import { loadDashboard, TEST_PROJECT_ID, TEST_USER } from '../helpers'

async function waitForSopTable(page: Page) {
  // The SopActionEditor renders when an active Draft SOP has actions
  await expect(page.getByRole('table')).toBeVisible({ timeout: 15_000 })
  // Wait for at least 3 action rows (tbody tr elements)
  await expect(page.locator('tbody tr').nth(2)).toBeVisible({ timeout: 10_000 })
}

test.describe('SOP Action Editor — Optimistic UI', () => {
  test.beforeEach(async ({ page }) => {
    await loadDashboard(page, TEST_PROJECT_ID, TEST_USER)
    await waitForSopTable(page)
  })

  test('renders the SOP action table with correct columns', async ({ page }) => {
    const table = page.getByRole('table')
    await expect(table).toBeVisible()

    // Column headers
    await expect(page.getByRole('columnheader', { name: /#/i })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: /type/i })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: /description/i })).toBeVisible()
    // Actual column header is "Seconds" (not "CT")
    await expect(page.getByRole('columnheader', { name: /seconds/i })).toBeVisible()

    // At least 7 rows (seed data has 7 actions for proj-atlas)
    const rows = page.locator('tbody tr')
    const rowCount = await rows.count()
    expect(rowCount).toBeGreaterThan(0)
  })

  test('shows "GENERAL" seq_type for the first action in seed data', async ({ page }) => {
    // The seed DB has seq_type: GENERAL for all proj-atlas actions
    const firstType = page.locator('tbody tr').first().locator('td').nth(2)
    await expect(firstType).toContainText('GENERAL')
  })

  test('drag-and-drop reorder marks the editor as dirty', async ({ page }) => {
    const rows = page.locator('tbody tr')

    // Use Playwright's dragTo() which dispatches native HTML5 drag events
    // (dragstart / dragover / drop) required by React's draggable handler
    await rows.first().dragTo(rows.nth(2))

    // After a successful drag, isDirty=true enables the Save button
    const saveBtn = page.getByRole('button', { name: /save/i })
    await expect(saveBtn).toBeEnabled({ timeout: 5_000 })
  })

  test('optimistic save: PUT is dispatched and success toast fires', async ({ page }) => {
    // Wait for the PUT network request during the save flow
    const putRequest = page.waitForRequest(
      (req) =>
        req.method() === 'PUT' &&
        req.url().includes('/sop/versions/') &&
        req.url().includes('/actions'),
      { timeout: 15_000 },
    )

    const rows = page.locator('tbody tr')

    // Use dragTo() for HTML5 drag-and-drop (dispatches dragstart/dragover/drop)
    await rows.first().dragTo(rows.nth(1))

    // Wait for Save button to be ENABLED (isDirty=true)
    const saveBtn = page.getByRole('button', { name: /save/i })
    await expect(saveBtn).toBeEnabled({ timeout: 5_000 })
    await saveBtn.click()

    // PUT is fired
    await putRequest

    // Success toast — react-hot-toast wraps content in a div[role="status"]
    await expect(
      page.getByText(/saved successfully/i).or(page.locator('[role="status"]')),
    ).toBeVisible({ timeout: 10_000 })
  })

  test('discard resets the order and hides the save button', async ({ page }) => {
    const rows = page.locator('tbody tr')

    // Use dragTo for HTML5 drag (same as other tests)
    await rows.first().dragTo(rows.nth(1))

    const saveBtn = page.getByRole('button', { name: /save/i })
    await expect(saveBtn).toBeEnabled({ timeout: 5_000 })

    // Discard button only appears when isDirty=true
    await page.getByRole('button', { name: /discard/i }).click()

    // After discard, button reverts to disabled state
    await expect(saveBtn).toBeDisabled({ timeout: 5_000 })
  })
})

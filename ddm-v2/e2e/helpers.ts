/**
 * Shared helpers & page-object utilities for DDM E2E tests.
 *
 * Seed credentials match the runtime-db.json fixture data:
 *   Engineer  → username: Avery   password: avery
 *   Manager   → username: admin   password: admin123
 */
import { type Page, expect } from '@playwright/test'

export const TEST_USER = { username: 'Avery', password: 'avery', name: 'Avery, Yeh' }
export const TEST_PROJECT_ID = 'proj-atlas'
export const TEST_SOP_VERSION = 'V1.0'

/**
 * Fill and submit the login form, then wait until the project selector appears.
 */
export async function login(page: Page, user = TEST_USER) {
  await page.goto('/')
  // Ensure we land on the login page
  await expect(page.getByRole('heading', { name: /DDM IE\/PE Console/i })).toBeVisible()

  // Use id-based locators — matches the htmlFor/id associations in LoginPage.tsx
  await page.locator('#username').fill(user.username)
  await page.locator('#password').fill(user.password)
  await page.getByRole('button', { name: /sign in/i }).click()

  // After successful login the project selector is shown
  await expect(page.getByRole('heading', { name: /open project/i })).toBeVisible({
    timeout: 10_000,
  })
}

/**
 * Log in and navigate to the dashboard for the default test project.
 */
export async function loadDashboard(
  page: Page,
  projectId = TEST_PROJECT_ID,
  user = TEST_USER,
) {
  await login(page, user)

  const input = page.getByPlaceholder(/project id/i)
  await input.fill(projectId)
  await page.getByRole('button', { name: /load dashboard/i }).click()

  // The KPI strip signals the BFF payload has loaded
  await expect(page.getByText(/actions/i).first()).toBeVisible({ timeout: 20_000 })
}

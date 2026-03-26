import { defineConfig, devices } from '@playwright/test'

/**
 * DDM IE/PE Console — Playwright configuration
 *
 * The test suite runs against the fully integrated containerised stack
 * (Nginx → FastAPI → JsonStore). globalSetup boots docker-compose.test.yml
 * before any test and globalTeardown shuts it down afterwards.
 *
 * Set E2E_BASE_URL to override the default frontend origin.
 */

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000'

export default defineConfig({
  testDir: './tests',
  fullyParallel: false, // Simulation tests share WS state; keep sequential
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],

  use: {
    baseURL: BASE_URL,
    // Industrial dashboard — wide viewport for the dense layout
    viewport: { width: 1440, height: 900 },
    // Keep a full trace on retry so failures are diagnosable in CI
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'on-first-retry',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },

  // Chromium only for CI speed; add Firefox/WebKit for optional cross-browser
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  globalSetup: './global-setup.ts',
  globalTeardown: './global-teardown.ts',
})

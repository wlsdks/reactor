import { defineConfig, devices } from '@playwright/test'

const host = '127.0.0.1'
const port = 3001
const baseURL = process.env.PLAYWRIGHT_BASE_URL || `http://${host}:${port}`
const webServer = process.env.PW_SKIP_WEBSERVER
  ? undefined
  : {
      command: `pnpm dev --host ${host} --port ${port}`,
      url: baseURL,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    }

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'list',
  use: {
    baseURL,
    trace: 'on-first-retry',
    serviceWorkers: 'block',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer,
})

import { test, expect } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

test.describe('Login page', () => {
  test.beforeEach(async ({ page }) => {
    // Ensure not authenticated; suppress onboarding tour on "/" so it never
    // intercepts redirect-time interactions if a follow-up assertion lands on
    // the dashboard before this script clears the storage state.
    await page.addInitScript(() => {
      localStorage.removeItem('reactor-admin-token')
      sessionStorage.removeItem('reactor-admin-feature-availability-v1')
      sessionStorage.removeItem('reactor-admin-feature-availability-v2')
      localStorage.setItem('reactor-admin-v1-1-release-onboarding-completed', new Date().toISOString())
    })
    // Return 401 for /me so we stay on login
    await page.route('**/api/auth/me', route => {
      route.fulfill({ status: 401, contentType: 'application/json', body: '{"error":"Unauthorized"}' })
    })
    await page.goto('/login')
    await page.waitForSelector('.login-card', { timeout: 15000 })
  })

  test('renders login card with logo and title', async ({ page }) => {
    await expect(page.locator('.login-card')).toBeVisible()
    await expect(page.locator('.login-header')).toBeVisible()
  })

  test('renders login form with email and password fields', async ({ page }) => {
    await expect(page.locator('input[type="password"]')).toBeVisible()
  })

  test('shows error on invalid credentials', async ({ page }) => {
    await page.route('**/api/auth/login', route => {
      route.fulfill({
        status: 401, contentType: 'application/json',
        body: JSON.stringify({ error: 'Invalid credentials' }),
      })
    })

    const inputs = page.locator('input')
    await inputs.nth(0).fill('wrong@example.com')
    await page.locator('input[type="password"]').fill('wrongpassword')
    await page.locator('button[type="submit"]').click()

    await expect(page.locator('.alert-error, .login-error').first()).toBeVisible({ timeout: 5000 })
  })

  test('successful login redirects to dashboard', async ({ page }) => {
    // Single handler for all API calls
    await page.route('**/*', async route => {
      const requestUrl = new URL(route.request().url())
      if (!requestUrl.pathname.startsWith('/api/')) {
        await route.continue()
        return
      }

      const url = requestUrl.toString()
      if (url.includes('/auth/login')) {
        // Hybrid: works for both direct (AuthResponse) AND IAM (IamTokenResponse) flows
        await route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({
            // AuthResponse fields (direct login path)
            token: MOCK_TOKEN,
            user: MOCK_USER,
            // IamTokenResponse fields (IAM step 1)
            requiresTwoFactor: false,
            accessToken: 'mock-iam-jwt-token',
            tokenType: 'Bearer',
            expiresIn: 3600,
          }),
        })
      } else if (url.includes('/auth/exchange')) {
        // IAM step 2: exchange IAM token for reactor token
        await route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }),
        })
      } else if (url.includes('/auth/me')) {
        await route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify(MOCK_USER),
        })
      } else {
        await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
      }
    })

    // Wait for the form to be interactive before filling — under heavy
    // parallel load the dev server can lag enough that the email input is in
    // the DOM but not yet hydrated, causing the submit click to fire before
    // the form's onSubmit is wired up.
    const emailInput = page.locator('input[type="email"], input').first()
    await expect(emailInput).toBeEditable()
    await emailInput.fill('admin@example.com')
    await page.locator('input[type="password"]').fill('password')
    const submit = page.locator('button[type="submit"]')
    await expect(submit).toBeEnabled()
    await submit.click()

    await expect(page).not.toHaveURL(/\/login/, { timeout: 15000 })
  })
})

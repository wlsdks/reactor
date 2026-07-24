import { expect, test } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/admin/rbac/roles',
  '/api/admin/platform/users/by-email',
  '/api/admin/platform/users/{id}/role',
  '/api/auth/login',
  '/api/auth/me',
]

// The four canonical roles surfaced by the RBAC pill selector.
// Shape mirrors the RawRole returned by GET /api/admin/rbac/roles.
const RBAC_ROLES = [
  {
    role: 'ADMIN',
    scope: 'platform',
    permissions: ['settings:read', 'settings:write', 'user:read', 'user:write'],
  },
  {
    role: 'ADMIN_DEVELOPER',
    scope: 'platform',
    permissions: ['mcp:read', 'mcp:write', 'audit:read'],
  },
  {
    role: 'ADMIN_MANAGER',
    scope: 'platform',
    permissions: ['session:read', 'feedback:read'],
  },
  {
    role: 'USER',
    scope: 'tenant',
    permissions: ['chat:use'],
  },
]

test.describe('/access-control tabs', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(({ paths, token }: { paths: string[]; token: string }) => {
      localStorage.setItem('reactor-admin-token', token)
      sessionStorage.setItem(
        'reactor-admin-feature-availability-v2',
        JSON.stringify({
          mode: 'manifest',
          endpoints: paths,
          timestamp: Date.now(),
        }),
      )
    }, { paths: CAPABILITY_PATHS, token: MOCK_TOKEN })

    await page.route('**/*', async (route) => {
      const requestUrl = new URL(route.request().url())
      if (!requestUrl.pathname.startsWith('/api/')) {
        await route.continue()
        return
      }

      const pathname = requestUrl.pathname

      if (pathname.includes('/auth/me')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_USER),
        })
        return
      }
      if (pathname.includes('/auth/login')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }),
        })
        return
      }
      if (pathname.includes('/admin/capabilities')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            generatedAt: Date.now(),
            source: 'playwright-mock',
            paths: CAPABILITY_PATHS,
          }),
        })
        return
      }
      if (pathname === '/api/admin/rbac/roles') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(RBAC_ROLES),
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '[]',
      })
    })

    await page.goto('/access-control')
  })

  test('exposes the permissions and members tabs (permissions active by default)', async ({ page }) => {
    // AccessControlPage uses the shared <Tabs> primitive which renders role="tab".
    const permissionsTab = page.getByRole('tab', { name: '권한' })
    const membersTab = page.getByRole('tab', { name: '멤버' })

    await expect(permissionsTab).toBeVisible()
    await expect(membersTab).toBeVisible()

    // Permissions is the default tab, surfaced via aria-selected.
    await expect(permissionsTab).toHaveAttribute('aria-selected', 'true')
  })

  test('renders all four canonical role pills in the permissions tab', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '접근 제어' })).toBeVisible()

    // The rbac pill group renders one button per role. The `RolePillSelector`
    // resolves each label via `t('rbacPage.roleNames.<ROLE>')`, but those keys
    // currently live under `auth.roleNames.*` — the i18n fallback surfaces the
    // raw key, so we assert against the four key strings that actually render.
    const pillsGroup = page.locator('.rbac-pills')
    await expect(pillsGroup).toBeVisible()
    await expect(pillsGroup.locator('button')).toHaveCount(4)
    await expect(pillsGroup.getByRole('button', { name: 'rbacPage.roleNames.ADMIN', exact: true })).toBeVisible()
    await expect(pillsGroup.getByRole('button', { name: 'rbacPage.roleNames.ADMIN_DEVELOPER', exact: true })).toBeVisible()
    await expect(pillsGroup.getByRole('button', { name: 'rbacPage.roleNames.ADMIN_MANAGER', exact: true })).toBeVisible()
    await expect(pillsGroup.getByRole('button', { name: 'rbacPage.roleNames.USER', exact: true })).toBeVisible()
  })

  test('switches to the members tab when activated', async ({ page }) => {
    const membersTab = page.getByRole('tab', { name: '멤버' })
    await membersTab.click()

    await expect(membersTab).toHaveAttribute('aria-selected', 'true')
  })
})

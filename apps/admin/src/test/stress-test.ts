/**
 * Frontend Stress Test
 *
 * Tests the UI with large/extreme data volumes to find:
 * - Rendering bottlenecks
 * - Layout breakage with long text
 * - Memory issues with large datasets
 * - Pagination edge cases
 * - Toast overflow behavior
 *
 * Run: npx tsx src/test/stress-test.ts
 * Requires: dev server running on localhost:3001 with VITE_MOCK=true
 */

import { chromium } from 'playwright'

const BASE_URL = 'http://localhost:3001'

interface TestResult {
  test: string
  status: 'PASS' | 'FAIL' | 'WARN'
  detail: string
  durationMs?: number
}

const results: TestResult[] = []

function log(msg: string) {
  console.log(`[${new Date().toISOString().slice(11, 19)}] ${msg}`)
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext()
  const page = await context.newPage()

  // Track errors
  const errors: string[] = []
  page.on('console', (msg) => {
    if (msg.type() === 'error' && !msg.text().includes('Failed to load resource')) {
      errors.push(msg.text())
    }
  })

  log('=== STRESS TEST START ===')

  // Login
  await page.goto(BASE_URL)
  await page.waitForTimeout(3000)
  try {
    await page.getByRole('button', { name: /dev|개발|빠른/i }).click()
    await page.waitForTimeout(4000)
  } catch {
    log('FATAL: Could not login')
    await browser.close()
    process.exit(1)
  }
  log(`Logged in: ${page.url()}`)

  // ── Test 1: Large table rendering ──
  log('\n--- Test 1: Large Table Rendering ---')
  {
    const routes = ['/sessions', '/feedback', '/audit', '/approvals']
    for (const route of routes) {
      const start = Date.now()
      await page.goto(`${BASE_URL}${route}`, { waitUntil: 'domcontentloaded', timeout: 15000 })
      await page.waitForTimeout(3000)

      const rowCount = await page.evaluate(() => {
        const rows = document.querySelectorAll('.data-table tbody tr')
        return rows.length
      })

      const renderTime = Date.now() - start
      const name = route.slice(1)

      results.push({
        test: `Table render: ${name}`,
        status: renderTime > 5000 ? 'FAIL' : renderTime > 3000 ? 'WARN' : 'PASS',
        detail: `${rowCount} rows rendered in ${renderTime}ms`,
        durationMs: renderTime,
      })
    }
  }

  // ── Test 2: Pagination stress ──
  log('\n--- Test 2: Pagination Stress ---')
  {
    await page.goto(`${BASE_URL}/audit`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)

    // Click next page repeatedly
    let pageClicks = 0
    const paginationStart = Date.now()
    for (let i = 0; i < 10; i++) {
      try {
        const nextBtn = page.getByRole('button', { name: /next|다음/i })
        if (await nextBtn.isVisible({ timeout: 1000 })) {
          await nextBtn.click()
          await page.waitForTimeout(300)
          pageClicks++
        } else {
          break
        }
      } catch {
        break
      }
    }
    const paginationTime = Date.now() - paginationStart

    results.push({
      test: 'Pagination: rapid page switching',
      status: paginationTime > 10000 ? 'FAIL' : 'PASS',
      detail: `${pageClicks} page switches in ${paginationTime}ms`,
      durationMs: paginationTime,
    })
  }

  // ── Test 3: Long text layout ──
  log('\n--- Test 3: Long Text Layout ---')
  {
    // Check if any text overflows its container
    await page.goto(`${BASE_URL}/personas`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)

    const overflows = await page.evaluate(() => {
      const elements = document.querySelectorAll('td, .detail-note, .page-subtitle, h1, h2, h3')
      let overflowCount = 0
      elements.forEach((el) => {
        const htmlEl = el as HTMLElement
        if (htmlEl.scrollWidth > htmlEl.clientWidth + 2) {
          overflowCount++
        }
      })
      return overflowCount
    })

    results.push({
      test: 'Text overflow check: personas',
      status: overflows > 5 ? 'WARN' : 'PASS',
      detail: `${overflows} elements with horizontal overflow`,
    })
  }

  // ── Test 4: Rapid navigation + memory ──
  log('\n--- Test 4: Rapid Navigation Memory ---')
  {
    const memBefore = await page.evaluate(() => {
      if ('memory' in performance) {
        return (performance as unknown as { memory: { usedJSHeapSize: number } }).memory.usedJSHeapSize
      }
      return null
    })

    const routes = [
      '/', '/issues', '/approvals', '/personas',
      '/prompt-studio', '/documents', '/sessions',
      '/feedback', '/audit', '/mcp-servers',
      '/chat-inspector', '/scheduler',
    ]

    // Navigate 60 times (5 full cycles)
    const navStart = Date.now()
    for (let cycle = 0; cycle < 5; cycle++) {
      for (const route of routes) {
        await page.goto(`${BASE_URL}${route}`, { waitUntil: 'domcontentloaded', timeout: 10000 })
        await page.waitForTimeout(200)
      }
    }
    const navTime = Date.now() - navStart

    const memAfter = await page.evaluate(() => {
      if ('memory' in performance) {
        return (performance as unknown as { memory: { usedJSHeapSize: number } }).memory.usedJSHeapSize
      }
      return null
    })

    if (memBefore && memAfter) {
      const growthMB = (memAfter - memBefore) / 1024 / 1024
      const growthPct = ((memAfter - memBefore) / memBefore) * 100

      results.push({
        test: 'Memory after 60 navigations',
        status: growthPct > 50 ? 'FAIL' : growthPct > 20 ? 'WARN' : 'PASS',
        detail: `${(memBefore / 1024 / 1024).toFixed(1)}MB → ${(memAfter / 1024 / 1024).toFixed(1)}MB (${growthPct.toFixed(1)}%)`,
        durationMs: navTime,
      })
    }

    results.push({
      test: 'Navigation speed (60 pages)',
      status: navTime > 60000 ? 'FAIL' : navTime > 30000 ? 'WARN' : 'PASS',
      detail: `60 navigations in ${(navTime / 1000).toFixed(1)}s (avg ${(navTime / 60).toFixed(0)}ms/page)`,
      durationMs: navTime,
    })
  }

  // ── Test 5: Dashboard with data ──
  log('\n--- Test 5: Dashboard Render Performance ---')
  {
    const start = Date.now()
    await page.goto(`${BASE_URL}/`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(5000)

    const hasHealthBar = await page.evaluate(() => !!document.querySelector('.health-bar'))
    const hasActionCards = await page.evaluate(() => !!document.querySelector('.action-cards'))
    const hasTrendCharts = await page.evaluate(() => !!document.querySelector('.trend-charts'))
    const hasInfraPanel = await page.evaluate(() => !!document.querySelector('.infra-panel'))

    const renderTime = Date.now() - start
    const components = [hasHealthBar, hasActionCards, hasTrendCharts, hasInfraPanel].filter(Boolean).length

    results.push({
      test: 'Dashboard render',
      status: components < 4 ? 'FAIL' : renderTime > 8000 ? 'WARN' : 'PASS',
      detail: `${components}/4 sections rendered in ${renderTime}ms`,
      durationMs: renderTime,
    })
  }

  // ── Test 6: Modal open/close stress ──
  log('\n--- Test 6: Modal Stress ---')
  {
    await page.goto(`${BASE_URL}/personas`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)

    let modalCycles = 0
    const modalStart = Date.now()

    for (let i = 0; i < 10; i++) {
      try {
        // Click create button
        const createBtn = page.getByRole('button', { name: /생성|create/i })
        if (await createBtn.isVisible({ timeout: 2000 })) {
          await createBtn.click()
          await page.waitForTimeout(500)

          // Close modal (press Escape)
          await page.keyboard.press('Escape')
          await page.waitForTimeout(300)
          modalCycles++
        }
      } catch {
        break
      }
    }
    const modalTime = Date.now() - modalStart

    results.push({
      test: 'Modal open/close (10 cycles)',
      status: modalCycles < 5 ? 'FAIL' : 'PASS',
      detail: `${modalCycles} cycles in ${modalTime}ms`,
      durationMs: modalTime,
    })
  }

  // ── Test 7: Sidebar toggle stress ──
  log('\n--- Test 7: Sidebar Toggle Stress ---')
  {
    const toggleStart = Date.now()
    let toggleCount = 0

    for (let i = 0; i < 20; i++) {
      try {
        const toggle = page.getByRole('button', { name: /네비게이션|navigation/i })
        if (await toggle.isVisible({ timeout: 1000 })) {
          await toggle.click()
          await page.waitForTimeout(100)
          toggleCount++
        }
      } catch {
        break
      }
    }
    const toggleTime = Date.now() - toggleStart

    results.push({
      test: 'Sidebar toggle (20 cycles)',
      status: toggleCount < 15 ? 'FAIL' : 'PASS',
      detail: `${toggleCount} toggles in ${toggleTime}ms`,
      durationMs: toggleTime,
    })
  }

  // ── Test 8: Console errors check ──
  log('\n--- Test 8: Error Accumulation ---')
  {
    const realErrors = errors.filter(e =>
      !e.includes('slack') && !e.includes('error-report') && !e.includes('405')
    )

    results.push({
      test: 'Console errors during all tests',
      status: realErrors.length > 10 ? 'FAIL' : realErrors.length > 0 ? 'WARN' : 'PASS',
      detail: `${realErrors.length} errors (${errors.length} total including expected)`,
    })

    if (realErrors.length > 0) {
      log('  Unexpected errors:')
      realErrors.slice(0, 5).forEach(e => log(`    ${e.substring(0, 100)}`))
    }
  }

  // ── Results ──
  await browser.close()

  log('\n\n========================================')
  log('        STRESS TEST RESULTS            ')
  log('========================================\n')

  for (const r of results) {
    const icon = r.status === 'PASS' ? 'PASS' : r.status === 'WARN' ? 'WARN' : 'FAIL'
    log(`[${icon}] ${r.test}`)
    log(`       ${r.detail}`)
    if (r.durationMs) log(`       (${r.durationMs}ms)`)
    log('')
  }

  const failures = results.filter(r => r.status === 'FAIL')
  const warnings = results.filter(r => r.status === 'WARN')
  const passed = results.filter(r => r.status === 'PASS')

  log(`Summary: ${results.length} tests — ${passed.length} passed, ${warnings.length} warnings, ${failures.length} failures`)

  process.exit(failures.length > 0 ? 1 : 0)
}

main().catch((e) => {
  console.error('Stress test crashed:', e)
  process.exit(2)
})

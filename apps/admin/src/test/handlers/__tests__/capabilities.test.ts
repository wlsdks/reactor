import { describe, expect, it } from 'vitest'
import { getRouteRequirements } from '../../../features/capabilities/requirements'
import { mockCapabilities } from '../capabilities'
import { mockToolAccuracy, mockToolStats } from '../tool-stats'

const RELEASE_OPERATION_ROUTES = [
  '/documents',
  '/rag-cache',
  '/feedback',
  '/evals',
  '/integrations',
  '/models',
] as const

describe('mock capability manifest', () => {
  it('advertises the globally polled doctor endpoints', () => {
    expect(mockCapabilities.paths).toEqual(expect.arrayContaining([
      '/api/admin/doctor',
      '/api/admin/doctor/summary',
    ]))
  })

  it.each(RELEASE_OPERATION_ROUTES)(
    'keeps the %s release operation route available in mock mode',
    (routePath) => {
      const manifestPaths = new Set(mockCapabilities.paths)
      const missingRequirements = getRouteRequirements(routePath)
        .filter((openApiPath) => !manifestPaths.has(openApiPath))

      expect(missingRequirements).toEqual([])
    },
  )

  it('keeps the execution history route available when its mock handlers are present', () => {
    const manifestPaths = new Set(mockCapabilities.paths)
    const missingRequirements = getRouteRequirements('/traces')
      .filter((openApiPath) => !manifestPaths.has(openApiPath))

    expect(missingRequirements).toEqual([])
    expect(mockCapabilities.paths).toEqual(expect.arrayContaining([
      '/api/admin/traces',
      '/api/admin/traces/{trace_id}/spans',
    ]))
  })

  it('keeps the AI role workspace available when its mock handlers are present', () => {
    const manifestPaths = new Set(mockCapabilities.paths)
    const missingRequirements = getRouteRequirements('/reactor-universe')
      .filter((openApiPath) => !manifestPaths.has(openApiPath))

    expect(missingRequirements).toEqual([])
    expect(mockCapabilities.paths).toContain('/api/admin/agent-specs')
  })

  it('keeps the conversation workspace available when its mock handlers are present', () => {
    const manifestPaths = new Set(mockCapabilities.paths)
    const missingRequirements = getRouteRequirements('/sessions')
      .filter((openApiPath) => !manifestPaths.has(openApiPath))

    expect(missingRequirements).toEqual([])
    expect(mockCapabilities.paths).toEqual(expect.arrayContaining([
      '/api/admin/sessions',
      '/api/admin/sessions/overview',
      '/api/admin/users',
      '/api/admin/users/{user_id}/sessions',
    ]))
  })

  it('keeps the AI usage report available with the endpoints it actually renders', () => {
    const manifestPaths = new Set(mockCapabilities.paths)
    const missingRequirements = getRouteRequirements('/usage')
      .filter((openApiPath) => !manifestPaths.has(openApiPath))

    expect(missingRequirements).toEqual([])
    expect(mockCapabilities.paths).toEqual(expect.arrayContaining([
      '/api/admin/users/usage/cost',
      '/api/admin/users/usage/daily',
      '/api/admin/users/usage/by-model',
    ]))
    expect(mockCapabilities.paths).not.toContain('/api/admin/users/usage/top')
  })

  it('keeps every visible service-quality tab available in mock mode', () => {
    const manifestPaths = new Set(mockCapabilities.paths)
    const missingRouteRequirements = getRouteRequirements('/performance')
      .filter((openApiPath) => !manifestPaths.has(openApiPath))

    expect(missingRouteRequirements).toEqual([])
    expect(mockCapabilities.paths).toEqual(expect.arrayContaining([
      '/api/admin/metrics/latency/summary',
      '/api/admin/metrics/latency/timeseries',
      '/api/admin/conversation-analytics/by-channel',
      '/api/admin/conversation-analytics/failure-patterns',
      '/api/admin/conversation-analytics/latency-distribution',
      '/api/admin/tools/stats',
      '/api/admin/tools/accuracy',
    ]))
  })

  it('keeps the evaluation workspace aligned with the data it renders', async () => {
    const manifestPaths = new Set(mockCapabilities.paths)
    const missingRouteRequirements = getRouteRequirements('/evals')
      .filter((openApiPath) => !manifestPaths.has(openApiPath))

    expect(missingRouteRequirements).toEqual([])
    expect(mockCapabilities.paths).toEqual(expect.arrayContaining([
      '/api/admin/evals/runs',
      '/api/admin/evals/pass-rate',
      '/api/admin/agent-eval/cases',
    ]))

    const [runsResponse, passRateResponse] = await Promise.all([
      fetch('http://localhost/api/admin/evals/runs?days=30'),
      fetch('http://localhost/api/admin/evals/pass-rate?days=30'),
    ])

    expect(runsResponse.ok).toBe(true)
    await expect(runsResponse.json()).resolves.toEqual(expect.arrayContaining([
      expect.objectContaining({
        eval_run_id: expect.any(String),
        total_cases: expect.any(Number),
        pass_count: expect.any(Number),
        avg_score: expect.any(Number),
      }),
    ]))
    expect(passRateResponse.ok).toBe(true)
    await expect(passRateResponse.json()).resolves.toEqual(expect.arrayContaining([
      expect.objectContaining({
        day: expect.any(String),
        total: expect.any(Number),
        passed: expect.any(Number),
        avg_score: expect.any(Number),
      }),
    ]))
  })

  it('serves the tool stability data advertised by the service-quality route', async () => {
    const [statsResponse, accuracyResponse] = await Promise.all([
      fetch('http://localhost/api/admin/tools/stats'),
      fetch('http://localhost/api/admin/tools/accuracy'),
    ])

    expect(statsResponse.ok).toBe(true)
    await expect(statsResponse.json()).resolves.toEqual(mockToolStats)
    expect(accuracyResponse.ok).toBe(true)
    await expect(accuracyResponse.json()).resolves.toEqual(mockToolAccuracy)
  })

  it('serves the policy seed operation advertised by the documents route', async () => {
    const response = await fetch('http://localhost/api/admin/rag/seed-policy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        entries: [
          { key: 'release-check', title: 'Release check', content: 'Mock document' },
        ],
      }),
    })

    expect(response.ok).toBe(true)
    await expect(response.json()).resolves.toEqual({
      documentCount: 1,
      chunkCount: 2,
      keys: ['release-check'],
      durationMs: 42,
    })
  })

  it('serves precise cache invalidation and runtime settings operations', async () => {
    const [invalidateResponse, settingsResponse] = await Promise.all([
      fetch('http://localhost/api/admin/platform/cache/invalidate-key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'release:check' }),
      }),
      fetch('http://localhost/api/admin/settings?limit=200'),
    ])

    expect(invalidateResponse.ok).toBe(true)
    await expect(invalidateResponse.json()).resolves.toEqual({
      invalidated: true,
      cacheEnabled: true,
    })
    expect(settingsResponse.ok).toBe(true)
    await expect(settingsResponse.json()).resolves.toEqual(expect.arrayContaining([
      expect.objectContaining({ key: 'cache.enabled', value: 'true' }),
    ]))
  })
})

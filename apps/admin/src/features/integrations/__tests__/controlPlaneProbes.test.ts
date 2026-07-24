import { describe, expect, it } from 'vitest'
import {
  CONTROL_PLANE_PROBE_SPECS,
  summarizeControlPlaneProbe,
  summarizeControlPlaneProbes,
} from '../controlPlaneProbes'

describe('controlPlaneProbes', () => {
  it('includes release smoke probes for Slack, A2A, and provider readiness', () => {
    expect(CONTROL_PLANE_PROBE_SPECS).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: 'slackCommands', path: '/api/slack/commands' }),
        expect.objectContaining({ id: 'slackEvents', path: '/api/slack/events' }),
        expect.objectContaining({ id: 'a2aDiagnostics', path: '/api/v1/a2a/diagnostics' }),
        expect.objectContaining({ id: 'providerModels', path: '/api/admin/models' }),
      ]),
    )
  })

  it('uses the backend route methods for endpoints that do not expose a safe GET probe', () => {
    expect(CONTROL_PLANE_PROBE_SPECS).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: 'approvals',
          path: '/api/approvals',
          method: 'OPTIONS',
          reachableStatusCodes: expect.arrayContaining([405]),
        }),
        expect.objectContaining({
          id: 'slackCommands',
          method: 'OPTIONS',
          reachableStatusCodes: expect.arrayContaining([405]),
        }),
        expect.objectContaining({
          id: 'slackEvents',
          method: 'OPTIONS',
          reachableStatusCodes: expect.arrayContaining([405]),
        }),
        expect.objectContaining({
          id: 'errorReport',
          method: 'OPTIONS',
          reachableStatusCodes: expect.arrayContaining([405]),
        }),
      ]),
    )
  })

  it('marks declared healthy endpoints as pass', () => {
    const manifest = new Set(['/api/admin/capabilities'])
    const result = summarizeControlPlaneProbe(
      { id: 'capabilities', path: '/api/admin/capabilities' },
      { status: 200, body: { paths: [] }, durationMs: 24 },
      manifest,
    )

    expect(result.status).toBe('PASS')
    expect(result.reason).toBe('ready')
    expect(result.manifestDeclared).toBe(true)
  })

  it('warns when an endpoint is reachable but missing from the manifest', () => {
    const result = summarizeControlPlaneProbe(
      { id: 'schedulerJobs', path: '/api/scheduler/jobs' },
      { status: 200, body: [], durationMs: 15 },
      new Set(['/api/ops/dashboard']),
    )

    expect(result.status).toBe('WARN')
    expect(result.reason).toBe('reachableUndeclared')
    expect(result.manifestDeclared).toBe(false)
  })

  it('treats a 405 on POST-only integration routes as reachable', () => {
    const result = summarizeControlPlaneProbe(
      { id: 'slackCommands', path: '/api/slack/commands', reachableStatusCodes: [405] },
      { status: 405, body: { error: 'Method not allowed' }, durationMs: 17 },
      new Set(['/api/slack/commands']),
    )

    expect(result.status).toBe('PASS')
    expect(result.reason).toBe('ready')
    expect(result.detail).toBe('Route reachable (HTTP 405)')
  })

  it('fails when a declared endpoint breaks before returning a response', () => {
    const result = summarizeControlPlaneProbe(
      { id: 'auditLogs', path: '/api/admin/audits?limit=5' },
      { status: null, body: null, durationMs: 41, error: 'Failed to fetch' },
      new Set(['/api/admin/audits']),
    )

    expect(result.status).toBe('FAIL')
    expect(result.reason).toBe('probeFailed')
    expect(result.detail).toBe('Failed to fetch')
  })

  it('warns when an endpoint is not advertised and returns 404', () => {
    const result = summarizeControlPlaneProbe(
      { id: 'schedulerJobs', path: '/api/scheduler/jobs' },
      { status: 404, body: { error: 'Not found' }, durationMs: 9 },
      new Set(['/api/ops/dashboard']),
    )

    expect(result.status).toBe('WARN')
    expect(result.reason).toBe('notAdvertised')
    expect(result.detail).toBe('Not found')
  })

  it('preserves transport failures even when an endpoint is not advertised', () => {
    const result = summarizeControlPlaneProbe(
      { id: 'mcpSecurity', path: '/api/mcp/security' },
      { status: null, body: null, durationMs: 18, error: 'socket hang up' },
      new Set(['/api/admin/capabilities']),
    )

    expect(result.status).toBe('WARN')
    expect(result.reason).toBe('probeFailed')
    expect(result.detail).toBe('socket hang up')
  })

  it('summarizes pass warn fail counts', () => {
    const summary = summarizeControlPlaneProbes([
      {
        id: 'capabilities',
        path: '/api/admin/capabilities',
        status: 'PASS',
        reason: 'ready',
        manifestDeclared: true,
        httpStatus: 200,
        durationMs: 10,
        detail: 'OK',
      },
      {
        id: 'schedulerJobs',
        path: '/api/scheduler/jobs',
        status: 'WARN',
        reason: 'notAdvertised',
        manifestDeclared: false,
        httpStatus: 404,
        durationMs: 12,
        detail: 'Not found',
      },
      {
        id: 'auditLogs',
        path: '/api/admin/audits?limit=5',
        status: 'FAIL',
        reason: 'probeFailed',
        manifestDeclared: true,
        httpStatus: null,
        durationMs: 30,
        detail: 'Failed to fetch',
      },
    ])

    expect(summary).toEqual({
      total: 3,
      passCount: 1,
      warnCount: 1,
      failCount: 1,
      declaredCount: 2,
    })
  })
})

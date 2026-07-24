import { describe, expect, it } from 'vitest'
import {
  buildDebugReplayInspectorHref,
  buildMissingQueryInspectorHref,
  buildTrustEventInspectorHref,
  isDebugReplayCaptureReplayable,
  parseChatInspectorPrefill,
} from '../prefill'
import type { DebugReplayCapture } from '../../debug-replay/types'

describe('chat inspector prefill', () => {
  it('builds dashboard trust event links with compact query context', () => {
    const href = buildTrustEventInspectorHref({
      occurredAt: 1,
      type: 'unverified_response',
      severity: 'WARN',
      channel: 'slack',
      queryCluster: '93bd4b524029',
      queryLabel: 'Question cluster 93bd4b524029',
      reason: 'unverified_sources',
    })

    expect(href).toContain('/chat-inspector?')
    expect(href).toContain('channel=slack')
    expect(href).toContain('queryCluster=93bd4b524029')
    expect(href).toContain('queryLabel=Question+cluster+93bd4b524029')
  })

  it('parses dashboard trust event links into chat inspector defaults', () => {
    const prefill = parseChatInspectorPrefill(new URLSearchParams(
      'channel=slack&queryCluster=93bd4b524029&queryLabel=Question+cluster+93bd4b524029&eventType=unverified_response&severity=WARN&reason=unverified_sources'
    ))

    expect(prefill).toEqual({
      message: '',
      metadata: {
        diagnosticSource: 'dashboard-trust-event',
        channel: 'slack',
        queryCluster: '93bd4b524029',
        queryLabel: 'Question cluster 93bd4b524029',
        trustEventType: 'unverified_response',
        trustEventSeverity: 'WARN',
        trustEventReason: 'unverified_sources',
      },
      severity: 'WARN',
      eventType: 'unverified_response',
      queryLabel: 'Question cluster 93bd4b524029',
      model: null,
      tools: null,
    })
  })

  it('returns null when no prefill parameters exist', () => {
    expect(parseChatInspectorPrefill(new URLSearchParams(''))).toBeNull()
  })

  it('builds missing query links for direct repro from dashboard', () => {
    const href = buildMissingQueryInspectorHref({
      queryCluster: 'f1e6a063a8d0',
      queryLabel: 'Question cluster f1e6a063a8d0',
      count: 3,
      lastOccurredAt: 1,
      blockReason: 'unverified_sources',
    })

    expect(href).toContain('/chat-inspector?')
    expect(href).toContain('queryCluster=f1e6a063a8d0')
    expect(href).toContain('queryLabel=Question+cluster+f1e6a063a8d0')
    expect(href).toContain('diagnosticSource=dashboard-missing-query')
    expect(href).toContain('eventType=unverified_response')
    expect(href).toContain('reason=unverified_sources')
  })

  it('parses missing query links into targeted dashboard metadata', () => {
    const prefill = parseChatInspectorPrefill(new URLSearchParams(
      'queryCluster=f1e6a063a8d0&queryLabel=Question+cluster+f1e6a063a8d0&diagnosticSource=dashboard-missing-query&eventType=unverified_response&severity=WARN&reason=unverified_sources'
    ))

    expect(prefill).toEqual({
      message: '',
      metadata: {
        diagnosticSource: 'dashboard-missing-query',
        queryCluster: 'f1e6a063a8d0',
        queryLabel: 'Question cluster f1e6a063a8d0',
        trustEventType: 'unverified_response',
        trustEventSeverity: 'WARN',
        trustEventReason: 'unverified_sources',
      },
      severity: 'WARN',
      eventType: 'unverified_response',
      queryLabel: 'Question cluster f1e6a063a8d0',
      model: null,
      tools: null,
    })
  })

  describe('debug replay', () => {
    const baseCapture: DebugReplayCapture = {
      id: 'cap-abc123',
      tenantId: 'default',
      userHash: 'deadbeef',
      capturedAt: '2026-04-24T10:00:00Z',
      userPrompt: 'Why did this request fail?',
      errorCode: 'MODEL_TIMEOUT',
      errorMessage: 'Upstream timeout after 30s',
      modelId: 'gpt-4o-mini',
      toolsAttempted: 'search_docs,fetch_url',
      expiresAt: '2026-05-01T10:00:00Z',
    }

    it('builds a chat-inspector href with prompt, model, tools, and capture id', () => {
      const href = buildDebugReplayInspectorHref(baseCapture)

      expect(href).toContain('/chat-inspector?')
      expect(href).toContain('message=Why+did+this+request+fail%3F')
      expect(href).toContain('model=gpt-4o-mini')
      expect(href).toContain('tools=search_docs%2Cfetch_url')
      expect(href).toContain('reason=MODEL_TIMEOUT')
      expect(href).toContain('diagnosticSource=debug-replay')
      expect(href).toContain('captureId=cap-abc123')
    })

    it('omits optional fields when capture only has a prompt', () => {
      const href = buildDebugReplayInspectorHref({
        ...baseCapture,
        modelId: null,
        toolsAttempted: null,
        errorCode: null,
      })

      expect(href).toContain('message=Why+did+this+request+fail%3F')
      expect(href).not.toContain('model=')
      expect(href).not.toContain('tools=')
      expect(href).not.toContain('reason=')
      expect(href).toContain('captureId=cap-abc123')
    })

    it('considers captures replayable when a prompt is present', () => {
      expect(isDebugReplayCaptureReplayable(baseCapture)).toBe(true)
      expect(isDebugReplayCaptureReplayable({ ...baseCapture, userPrompt: '' })).toBe(false)
      expect(isDebugReplayCaptureReplayable({ ...baseCapture, userPrompt: '   ' })).toBe(false)
    })

    it('parses a debug-replay link back into chat inspector prefill with model and tools', () => {
      const href = buildDebugReplayInspectorHref(baseCapture)
      const query = href.split('?')[1]
      const prefill = parseChatInspectorPrefill(new URLSearchParams(query))

      expect(prefill).not.toBeNull()
      expect(prefill?.message).toBe('Why did this request fail?')
      expect(prefill?.model).toBe('gpt-4o-mini')
      expect(prefill?.tools).toBe('search_docs,fetch_url')
      expect(prefill?.metadata).toMatchObject({
        diagnosticSource: 'debug-replay',
        debugReplayCaptureId: 'cap-abc123',
        toolsAttempted: 'search_docs,fetch_url',
        trustEventReason: 'MODEL_TIMEOUT',
      })
    })

    it('falls back to debug-replay diagnostic source when captureId is present but no explicit source', () => {
      const prefill = parseChatInspectorPrefill(new URLSearchParams('captureId=cap-xyz&message=hello'))
      expect(prefill?.metadata.diagnosticSource).toBe('debug-replay')
    })
  })
})

import type { DashboardMissingQuery, DashboardRecentTrustEvent } from '../dashboard/types'
import type { DebugReplayCapture } from '../debug-replay/types'

export interface ChatInspectorPrefill {
  message: string
  metadata: Record<string, unknown>
  severity?: string | null
  eventType?: string | null
  queryLabel?: string | null
  model?: string | null
  tools?: string | null
}

function trimmed(value: string | null | undefined): string | null {
  const normalized = value?.trim()
  if (!normalized) return null
  return normalized
}

/**
 * Build a `/chat-inspector` URL pre-populated with a captured failed request so
 * a developer can reproduce it. Used by Debug Replay's Replay action.
 */
export function buildDebugReplayInspectorHref(capture: DebugReplayCapture): string {
  const params = new URLSearchParams()
  const message = trimmed(capture.userPrompt)
  const model = trimmed(capture.modelId)
  const tools = trimmed(capture.toolsAttempted)
  const errorCode = trimmed(capture.errorCode)

  if (message != null) params.set('message', message)
  if (model != null) params.set('model', model)
  if (tools != null) params.set('tools', tools)
  if (errorCode != null) params.set('reason', errorCode)
  params.set('diagnosticSource', 'debug-replay')
  params.set('captureId', capture.id)

  return `/chat-inspector?${params.toString()}`
}

/**
 * Debug Replay captures only carry a prompt (and sometimes model/tools). When
 * all reproducible fields are missing the Replay button is rendered disabled.
 */
export function isDebugReplayCaptureReplayable(capture: DebugReplayCapture): boolean {
  return trimmed(capture.userPrompt) != null
}

export function buildTrustEventInspectorHref(event: DashboardRecentTrustEvent): string {
  const params = new URLSearchParams()

  const entries: Array<[string, string | null]> = [
    ['channel', trimmed(event.channel)],
    ['queryCluster', trimmed(event.queryCluster)],
    ['queryLabel', trimmed(event.queryLabel)],
    ['eventType', trimmed(event.type)],
    ['severity', trimmed(event.severity)],
    ['reason', trimmed(event.reason)],
    ['stage', trimmed(event.stage)],
    ['action', trimmed(event.action)],
    ['violation', trimmed(event.violation)],
    ['policy', trimmed(event.policy)],
  ]

  entries.forEach(([key, value]) => {
    if (value != null) params.set(key, value)
  })

  return `/chat-inspector?${params.toString()}`
}

export function buildMissingQueryInspectorHref(query: DashboardMissingQuery): string {
  const params = new URLSearchParams()
  const reason = trimmed(query.blockReason)
  params.set('queryCluster', query.queryCluster)
  params.set('queryLabel', query.queryLabel)
  params.set('diagnosticSource', 'dashboard-missing-query')
  params.set('eventType', 'unverified_response')
  params.set('severity', 'WARN')
  if (reason != null) params.set('reason', reason)
  return `/chat-inspector?${params.toString()}`
}

export function parseChatInspectorPrefill(searchParams: URLSearchParams): ChatInspectorPrefill | null {
  const message = trimmed(searchParams.get('message')) ?? ''
  const diagnosticSource = trimmed(searchParams.get('diagnosticSource'))
  const eventType = trimmed(searchParams.get('eventType'))
  const severity = trimmed(searchParams.get('severity'))
  const channel = trimmed(searchParams.get('channel'))
  const queryCluster = trimmed(searchParams.get('queryCluster'))
  const queryLabel = trimmed(searchParams.get('queryLabel'))
  const reason = trimmed(searchParams.get('reason'))
  const stage = trimmed(searchParams.get('stage'))
  const action = trimmed(searchParams.get('action'))
  const violation = trimmed(searchParams.get('violation'))
  const policy = trimmed(searchParams.get('policy'))
  const model = trimmed(searchParams.get('model'))
  const tools = trimmed(searchParams.get('tools'))
  const captureId = trimmed(searchParams.get('captureId'))

  if (
    message.length === 0 &&
    eventType == null &&
    severity == null &&
    channel == null &&
    queryCluster == null &&
    queryLabel == null &&
    model == null &&
    tools == null &&
    captureId == null
  ) {
    return null
  }

  const defaultSource = captureId != null ? 'debug-replay' : 'dashboard-trust-event'
  const metadata: Record<string, unknown> = {
    diagnosticSource: diagnosticSource ?? defaultSource,
  }
  if (channel != null) metadata.channel = channel
  if (queryCluster != null) metadata.queryCluster = queryCluster
  if (queryLabel != null) metadata.queryLabel = queryLabel
  if (eventType != null) metadata.trustEventType = eventType
  if (severity != null) metadata.trustEventSeverity = severity
  if (reason != null) metadata.trustEventReason = reason
  if (stage != null) metadata.trustEventStage = stage
  if (action != null) metadata.trustEventAction = action
  if (violation != null) metadata.trustEventViolation = violation
  if (policy != null) metadata.trustEventPolicy = policy
  if (tools != null) metadata.toolsAttempted = tools
  if (captureId != null) metadata.debugReplayCaptureId = captureId

  return {
    message,
    metadata,
    severity,
    eventType,
    queryLabel,
    model,
    tools,
  }
}

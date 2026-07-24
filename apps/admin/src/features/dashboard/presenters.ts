import type {
  DashboardEmployeeValueBucket,
  DashboardEmployeeValueSummary,
  DashboardRecentSchedulerExecution,
  DashboardRecentTrustEvent,
} from './types'
import type { TFunction } from 'i18next'

export function humanizeMetricName(name: string, t: TFunction): string {
  const labels: Record<string, string> = {
    'api.requests.total': t('dashboard.metricLabel.apiRequests'),
    'api.latency.p99': t('dashboard.metricLabel.apiLatency'),
    'mcp.tool_calls.total': t('dashboard.metricLabel.toolCalls'),
    'tokens.consumed.total': t('dashboard.metricLabel.tokensConsumed'),
    'reactor.agent.executions': t('dashboard.metricLabel.agentExecutions'),
    'reactor.agent.errors': t('dashboard.metricLabel.agentErrors'),
    'reactor.agent.requests': t('dashboard.metricLabel.agentRequests'),
  }
  return labels[name] ?? name.replace(/^(reactor\.|agent\.)/, '').replace(/[._]/g, ' ')
}

export function describeTrustEventType(event: DashboardRecentTrustEvent): string {
  if (event.type === 'output_guard') {
    if (event.action === 'rejected') return 'OUTPUT_GUARD_REJECTED'
    if (event.action === 'modified') return 'OUTPUT_GUARD_MODIFIED'
    return 'OUTPUT_GUARD'
  }
  if (event.type === 'boundary_violation') return 'BOUNDARY_VIOLATION'
  if (event.type === 'unverified_response') return 'UNVERIFIED_RESPONSE'
  return event.type.toUpperCase()
}

export function describeTrustEventDetail(event: DashboardRecentTrustEvent): string {
  const parts = [
    event.queryLabel ? `cluster:${event.queryLabel}` : null,
    event.reason,
    event.stage ? `stage:${event.stage}` : null,
    event.violation,
    event.policy ? `policy:${event.policy}` : null,
  ].filter(Boolean)

  return parts.join(' / ') || '—'
}

export function describeTrustEventScope(event: DashboardRecentTrustEvent): string {
  const parts = [
    event.channel ? `channel:${event.channel}` : null,
    event.queryCluster ? `cluster:${event.queryCluster}` : null,
  ].filter(Boolean)

  return parts.join(' / ') || '—'
}

export function dashboardExecutionTimestamp(execution: DashboardRecentSchedulerExecution): number {
  return execution.completedAt ?? execution.startedAt
}

export function humanizeAnswerMode(answerMode: string): string {
  switch (answerMode) {
    case 'knowledge':
      return 'Knowledge'
    case 'operational':
      return 'Operational'
    case 'hybrid':
      return 'Hybrid'
    case 'unknown':
      return 'Unknown'
    default:
      return answerMode
  }
}

export function humanizeToolFamily(toolFamily: string): string {
  switch (toolFamily) {
    case 'confluence':
      return 'Confluence'
    case 'jira':
      return 'Jira'
    case 'bitbucket':
      return 'Bitbucket'
    case 'work':
      return 'Work'
    case 'mixed':
      return 'Mixed'
    case 'none':
      return 'None'
    default:
      return toolFamily
  }
}

export function humanizeChannel(channel: string): string {
  switch (channel) {
    case 'slack':
      return 'Slack'
    case 'web':
      return 'Web'
    case 'admin':
      return 'Admin'
    case 'unknown':
      return 'Unknown'
    default:
      return channel
  }
}

export function topBucketLabel(bucket: DashboardEmployeeValueBucket): string {
  return `${humanizeToolFamily(bucket.key)}: ${bucket.count}`
}

export function laneCoverageLabel(groundedRatePercent: number): string {
  return `${groundedRatePercent}%`
}

export function coverageColor(percent: number): string {
  if (percent >= 80) return 'var(--green)'
  if (percent >= 50) return 'var(--yellow)'
  return 'var(--red)'
}

export interface EmployeeValueFocusHint {
  title: string
  detail: string
}

export function deriveEmployeeValueFocus(employeeValue: DashboardEmployeeValueSummary | null | undefined): EmployeeValueFocusHint[] {
  if (!employeeValue || employeeValue.observedResponses === 0) return []

  const hints: EmployeeValueFocusHint[] = []
  const topLane = employeeValue.lanes[0]
  const topMissingQuery = employeeValue.topMissingQueries[0]

  if (topLane && topLane.answerMode === 'unknown' && topLane.blockedResponses > 0) {
    hints.push({
      title: 'Routing or source coverage',
      detail: 'Unknown lane dominates blocked traffic. Check tool routing, source enforcement, and repeated blocked questions first.',
    })
  }

  const knowledgeLane = employeeValue.lanes.find(lane => lane.answerMode === 'knowledge')
  if (knowledgeLane && knowledgeLane.groundedRatePercent < 70 && knowledgeLane.observedResponses >= 3) {
    hints.push({
      title: 'Confluence knowledge hygiene',
      detail: 'Knowledge lane coverage is weak. Review authoritative spaces, titles, labels, and missing policy pages.',
    })
  }

  const operationalLane = employeeValue.lanes.find(lane => lane.answerMode === 'operational')
  if (operationalLane && operationalLane.groundedRatePercent < 70 && operationalLane.observedResponses >= 3) {
    hints.push({
      title: 'Operational source quality',
      detail: 'Operational lane is under-grounded. Check Jira/Bitbucket source links, allowlists, and work-tool normalization.',
    })
  }

  if (employeeValue.scheduledResponses > employeeValue.interactiveResponses && employeeValue.blockedResponses > 0) {
    hints.push({
      title: 'Scheduler template review',
      detail: 'Scheduled traffic is dominating while blocked responses exist. Tighten recurring templates before widening usage.',
    })
  }

  if (hints.length === 0 && topMissingQuery) {
    hints.push({
      title: 'Close repeated blocked questions',
      detail: `Most frequent blocked cluster: ${topMissingQuery.queryLabel}. Fix this loop first before adding new features.`,
    })
  }

  return hints.slice(0, 2)
}

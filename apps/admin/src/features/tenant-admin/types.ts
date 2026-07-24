export interface TenantUsageRangeParams {
  fromMs?: number
  toMs?: number
}

export interface TenantQuotaResponse {
  tenantId: string
  quota: {
    maxRequestsPerMonth: number
    maxTokensPerMonth: number
    maxUsers: number
    maxAgents: number
    maxMcpServers: number
  }
  usage: {
    requests: number
    tokens: number
    costUsd: string
  }
  requestUsagePercent: number
  tokenUsagePercent: number
}

export interface TenantOverviewResponse {
  totalRequests: number
  successRate: number
  avgResponseTimeMs: number
  apdexScore: number
  sloAvailability: number
  errorBudgetRemaining: number
  monthlyCost: string
  activeAlerts: number
}

export interface TimeSeriesPoint {
  time: string
  value: number
}

export interface TenantUserUsage {
  userLabel: string
  requests: number
  tokens: number
  costUsd: number
  lastActivity: number | null
}

export interface TenantUsageResponse {
  timeSeries: TimeSeriesPoint[]
  channelDistribution: Record<string, number>
  topUsers: TenantUserUsage[]
  avgTurnsPerSession: number
  sessionAbandonRate: number
  sessionResolveRate: number
}

export interface TenantQualityResponse {
  successRateTrend: TimeSeriesPoint[]
  apdexTrend: TimeSeriesPoint[]
  latencyP50: number
  latencyP95: number
  latencyP99: number
  errorDistribution: Record<string, number>
}

export interface TenantToolUsage {
  toolName: string
  calls: number
  successRate: number
  avgDurationMs: number
  p95DurationMs: number
  mcpServerName: string | null
}

export interface TenantToolsResponse {
  toolRanking: TenantToolUsage[]
  slowestTools: TenantToolUsage[]
  statusCounts: Record<string, number>
}

export interface TenantCostResponse {
  monthlyCost: string
  dailyCostTrend: TimeSeriesPoint[]
  costByModel: Record<string, string>
  costPerResolution: string
  cachedTokenRatio: number
  budgetUsagePercent: number
}

export interface TenantSloResponse {
  tenantId: string
  sloAvailability: number
  sloLatencyP99Ms: number
  currentAvailability: number
  latencyP99Ms: number
  errorBudgetRemaining: number
}

export interface TenantAlertResponse {
  id: string
  ruleId: string
  tenantId: string | null
  severity: string
  status: string
  message: string
  metricValue: number
  threshold: number
  firedAt: number
  resolvedAt: number | null
  acknowledgedBy: string | null
}

export interface TenantExportRangeParams {
  fromMs?: number
  toMs?: number
}

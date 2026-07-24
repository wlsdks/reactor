export type TenantPlan = 'FREE' | 'STARTER' | 'BUSINESS' | 'ENTERPRISE'
export type TenantStatus = 'ACTIVE' | 'SUSPENDED' | 'DEACTIVATED'

export interface TenantQuota {
  maxRequestsPerMonth: number
  maxTokensPerMonth: number
  maxUsers: number
  maxAgents: number
  maxMcpServers: number
}

export interface Tenant {
  id: string
  name: string
  slug: string
  plan: TenantPlan
  status: TenantStatus
  quota: TenantQuota
  billingCycleStart: number
  billingEmail: string | null
  sloAvailability: number
  sloLatencyP99Ms: number
  metadata: Record<string, unknown>
  createdAt: string
  updatedAt: string
}

export interface PlatformHealthDashboard {
  pipelineBufferUsage: number
  pipelineDropRate: number
  pipelineWriteLatencyMs: number
  pipelineMetricsAvailable: boolean
  responseCacheEnabled: boolean
  activeAlerts: number
  cacheExactHits: number
  cacheSemanticHits: number
  cacheMisses: number
}

export interface CacheInvalidationResult {
  invalidated: boolean
  cacheEnabled: boolean
  message: string
}

export interface CreateTenantRequest {
  name: string
  slug: string
  plan: TenantPlan
}

export interface ModelPricing {
  id: string
  provider: string
  model: string
  promptPricePer1m: string
  completionPricePer1m: string
  cachedInputPricePer1m: string
  reasoningPricePer1m: string
  batchPromptPricePer1m: string
  batchCompletionPricePer1m: string
  effectiveFrom: string
  effectiveTo: string | null
}

export interface ModelPricingRequest {
  id: string
  provider: string
  model: string
  promptPricePer1m: number
  completionPricePer1m: number
  cachedInputPricePer1m: number
  reasoningPricePer1m: number
  batchPromptPricePer1m: number
  batchCompletionPricePer1m: number
  effectiveFrom: string
  effectiveTo: string | null
}

export type AlertType = 'STATIC_THRESHOLD' | 'BASELINE_ANOMALY' | 'ERROR_BUDGET_BURN_RATE'
export type AlertSeverity = 'INFO' | 'WARNING' | 'CRITICAL'

export interface AlertRule {
  id?: string
  tenantId?: string | null
  name: string
  description?: string
  type: AlertType
  severity?: AlertSeverity
  metric: string
  threshold: number
  windowMinutes?: number
  enabled?: boolean
  platformOnly?: boolean
  createdAt?: number
}

export interface AlertInstance {
  id: string
  ruleId: string
  tenantId: string | null
  severity: AlertSeverity
  status: string
  message: string
  metricValue: number
  threshold: number
  firedAt: number
  resolvedAt: number | null
  acknowledgedBy: string | null
}

export type PlatformUserRole = 'USER' | 'ADMIN' | 'ADMIN_MANAGER' | 'ADMIN_DEVELOPER'
export type PlatformAdminScope = 'FULL' | 'MANAGER' | 'DEVELOPER'

export interface PlatformUserSummary {
  id: string
  email: string
  name: string
  role: PlatformUserRole
  adminScope?: PlatformAdminScope | null
  createdAt: string
}

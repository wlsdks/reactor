import { api } from '../../shared/api/client'
import type {
  AlertInstance,
  AlertRule,
  CacheInvalidationResult,
  CreateTenantRequest,
  ModelPricing,
  ModelPricingRequest,
  PlatformUserRole,
  PlatformUserSummary,
  PlatformHealthDashboard,
  Tenant,
} from './types'

function finite(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function enabled(value: unknown): boolean {
  return value === true
}

export const getPlatformHealth = async (): Promise<PlatformHealthDashboard> => {
  const raw = await api.get('admin/platform/health').json<Record<string, unknown>>()
  return {
    pipelineBufferUsage: finite(raw.pipelineBufferUsage),
    pipelineDropRate: finite(raw.pipelineDropRate),
    pipelineWriteLatencyMs: finite(raw.pipelineWriteLatencyMs),
    pipelineMetricsAvailable: enabled(raw.pipelineMetricsAvailable),
    responseCacheEnabled: enabled(raw.responseCacheEnabled),
    activeAlerts: finite(raw.activeAlerts),
    cacheExactHits: finite(raw.cacheExactHits),
    cacheSemanticHits: finite(raw.cacheSemanticHits),
    cacheMisses: finite(raw.cacheMisses),
  }
}

export const listTenants = (): Promise<Tenant[]> =>
  api.get('admin/platform/tenants', { searchParams: { limit: 200 } }).json()

export const getTenant = (id: string): Promise<Tenant> =>
  api.get(`admin/platform/tenants/${encodeURIComponent(id)}`).json()

export const createTenant = (request: CreateTenantRequest): Promise<Tenant> =>
  api.post('admin/platform/tenants', { json: request }).json()

export const suspendTenant = (id: string): Promise<Tenant> =>
  api.post(`admin/platform/tenants/${encodeURIComponent(id)}/suspend`).json()

export const activateTenant = (id: string): Promise<Tenant> =>
  api.post(`admin/platform/tenants/${encodeURIComponent(id)}/activate`).json()

export const listPricing = (): Promise<ModelPricing[]> =>
  api.get('admin/platform/pricing').json()

export const upsertPricing = (pricing: ModelPricingRequest): Promise<ModelPricing> =>
  api.post('admin/platform/pricing', { json: pricing }).json()

export const listAlertRules = (): Promise<AlertRule[]> =>
  api.get('admin/platform/alerts/rules').json()

export const saveAlertRule = (rule: AlertRule): Promise<AlertRule> =>
  api.post('admin/platform/alerts/rules', { json: rule }).json()

export const deleteAlertRule = async (id: string): Promise<void> => {
  await api.delete(`admin/platform/alerts/rules/${encodeURIComponent(id)}`)
}

export const listActiveAlerts = (): Promise<AlertInstance[]> =>
  api.get('admin/platform/alerts').json()

export const resolveAlert = (id: string): Promise<void> =>
  api.post(`admin/platform/alerts/${encodeURIComponent(id)}/resolve`).json()

export const evaluateAlerts = (): Promise<{ status: string }> =>
  api.post('admin/platform/alerts/evaluate').json()

export const invalidateResponseCache = (): Promise<CacheInvalidationResult> =>
  api.post('admin/platform/cache/invalidate').json()

export const getUserByEmail = (email: string): Promise<PlatformUserSummary> =>
  api.get('admin/platform/users/by-email', { searchParams: { email } }).json()

export const updateUserRole = (userId: string, role: PlatformUserRole): Promise<PlatformUserSummary> =>
  api.post(`admin/platform/users/${encodeURIComponent(userId)}/role`, { json: { role } }).json()

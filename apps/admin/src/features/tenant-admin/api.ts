import { api } from '../../shared/api/client'
import type {
  TenantAlertResponse,
  TenantCostResponse,
  TenantExportRangeParams,
  TenantOverviewResponse,
  TenantQualityResponse,
  TenantQuotaResponse,
  TenantSloResponse,
  TenantToolsResponse,
  TenantUsageRangeParams,
  TenantUsageResponse,
} from './types'

function rangeSearchParams(range?: TenantUsageRangeParams): Record<string, string> {
  const params: Record<string, string> = {}
  if (range?.fromMs != null) params.fromMs = String(range.fromMs)
  if (range?.toMs != null) params.toMs = String(range.toMs)
  return params
}

export const getOverview = (tenantId: string, range?: TenantUsageRangeParams): Promise<TenantOverviewResponse> => {
  const searchParams = rangeSearchParams(range)
  return api.get('admin/tenant/overview', {
    headers: { 'X-Tenant-Id': tenantId },
    ...(Object.keys(searchParams).length ? { searchParams } : {}),
  }).json()
}

export const getUsage = (tenantId: string, range?: TenantUsageRangeParams): Promise<TenantUsageResponse> => {
  const searchParams = rangeSearchParams(range)
  return api.get('admin/tenant/usage', {
    headers: { 'X-Tenant-Id': tenantId },
    ...(Object.keys(searchParams).length ? { searchParams } : {}),
  }).json()
}

export const getQuality = (tenantId: string, range?: TenantUsageRangeParams): Promise<TenantQualityResponse> => {
  const searchParams = rangeSearchParams(range)
  return api.get('admin/tenant/quality', {
    headers: { 'X-Tenant-Id': tenantId },
    ...(Object.keys(searchParams).length ? { searchParams } : {}),
  }).json()
}

export const getTools = (tenantId: string, range?: TenantUsageRangeParams): Promise<TenantToolsResponse> => {
  const searchParams = rangeSearchParams(range)
  return api.get('admin/tenant/tools', {
    headers: { 'X-Tenant-Id': tenantId },
    ...(Object.keys(searchParams).length ? { searchParams } : {}),
  }).json()
}

export const getCost = (tenantId: string, range?: TenantUsageRangeParams): Promise<TenantCostResponse> => {
  const searchParams = rangeSearchParams(range)
  return api.get('admin/tenant/cost', {
    headers: { 'X-Tenant-Id': tenantId },
    ...(Object.keys(searchParams).length ? { searchParams } : {}),
  }).json()
}

export const getSlo = (tenantId: string): Promise<TenantSloResponse> =>
  api.get('admin/tenant/slo', { headers: { 'X-Tenant-Id': tenantId } }).json()

export const getTenantAlerts = (tenantId: string): Promise<TenantAlertResponse[]> =>
  api.get('admin/tenant/alerts', { headers: { 'X-Tenant-Id': tenantId }, searchParams: { limit: 200 } }).json()

export const getQuota = (tenantId: string): Promise<TenantQuotaResponse> =>
  api.get('admin/tenant/quota', { headers: { 'X-Tenant-Id': tenantId } }).json()

export const exportExecutionsCsv = async (tenantId: string, range?: TenantExportRangeParams): Promise<string> => {
  const searchParams = rangeSearchParams(range)
  return api.get('admin/tenant/export/executions', {
    headers: { 'X-Tenant-Id': tenantId },
    ...(Object.keys(searchParams).length ? { searchParams } : {}),
  }).text()
}

export const exportToolsCsv = async (tenantId: string, range?: TenantExportRangeParams): Promise<string> => {
  const searchParams = rangeSearchParams(range)
  return api.get('admin/tenant/export/tools', {
    headers: { 'X-Tenant-Id': tenantId },
    ...(Object.keys(searchParams).length ? { searchParams } : {}),
  }).text()
}

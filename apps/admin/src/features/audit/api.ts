import type {
  AuditLogEntry,
  AuditPaginatedResponse,
  AuditRollbackPreview,
  AuditRollbackResult,
} from './types'
import { api } from '../../shared/api/client'

export interface AuditPageQuery {
  category?: string
  action?: string
  offset?: number
  limit?: number
}

export const listAuditPage = async (query: AuditPageQuery): Promise<AuditPaginatedResponse> => {
  const searchParams: Record<string, string> = {
    offset: String(query.offset ?? 0),
    pageLimit: String(query.limit ?? 25),
  }
  if (query.category) searchParams.category = query.category
  if (query.action) searchParams.action = query.action
  const body = await api.get('admin/audits', { searchParams }).json<AuditPaginatedResponse>()
  return {
    items: Array.isArray(body.items) ? body.items : [],
    total: Number.isFinite(body.total) ? body.total : 0,
    offset: Number.isFinite(body.offset) ? body.offset : 0,
    limit: Number.isFinite(body.limit) ? body.limit : query.limit ?? 25,
  }
}

export const listAuditLogs = async (
  limit = 100,
  category?: string,
  action?: string,
): Promise<AuditLogEntry[]> => {
  const searchParams: Record<string, string> = { limit: String(limit) }
  if (category) searchParams.category = category
  if (action) searchParams.action = action
  const body = await api.get('admin/audits', { searchParams }).json<AuditPaginatedResponse | AuditLogEntry[]>()
  return Array.isArray(body) ? body : body.items
}

export const exportAuditLogs = async (): Promise<Blob> => {
  const response = await api.get('admin/audits/export')
  return response.blob()
}

/**
 * Fetch an impact preview for rolling back the given audit entry.
 * A 404 still means the audit row no longer exists or the backend is older than
 * the rollback-boundary contract, so callers keep the unavailable preview state.
 */
export const previewAuditRollback = async (id: string): Promise<AuditRollbackPreview> => {
  return api.get(`admin/audits/${encodeURIComponent(id)}/rollback-preview`).json<AuditRollbackPreview>()
}

/**
 * Request the backend to roll back the given audit entry.
 * The current backend fails closed with 409 unless an automatic rollback
 * executor is explicitly registered for the target audit category.
 */
export const rollbackAuditEntry = async (id: string): Promise<AuditRollbackResult> => {
  return api.post(`admin/audits/${encodeURIComponent(id)}/rollback`).json<AuditRollbackResult>()
}

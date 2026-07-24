export interface AuditLogEntry {
  id: string
  category: string
  action: string
  actor: string
  actorEmail?: string
  resourceType: string | null
  resourceId: string | null
  detail: string | null
  targetEmail?: string
  createdAt: number
}

/**
 * Offset-based paginated response from GET /api/admin/audits.
 * Note: differs from shared PaginatedResponse<T> which uses page-based pagination.
 */
export interface AuditPaginatedResponse {
  items: AuditLogEntry[]
  total: number
  offset: number
  limit: number
}

/**
 * Summary of the effect a rollback would have. The backend is expected to
 * return a human-readable summary, a list of concrete changes that would be
 * applied, and any warnings that should be surfaced before the operator
 * confirms.
 *
 * This schema is defensive: every field is optional because older backends or
 * category-specific preview implementations may return a partial payload.
 */
export interface AuditRollbackPreviewChange {
  field?: string
  from?: unknown
  to?: unknown
  description?: string
}

export interface AuditRollbackPreview {
  summary?: string
  changes?: AuditRollbackPreviewChange[]
  warnings?: string[]
  resourceLabel?: string
}

/**
 * Outcome of a rollback execution. Again defensive — the UI only relies on
 * optional fields so a 2xx with an empty body still shows a success toast.
 */
export interface AuditRollbackResult {
  ok?: boolean
  message?: string
}

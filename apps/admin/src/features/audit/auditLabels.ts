import type { TFunction } from 'i18next'

export interface AuditResourceReference {
  resourceType?: string | null
  resourceId?: string | null
  targetEmail?: string | null
}

const CATEGORY_LABEL_KEYS: Record<string, string> = {
  platform_user: 'auditPage.categoryLabels.platform_user',
  approval: 'auditPage.categoryLabels.approval',
  mcp_server: 'auditPage.categoryLabels.mcp_server',
  mcp_security: 'auditPage.categoryLabels.mcp_security',
  tool_policy: 'auditPage.categoryLabels.tool_policy',
  output_guard: 'auditPage.categoryLabels.output_guard',
  session: 'auditPage.categoryLabels.session',
}

const ACTION_LABEL_KEYS: Record<string, string> = {
  create: 'auditPage.actionLabels.create',
  update: 'auditPage.actionLabels.update',
  delete: 'auditPage.actionLabels.delete',
  approve: 'auditPage.actionLabels.approve',
  reject: 'auditPage.actionLabels.reject',
  disable: 'auditPage.actionLabels.disable',
  role_update: 'auditPage.actionLabels.role_update',
}

const ROLLBACK_LABEL_KEYS: Record<string, string> = {
  ready: 'auditPage.rollbackReadinessLabels.ready',
  warn: 'auditPage.rollbackReadinessLabels.warn',
}

const RESOURCE_LABEL_KEYS: Record<string, string> = {
  user: 'auditPage.resourceLabels.user',
  platform_user: 'auditPage.resourceLabels.platform_user',
  approval: 'auditPage.resourceLabels.approval',
  toolapproval: 'auditPage.resourceLabels.approval',
  mcp_server: 'auditPage.resourceLabels.mcp_server',
  mcpserver: 'auditPage.resourceLabels.mcp_server',
  mcp: 'auditPage.resourceLabels.mcp',
  server: 'auditPage.resourceLabels.mcp_server',
  mcpaccesspolicy: 'auditPage.resourceLabels.mcp_access_policy',
  mcpsecuritypolicy: 'auditPage.resourceLabels.mcp_security_policy',
  tool_policy: 'auditPage.resourceLabels.tool_policy',
  toolpolicy: 'auditPage.resourceLabels.tool_policy',
  policy: 'auditPage.resourceLabels.tool_policy',
  output_guard: 'auditPage.resourceLabels.output_guard',
  rule: 'auditPage.resourceLabels.output_guard',
  session: 'auditPage.resourceLabels.session',
  prompt: 'auditPage.resourceLabels.prompt',
  persona: 'auditPage.resourceLabels.persona',
}

const RESOURCE_IDENTIFIER_LABEL_KEYS: Record<string, string> = {
  atlassian: 'auditPage.resourceNames.atlassian',
  'slack-bot': 'auditPage.resourceNames.slackBot',
  swagger: 'auditPage.resourceNames.apiDocs',
  'github-dev': 'auditPage.resourceNames.githubDevelopment',
  'internal-docs': 'auditPage.resourceNames.internalDocs',
  'legacy-api': 'auditPage.resourceNames.legacyApi',
  global: 'auditPage.resourceNames.allService',
  'workspace-eng': 'auditPage.resourceNames.engineeringWorkspace',
  'workspace-staging': 'auditPage.resourceNames.stagingWorkspace',
}

function resourceNameKey(resourceId: string, resourceType: string | null | undefined): string | undefined {
  const normalizedId = resourceId.trim().toLowerCase()
  const knownResourceName = RESOURCE_IDENTIFIER_LABEL_KEYS[normalizedId]
  if (knownResourceName) return knownResourceName

  if (/^approval[-_]\d+$/.test(normalizedId)) return 'auditPage.resourceNames.approval'

  const normalizedType = resourceType?.toLowerCase()
  if (normalizedType === 'user' || normalizedType === 'platform_user') return 'auditPage.resourceNames.userAccount'
  if (normalizedType === 'session') return 'auditPage.resourceNames.conversationRecord'
  return undefined
}

// Backend codes are traceability data, not primary operator copy. Known values
// use the localized task label; new values receive a safe Korean fallback and
// remain available through the table's technical hover or selected detail.
export function createAuditLabelLocalizers(t: TFunction) {
  const localize = (raw: string | null | undefined, labels: Record<string, string>, unknownKey: string): string => {
    const key = raw ? labels[raw.toLowerCase()] : undefined
    return t(key ?? unknownKey)
  }

  const localizeCategory = (raw: string | null | undefined): string => {
    return localize(raw, CATEGORY_LABEL_KEYS, 'auditPage.categoryLabels.unknown')
  }
  const localizeAction = (raw: string | null | undefined): string => {
    return localize(raw, ACTION_LABEL_KEYS, 'auditPage.actionLabels.unknown')
  }
  const localizeRollbackReadiness = (raw: string | null | undefined): string => {
    return localize(raw, ROLLBACK_LABEL_KEYS, 'auditPage.rollbackReadinessLabels.unknown')
  }
  const localizeResource = ({ resourceType, resourceId, targetEmail }: AuditResourceReference): string => {
    if (targetEmail?.trim()) return targetEmail
    const resourceTypeLabel = localize(resourceType, RESOURCE_LABEL_KEYS, 'auditPage.resourceLabels.unknown')
    const nameKey = resourceId?.trim() ? resourceNameKey(resourceId, resourceType) : undefined
    if (!nameKey) return resourceTypeLabel

    return nameKey === 'auditPage.resourceNames.approval'
      ? t(nameKey, { number: resourceId?.trim().match(/\d+$/)?.[0] ?? '' })
      : t(nameKey)
  }

  return { localizeCategory, localizeAction, localizeRollbackReadiness, localizeResource }
}

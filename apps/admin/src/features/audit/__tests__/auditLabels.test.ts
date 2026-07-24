import type { TFunction } from 'i18next'
import { describe, expect, it } from 'vitest'
import { createAuditLabelLocalizers } from '../auditLabels'

const labels: Record<string, string> = {
  'auditPage.resourceLabels.mcp_server': 'External tool',
  'auditPage.resourceLabels.approval': 'Approval request',
  'auditPage.resourceLabels.tool_policy': 'Tool permission',
  'auditPage.resourceLabels.unknown': 'Changed item',
  'auditPage.resourceNames.atlassian': 'Atlassian',
  'auditPage.resourceNames.allService': 'All service',
  'auditPage.resourceNames.approval': 'Approval {{number}}',
}

const translate = ((key: string, options?: Record<string, string>) => {
  const template = labels[key] ?? key
  return options?.number ? template.replace('{{number}}', options.number) : template
}) as unknown as TFunction

describe('createAuditLabelLocalizers', () => {
  it('shows a friendly resource name instead of a backend identifier', () => {
    const { localizeResource } = createAuditLabelLocalizers(translate)

    expect(localizeResource({ resourceType: 'McpServer', resourceId: 'atlassian' }))
      .toBe('Atlassian')
    expect(localizeResource({ resourceType: 'ToolApproval', resourceId: 'approval-7' }))
      .toBe('Approval 7')
  })

  it('does not leak an unknown backend identifier into primary copy', () => {
    const { localizeResource } = createAuditLabelLocalizers(translate)

    expect(localizeResource({ resourceType: 'job', resourceId: 'queue_recovery_v2' }))
      .toBe('Changed item')
  })
})

import { describe, expect, it } from 'vitest'
import { buildMcpServerDraft, detectMcpServerKind, formatDraftConfig } from '../presets'

describe('mcp server presets', () => {
  it('builds the atlassian preset with admin proxy fields', () => {
    const draft = buildMcpServerDraft('atlassian')

    expect(draft.name).toBe('atlassian')
    expect(draft.transportType).toBe('STREAMABLE_HTTP')
    expect(draft.config).toMatchObject({
      url: 'http://localhost:8085/mcp',
      adminUrl: 'http://localhost:8085',
      adminToken: '<set-admin-token>',
      adminHmacRequired: true,
    })
  })

  it('formats config as stable json', () => {
    expect(formatDraftConfig({ url: 'http://localhost:8081/sse' })).toContain('"url": "http://localhost:8081/sse"')
  })

  it('detects server kind from tool families', () => {
    expect(detectMcpServerKind({ name: 'ops', tools: ['jira_search_issues'] })).toBe('atlassian')
    expect(detectMcpServerKind({ name: 'catalog', tools: ['spec_list'] })).toBe('swagger')
    expect(detectMcpServerKind({ name: 'custom-server', tools: ['weather'] })).toBe('generic')
  })
})

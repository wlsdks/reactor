import type { McpServerDetailResponse, McpServerResponse } from './types'

export type KnownMcpServerKind = 'generic' | 'atlassian' | 'swagger'

export interface McpServerDraft {
  name: string
  transportType: string
  config: Record<string, unknown>
}

export const KNOWN_MCP_SERVER_PRESETS: KnownMcpServerKind[] = ['atlassian', 'swagger', 'generic']

const MCP_ENV = import.meta.env as Record<string, unknown>

function envValue(key: string, fallback: string): string {
  const value = MCP_ENV[key]
  return typeof value === 'string' && value.trim() ? value : fallback
}

function preferredEnv(primary: string, legacy: string, fallback: string): string {
  const primaryValue = MCP_ENV[primary]
  if (typeof primaryValue === 'string' && primaryValue.trim()) return primaryValue
  return envValue(legacy, fallback)
}

const ATLASSIAN_NAME = envValue('VITE_ATLASSIAN_MCP_NAME', 'atlassian')
function streamableUrl(value: string): string {
  return value.replace(/\/sse\/?$/, '/mcp')
}

const ATLASSIAN_MCP_URL = streamableUrl(preferredEnv(
  'VITE_ATLASSIAN_MCP_URL',
  'VITE_ATLASSIAN_MCP_SSE_URL',
  'http://localhost:8085/mcp',
))
const ATLASSIAN_ADMIN_URL = envValue('VITE_ATLASSIAN_MCP_ADMIN_URL', 'http://localhost:8085')

const SWAGGER_NAME = envValue('VITE_SWAGGER_MCP_NAME', 'swagger')
const SWAGGER_MCP_URL = streamableUrl(preferredEnv(
  'VITE_SWAGGER_MCP_URL',
  'VITE_SWAGGER_MCP_SSE_URL',
  'http://localhost:8081/mcp',
))
const SWAGGER_ADMIN_URL = envValue('VITE_SWAGGER_MCP_ADMIN_URL', 'http://localhost:8081')

export function formatDraftConfig(config: Record<string, unknown>): string {
  return JSON.stringify(config, null, 2)
}

function baseAdminConfig(url: string, adminUrl: string): Record<string, unknown> {
  return {
    url,
    adminUrl,
    adminToken: '<set-admin-token>',
    adminHmacRequired: true,
    adminHmacSecret: '<set-admin-hmac-secret>',
    adminTimeoutMs: 5000,
    adminConnectTimeoutMs: 2000,
  }
}

export function buildMcpServerDraft(kind: KnownMcpServerKind): McpServerDraft {
  if (kind === 'atlassian') {
    return {
      name: ATLASSIAN_NAME,
      transportType: 'STREAMABLE_HTTP',
      config: baseAdminConfig(ATLASSIAN_MCP_URL, ATLASSIAN_ADMIN_URL),
    }
  }

  if (kind === 'swagger') {
    return {
      name: SWAGGER_NAME,
      transportType: 'STREAMABLE_HTTP',
      config: baseAdminConfig(SWAGGER_MCP_URL, SWAGGER_ADMIN_URL),
    }
  }

  return {
    name: '',
    transportType: 'STREAMABLE_HTTP',
    config: { url: 'http://localhost:8081/mcp' },
  }
}

export function detectMcpServerKind(
  server: Pick<McpServerResponse | McpServerDetailResponse, 'name'> & { tools?: string[] },
): KnownMcpServerKind {
  const name = server.name.toLowerCase()
  const tools = server.tools ?? []

  if (
    name.includes('atlassian') ||
    tools.some((tool) => (
      tool.startsWith('jira_') ||
      tool.startsWith('confluence_') ||
      tool.startsWith('bitbucket_') ||
      tool.startsWith('work_')
    ))
  ) {
    return 'atlassian'
  }

  if (
    name.includes('swagger') ||
    tools.some((tool) => tool.startsWith('spec_') || tool.startsWith('swagger_') || tool.startsWith('catalog_'))
  ) {
    return 'swagger'
  }

  return 'generic'
}

export function createPresetDraft(kind: KnownMcpServerKind): McpServerDraft {
  return buildMcpServerDraft(kind)
}

export function detectKnownMcpServerKind(
  server: Pick<McpServerResponse | McpServerDetailResponse, 'name'> & { tools?: string[] },
): KnownMcpServerKind {
  return detectMcpServerKind(server)
}

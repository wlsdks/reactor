type Translate = (key: string) => string

const KNOWN_SERVER_NAMES: Record<string, string> = {
  atlassian: 'Atlassian',
  'slack-bot': 'Slack Bot',
  swagger: 'API 문서 도구',
  'github-dev': 'GitHub 개발 도구',
  'internal-docs': '내부 문서 도구',
  'legacy-api': '이전 API 도구',
}

const KNOWN_SERVER_DESCRIPTIONS: Record<string, { pattern: RegExp; label: string }> = {
  atlassian: {
    pattern: /^atlassian mcp server\b/i,
    label: 'Jira, Confluence, Bitbucket 업무 도구를 연결합니다.',
  },
  swagger: {
    pattern: /^swagger mcp server\b/i,
    label: 'API 문서를 연결해 필요한 정보를 찾고 확인합니다.',
  },
}

const WORD_LABELS: Record<string, string> = {
  ai: 'AI',
  api: 'API',
  github: 'GitHub',
  jira: 'Jira',
  mcp: 'MCP',
  slack: 'Slack',
}

export function displayMcpServerName(name: string): string {
  const normalized = name.trim().toLowerCase()
  if (!normalized) return ''
  if (KNOWN_SERVER_NAMES[normalized]) return KNOWN_SERVER_NAMES[normalized]

  if (!/^[a-z0-9_-]+$/.test(normalized)) return name
  return normalized
    .split(/[_-]+/)
    .filter(Boolean)
    .map((word) => WORD_LABELS[word] ?? `${word[0]?.toUpperCase() ?? ''}${word.slice(1)}`)
    .join(' ')
}

export function displayMcpServerDescription(name: string, description: string): string {
  const knownDescription = KNOWN_SERVER_DESCRIPTIONS[name.trim().toLowerCase()]
  if (knownDescription?.pattern.test(description.trim())) return knownDescription.label
  return description
}

export function localizeMcpConnectionStatus(status: string, t: Translate): string {
  switch (status.toUpperCase()) {
    case 'CONNECTED':
      return t('mcpServersPage.connectionStatus.connected')
    case 'DISCONNECTED':
      return t('mcpServersPage.connectionStatus.disconnected')
    case 'FAILED':
    case 'ERROR':
      return t('mcpServersPage.connectionStatus.failed')
    case 'RETRYING':
    case 'PENDING':
      return t('mcpServersPage.connectionStatus.retrying')
    default:
      return t('mcpServersPage.connectionStatus.unknown')
  }
}

export function localizeMcpTransport(transport: string, t: Translate): string {
  switch (transport.toUpperCase()) {
    case 'STREAMABLE':
    case 'STREAMABLE_HTTP':
      return t('mcpServersPage.transport.streamable')
    case 'STDIO':
      return t('mcpServersPage.transport.stdio')
    case 'HTTP':
      return t('mcpServersPage.transport.http')
    case 'SSE':
      return t('mcpServersPage.transport.sse')
    default:
      return t('mcpServersPage.transport.unknown')
  }
}

export function localizeMcpRuntimeStatus(status: string | null | undefined, t: Translate): string {
  switch (status?.toLowerCase()) {
    case 'healthy':
    case 'ready':
      return t('mcpServers.detail.runtimeStatus.healthy')
    case 'disabled':
    case 'disconnected':
      return t('mcpServers.detail.runtimeStatus.inactive')
    case 'degraded':
    case 'failed':
    case 'error':
      return t('mcpServers.detail.runtimeStatus.attention')
    default:
      return t('mcpServers.detail.runtimeStatus.unknown')
  }
}

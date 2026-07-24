import type {
  McpServerResponse,
  McpServerDetailResponse,
  RegisterMcpServerRequest,
  UpdateMcpServerRequest,
  McpConnectResponse,
  McpAccessPolicy,
  McpPreflightResponse,
  SwaggerSpecSource,
  SwaggerSpecSourceRequest,
  SwaggerSpecSourceUpdateRequest,
  SwaggerSpecRevision,
  SwaggerDiffSummary,
  SwaggerSpecSyncResult,
  SwaggerSpecPublishResult,
} from './types'
import { api } from '../../shared/api/client'
import {
  parsePolicy,
  parsePreflight,
  parseSwaggerSource,
  parseSwaggerDiffSummary,
  parseSwaggerRevision,
} from './parsers'

type BackendMcpServer = {
  server_id?: unknown
  tenant_id?: unknown
  name?: unknown
  transport?: unknown
  status?: unknown
  command?: unknown
  url?: unknown
  auth_type?: unknown
  timeout_ms?: unknown
  args?: unknown
  reconnect_policy?: unknown
  protocol_version?: unknown
  last_connection_error?: unknown
  tool_snapshot_hash?: unknown
  created_at?: unknown
  updated_at?: unknown
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function optionalText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function normalizeStatus(value: unknown): string {
  switch (text(value).toLowerCase()) {
    case 'healthy': return 'CONNECTED'
    case 'degraded': return 'FAILED'
    case 'registered':
    case 'disabled': return 'DISCONNECTED'
    default: return text(value).toUpperCase() || 'PENDING'
  }
}

function timestamp(value: unknown): number {
  if (typeof value !== 'string') return 0
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : 0
}

export function parseMcpServer(data: unknown): McpServerResponse {
  const row = (data && typeof data === 'object' ? data : {}) as BackendMcpServer
  const backendStatus = text(row.status)
  return {
    id: text(row.server_id),
    tenantId: text(row.tenant_id),
    name: text(row.name),
    description: null,
    transportType: text(row.transport),
    autoConnect: false,
    status: normalizeStatus(row.status),
    backendStatus,
    command: optionalText(row.command),
    url: optionalText(row.url),
    authType: text(row.auth_type) || 'none',
    timeoutMs: typeof row.timeout_ms === 'number' ? row.timeout_ms : 15_000,
    protocolVersion: optionalText(row.protocol_version),
    lastConnectionError: optionalText(row.last_connection_error),
    toolSnapshotHash: optionalText(row.tool_snapshot_hash),
    toolCount: 0,
    createdAt: timestamp(row.created_at),
    updatedAt: timestamp(row.updated_at),
  }
}

export function parseMcpServerDetail(data: unknown): McpServerDetailResponse {
  const server = parseMcpServer(data)
  const row = (data && typeof data === 'object' ? data : {}) as BackendMcpServer
  const reconnectPolicy = row.reconnect_policy && typeof row.reconnect_policy === 'object'
    ? row.reconnect_policy as Record<string, unknown>
    : {}
  return {
    ...server,
    config: {
      command: server.command,
      url: server.url,
      authType: server.authType,
      timeoutMs: server.timeoutMs,
      args: Array.isArray(row.args) ? row.args.map(String) : [],
      ...reconnectPolicy,
    },
    version: null,
    tools: [],
  }
}

function backendTransport(transport: string): string {
  return transport.toUpperCase() === 'STDIO' ? 'stdio' : 'streamable_http'
}

function backendRequest(request: RegisterMcpServerRequest | UpdateMcpServerRequest) {
  const config = request.config ?? {}
  const transport = request.transportType ? backendTransport(request.transportType) : undefined
  return {
    ...(transport ? { transport } : {}),
    command: optionalText(config.command),
    args: Array.isArray(config.args) ? config.args.map(String) : [],
    url: optionalText(config.url),
    authType: optionalText(config.authType) ?? 'none',
    timeoutMs: typeof config.timeoutMs === 'number' ? config.timeoutMs : 15_000,
    reconnectPolicy: config,
  }
}

export const listMcpServers = async (): Promise<McpServerResponse[]> => {
  const data = await api.get('mcp/servers', { searchParams: { limit: 200 } }).json()
  return Array.isArray(data) ? data.map(parseMcpServer) : []
}

export const getMcpServer = async (name: string): Promise<McpServerDetailResponse> =>
  parseMcpServerDetail(await api.get(`mcp/servers/${encodeURIComponent(name)}`).json())

export const registerMcpServer = async (request: RegisterMcpServerRequest): Promise<McpServerResponse> =>
  parseMcpServer(await api.post('mcp/servers', {
    json: { name: request.name, ...backendRequest(request) },
  }).json())

export const updateMcpServer = async (name: string, request: UpdateMcpServerRequest): Promise<McpServerResponse> =>
  parseMcpServer(await api.put(`mcp/servers/${encodeURIComponent(name)}`, {
    json: backendRequest(request),
  }).json())

export const deleteMcpServer = (name: string): Promise<void> =>
  api.delete(`mcp/servers/${encodeURIComponent(name)}`).json()

export const connectMcpServer = async (name: string): Promise<McpConnectResponse> => {
  const server = parseMcpServer(await api.post(`mcp/servers/${encodeURIComponent(name)}/connect`).json())
  return { status: server.status }
}

export const disconnectMcpServer = (name: string): Promise<void> =>
  api.post(`mcp/servers/${encodeURIComponent(name)}/disconnect`).json()

export const emergencyDenyAll = (name: string): Promise<void> =>
  api.post(`mcp/servers/${encodeURIComponent(name)}/access-policy/emergency-deny-all`).json()

export const getMcpAccessPolicy = async (name: string): Promise<McpAccessPolicy> => {
  const data = await api.get(`mcp/servers/${encodeURIComponent(name)}/access-policy`).json()
  return parsePolicy(data)
}

export const updateMcpAccessPolicy = async (name: string, request: McpAccessPolicy): Promise<McpAccessPolicy> => {
  const data = await api.put(`mcp/servers/${encodeURIComponent(name)}/access-policy`, { json: request }).json()
  return parsePolicy(data)
}

export const clearMcpAccessPolicy = (name: string): Promise<void> =>
  api.delete(`mcp/servers/${encodeURIComponent(name)}/access-policy`).json()

export const getMcpPreflight = async (name: string): Promise<McpPreflightResponse | null> => {
  const response = await api.get(`mcp/servers/${encodeURIComponent(name)}/preflight`)
  if (response.status === 204) return null
  const data = await response.json()
  return parsePreflight(data)
}

export const listSwaggerSpecSources = async (serverName: string): Promise<SwaggerSpecSource[]> => {
  const data = await api.get(`mcp/servers/${encodeURIComponent(serverName)}/swagger/sources`, { searchParams: { limit: 200 } }).json()
  return Array.isArray(data) ? data.map(parseSwaggerSource) : []
}

export const getSwaggerSpecSource = async (serverName: string, sourceName: string): Promise<SwaggerSpecSource> => {
  const data = await api.get(
    `mcp/servers/${encodeURIComponent(serverName)}/swagger/sources/${encodeURIComponent(sourceName)}`,
  ).json()
  return parseSwaggerSource(data)
}

export const createSwaggerSpecSource = async (
  serverName: string,
  request: SwaggerSpecSourceRequest,
): Promise<SwaggerSpecSource> => {
  const data = await api.post(
    `mcp/servers/${encodeURIComponent(serverName)}/swagger/sources`,
    { json: request },
  ).json()
  return parseSwaggerSource(data)
}

export const updateSwaggerSpecSource = async (
  serverName: string,
  sourceName: string,
  request: SwaggerSpecSourceUpdateRequest,
): Promise<SwaggerSpecSource> => {
  const data = await api.put(
    `mcp/servers/${encodeURIComponent(serverName)}/swagger/sources/${encodeURIComponent(sourceName)}`,
    { json: request },
  ).json()
  return parseSwaggerSource(data)
}

export const syncSwaggerSpecSource = async (serverName: string, sourceName: string): Promise<SwaggerSpecSyncResult> => {
  const row = await api.post(
    `mcp/servers/${encodeURIComponent(serverName)}/swagger/sources/${encodeURIComponent(sourceName)}/sync`,
  ).json<Partial<SwaggerSpecSyncResult>>()
  return {
    sourceName: typeof row.sourceName === 'string' ? row.sourceName : sourceName,
    status: typeof row.status === 'string' ? row.status : '',
    changed: row.changed === true,
    revisionId: typeof row.revisionId === 'string' ? row.revisionId : null,
    reviewStatus: typeof row.reviewStatus === 'string' ? row.reviewStatus : null,
    message: typeof row.message === 'string' ? row.message : '',
    diffSummary: row.diffSummary ? parseSwaggerDiffSummary(row.diffSummary) : null,
    syncedAt: typeof row.syncedAt === 'string' ? row.syncedAt : undefined,
  }
}

export const listSwaggerSpecRevisions = async (serverName: string, sourceName: string): Promise<SwaggerSpecRevision[]> => {
  const data = await api.get(
    `mcp/servers/${encodeURIComponent(serverName)}/swagger/sources/${encodeURIComponent(sourceName)}/revisions`,
    { searchParams: { limit: 200 } },
  ).json()
  return Array.isArray(data) ? data.map(parseSwaggerRevision) : []
}

export const getSwaggerSpecDiff = async (
  serverName: string,
  sourceName: string,
  fromRevisionId: string,
  toRevisionId: string,
): Promise<SwaggerDiffSummary> => {
  const data = await api.get(
    `mcp/servers/${encodeURIComponent(serverName)}/swagger/sources/${encodeURIComponent(sourceName)}/diff`,
    { searchParams: { from: fromRevisionId, to: toRevisionId } },
  ).json()
  return parseSwaggerDiffSummary(data)
}

export const publishSwaggerSpecRevision = async (
  serverName: string,
  sourceName: string,
  revisionId: string,
): Promise<SwaggerSpecPublishResult> => {
  const row = await api.post(
    `mcp/servers/${encodeURIComponent(serverName)}/swagger/sources/${encodeURIComponent(sourceName)}/publish`,
    { json: { revisionId } },
  ).json<Partial<SwaggerSpecPublishResult>>()
  return {
    sourceName: typeof row.sourceName === 'string' ? row.sourceName : sourceName,
    revisionId: typeof row.revisionId === 'string' ? row.revisionId : revisionId,
    publishedAt: typeof row.publishedAt === 'string' ? row.publishedAt : '',
    summary: row.summary && typeof row.summary === 'object'
      ? {
          title: typeof row.summary.title === 'string' ? row.summary.title : null,
          version: typeof row.summary.version === 'string' ? row.summary.version : null,
          description: typeof row.summary.description === 'string' ? row.summary.description : null,
          servers: Array.isArray(row.summary.servers) ? row.summary.servers.map(String) : [],
          tags: Array.isArray(row.summary.tags) ? row.summary.tags.map(String) : [],
          endpointCount: Number(row.summary.endpointCount ?? 0),
          schemaCount: Number(row.summary.schemaCount ?? 0),
          securitySchemeNames: Array.isArray(row.summary.securitySchemeNames)
            ? row.summary.securitySchemeNames.map(String)
            : [],
        }
      : {
          title: null,
          version: null,
          description: null,
          servers: [],
          tags: [],
          endpointCount: 0,
          schemaCount: 0,
          securitySchemeNames: [],
        },
  }
}

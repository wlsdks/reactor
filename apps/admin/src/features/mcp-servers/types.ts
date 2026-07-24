export type OperatorStatus = 'PASS' | 'WARN' | 'FAIL'

export interface McpServerResponse {
  id: string
  tenantId: string
  name: string
  description: string | null
  transportType: string
  autoConnect: boolean
  status: string
  backendStatus: string
  command: string | null
  url: string | null
  authType: string
  timeoutMs: number
  protocolVersion: string | null
  lastConnectionError: string | null
  toolSnapshotHash: string | null
  toolCount: number
  createdAt: number
  updatedAt: number
}

export interface McpServerDetailResponse {
  id: string
  tenantId: string
  name: string
  description: string | null
  transportType: string
  config: Record<string, unknown>
  version: string | null
  autoConnect: boolean
  status: string
  backendStatus: string
  command: string | null
  url: string | null
  authType: string
  timeoutMs: number
  protocolVersion: string | null
  lastConnectionError: string | null
  toolSnapshotHash: string | null
  tools: string[]
  createdAt: number
  updatedAt: number
}

export interface RegisterMcpServerRequest {
  name: string
  transportType: string
  config: Record<string, unknown>
}

export interface UpdateMcpServerRequest {
  transportType?: string
  config?: Record<string, unknown>
}

export interface McpConnectResponse {
  status: string
  tools?: string[]
  error?: string
}

export interface McpAccessPolicySnapshot {
  allowedJiraProjectKeys: string[]
  allowedConfluenceSpaceKeys: string[]
  allowedBitbucketRepositories: string[]
  allowedSourceNames: string[]
  allowPreviewReads: boolean
  allowPreviewWrites: boolean
  allowDirectUrlLoads: boolean
  publishedOnly: boolean
}

export interface McpAccessPolicy extends McpAccessPolicySnapshot {
  policySource?: string
  dynamicEnabled?: boolean
  dynamicPolicy?: McpAccessPolicySnapshot | null
}

export interface SwaggerSpecSource {
  id: string
  name: string
  url: string
  enabled: boolean
  syncCron: string
  jiraProjectKey: string | null
  confluenceSpaceKey: string | null
  bitbucketRepository: string | null
  serviceSlug: string | null
  ownerTeam: string | null
  publishedRevisionId: string | null
  etag: string | null
  lastModified: string | null
  lastSyncStatus: string | null
  lastSyncMessage: string | null
  lastSyncAt: string | null
  createdAt: string
  updatedAt: string
}

export interface SwaggerParsedSpecSummary {
  title: string | null
  version: string | null
  description: string | null
  servers: string[]
  tags: string[]
  endpointCount: number
  schemaCount: number
  securitySchemeNames: string[]
}

export interface SwaggerDiffSummary {
  endpointsAdded: string[]
  endpointsRemoved: string[]
  endpointsChanged: string[]
  schemasAdded: string[]
  schemasRemoved: string[]
  schemasChanged: string[]
  securityChanged: boolean
}

export interface SwaggerSpecRevision {
  id: string
  sourceId: string
  contentHash: string
  rawContent?: string
  parsedSummary: SwaggerParsedSpecSummary
  diffSummary: SwaggerDiffSummary | null
  reviewStatus: string
  fetchedAt: string
  createdAt: string
  updatedAt: string
}

export interface SwaggerSpecSourceRequest {
  name: string
  url: string
  enabled?: boolean
  syncCron?: string | null
  jiraProjectKey?: string | null
  confluenceSpaceKey?: string | null
  bitbucketRepository?: string | null
  serviceSlug?: string | null
  ownerTeam?: string | null
}

export interface SwaggerSpecSourceUpdateRequest {
  url?: string | null
  enabled?: boolean | null
  syncCron?: string | null
  jiraProjectKey?: string | null
  confluenceSpaceKey?: string | null
  bitbucketRepository?: string | null
  serviceSlug?: string | null
  ownerTeam?: string | null
}

export interface SwaggerSpecSyncResult {
  sourceName: string
  status: string
  changed: boolean
  revisionId?: string | null
  reviewStatus?: string | null
  message: string
  diffSummary?: SwaggerDiffSummary | null
  syncedAt?: string
}

export interface SwaggerSpecPublishResult {
  sourceName: string
  revisionId: string
  publishedAt: string
  summary: SwaggerParsedSpecSummary
}

export interface McpPreflightCheck {
  name: string
  status: string
  message: string
  details?: Record<string, unknown>
}

export interface McpPreflightRateBudgetService {
  service: string
  configuredRequestsPerSecond: number
  requestTotal: number
  retryTotal: number
  status429Total: number
  attention: boolean
}

export interface McpPreflightRateBudget {
  observedWindow: string
  services: McpPreflightRateBudgetService[]
  summary: {
    configuredRequestsPerSecond: number
    attentionServices: number
    rateLimitedServices: number
  }
}

export interface McpPreflightResponse {
  ok: boolean
  readyForProduction: boolean
  policySource: string
  checkedAt: string
  kind?: 'operational' | 'generic'
  summary: {
    passCount: number
    warnCount: number
    failCount: number
  }
  rateBudget?: McpPreflightRateBudget
  checks: McpPreflightCheck[]
}

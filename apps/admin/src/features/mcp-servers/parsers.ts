import i18n from 'i18next'
import type {
  McpAccessPolicy,
  McpAccessPolicySnapshot,
  McpPreflightResponse,
  SwaggerSpecSource,
  SwaggerDiffSummary,
  SwaggerSpecRevision,
} from './types'

const emptyPolicySnapshot: McpAccessPolicySnapshot = {
  allowedJiraProjectKeys: [],
  allowedConfluenceSpaceKeys: [],
  allowedBitbucketRepositories: [],
  allowedSourceNames: [],
  allowPreviewReads: false,
  allowPreviewWrites: false,
  allowDirectUrlLoads: false,
  publishedOnly: true,
}

export function parsePolicySnapshot(data: unknown): McpAccessPolicySnapshot {
  const row = data && typeof data === 'object' ? data as Partial<McpAccessPolicySnapshot> : {}

  return {
    allowedJiraProjectKeys: Array.isArray(row.allowedJiraProjectKeys) ? row.allowedJiraProjectKeys.map(String) : [],
    allowedConfluenceSpaceKeys: Array.isArray(row.allowedConfluenceSpaceKeys)
      ? row.allowedConfluenceSpaceKeys.map(String)
      : [],
    allowedBitbucketRepositories: Array.isArray(row.allowedBitbucketRepositories)
      ? row.allowedBitbucketRepositories.map(String)
      : [],
    allowedSourceNames: Array.isArray(row.allowedSourceNames) ? row.allowedSourceNames.map(String) : [],
    allowPreviewReads: row.allowPreviewReads === true,
    allowPreviewWrites: row.allowPreviewWrites === true,
    allowDirectUrlLoads: row.allowDirectUrlLoads === true,
    publishedOnly: row.publishedOnly !== false,
  }
}

export function parsePolicy(data: unknown): McpAccessPolicy {
  if (!data || typeof data !== 'object') {
    return {
      ...emptyPolicySnapshot,
      policySource: 'unknown',
      dynamicEnabled: false,
      dynamicPolicy: null,
    }
  }

  const row = data as Partial<McpAccessPolicy> & { dynamicPolicy?: unknown }
  const dynamicPolicy = row.dynamicPolicy == null ? null : parsePolicySnapshot(row.dynamicPolicy)

  return {
    ...parsePolicySnapshot(row),
    policySource: typeof row.policySource === 'string' ? row.policySource : 'unknown',
    dynamicEnabled: typeof row.dynamicEnabled === 'boolean' ? row.dynamicEnabled : false,
    dynamicPolicy,
  }
}

export function parsePreflight(data: unknown): McpPreflightResponse {
  if (!data || typeof data !== 'object') {
    throw new Error(i18n.t('mcpServers.invalidPreflightResponse'))
  }

  const row = data as Partial<McpPreflightResponse> & Record<string, unknown>
  if (typeof row.status === 'string') {
    const ok = row.status.toLowerCase() === 'ok'
    const checkedAt = typeof row.timestamp === 'string' ? row.timestamp : ''
    return {
      ok,
      readyForProduction: ok,
      policySource: 'server',
      checkedAt,
      kind: 'generic',
      summary: {
        passCount: ok ? 1 : 0,
        warnCount: 0,
        failCount: ok ? 0 : 1,
      },
      checks: [
        {
          name: 'server_preflight',
          status: ok ? 'PASS' : 'FAIL',
          message: ok ? 'Server preflight completed successfully.' : 'Server preflight reported a failure.',
          details: row,
        },
      ],
    }
  }

  return {
    ok: row.ok === true,
    readyForProduction: row.readyForProduction === true,
    policySource: typeof row.policySource === 'string' ? row.policySource : 'unknown',
    checkedAt: typeof row.checkedAt === 'string' ? row.checkedAt : '',
    kind: 'operational',
    summary: {
      passCount: Number(row.summary?.passCount ?? 0),
      warnCount: Number(row.summary?.warnCount ?? 0),
      failCount: Number(row.summary?.failCount ?? 0),
    },
    rateBudget: row.rateBudget && typeof row.rateBudget === 'object'
      ? {
          observedWindow: typeof row.rateBudget.observedWindow === 'string'
            ? row.rateBudget.observedWindow
            : 'unknown',
          services: Array.isArray(row.rateBudget.services)
            ? row.rateBudget.services.map((item) => {
                const service = (item && typeof item === 'object' ? item : {}) as Record<string, unknown>
                return {
                  service: typeof service.service === 'string' ? service.service : 'unknown',
                  configuredRequestsPerSecond: Number(service.configuredRequestsPerSecond ?? 0),
                  requestTotal: Number(service.requestTotal ?? 0),
                  retryTotal: Number(service.retryTotal ?? 0),
                  status429Total: Number(service.status429Total ?? 0),
                  attention: service.attention === true,
                }
              })
            : [],
          summary: {
            configuredRequestsPerSecond: Number(row.rateBudget.summary?.configuredRequestsPerSecond ?? 0),
            attentionServices: Number(row.rateBudget.summary?.attentionServices ?? 0),
            rateLimitedServices: Number(row.rateBudget.summary?.rateLimitedServices ?? 0),
          },
        }
      : undefined,
    checks: Array.isArray(row.checks)
      ? row.checks.map((item) => {
          const check = (item && typeof item === 'object' ? item : {}) as Record<string, unknown>
          return {
            name: typeof check.name === 'string' ? check.name : 'unknown',
            status: typeof check.status === 'string' ? check.status : 'WARN',
            message: typeof check.message === 'string' ? check.message : '',
            details: check.details && typeof check.details === 'object'
              ? check.details as Record<string, unknown>
              : undefined,
          }
        })
      : [],
  }
}

export function parseSwaggerSource(data: unknown): SwaggerSpecSource {
  const row = (data && typeof data === 'object' ? data : {}) as Partial<SwaggerSpecSource>
  return {
    id: typeof row.id === 'string' ? row.id : '',
    name: typeof row.name === 'string' ? row.name : '',
    url: typeof row.url === 'string' ? row.url : '',
    enabled: row.enabled !== false,
    syncCron: typeof row.syncCron === 'string' ? row.syncCron : '',
    jiraProjectKey: typeof row.jiraProjectKey === 'string' ? row.jiraProjectKey : null,
    confluenceSpaceKey: typeof row.confluenceSpaceKey === 'string' ? row.confluenceSpaceKey : null,
    bitbucketRepository: typeof row.bitbucketRepository === 'string' ? row.bitbucketRepository : null,
    serviceSlug: typeof row.serviceSlug === 'string' ? row.serviceSlug : null,
    ownerTeam: typeof row.ownerTeam === 'string' ? row.ownerTeam : null,
    publishedRevisionId: typeof row.publishedRevisionId === 'string' ? row.publishedRevisionId : null,
    etag: typeof row.etag === 'string' ? row.etag : null,
    lastModified: typeof row.lastModified === 'string' ? row.lastModified : null,
    lastSyncStatus: typeof row.lastSyncStatus === 'string' ? row.lastSyncStatus : null,
    lastSyncMessage: typeof row.lastSyncMessage === 'string' ? row.lastSyncMessage : null,
    lastSyncAt: typeof row.lastSyncAt === 'string' ? row.lastSyncAt : null,
    createdAt: typeof row.createdAt === 'string' ? row.createdAt : '',
    updatedAt: typeof row.updatedAt === 'string' ? row.updatedAt : '',
  }
}

export function parseSwaggerDiffSummary(data: unknown): SwaggerDiffSummary {
  const row = (data && typeof data === 'object' ? data : {}) as Partial<SwaggerDiffSummary>
  return {
    endpointsAdded: Array.isArray(row.endpointsAdded) ? row.endpointsAdded.map(String) : [],
    endpointsRemoved: Array.isArray(row.endpointsRemoved) ? row.endpointsRemoved.map(String) : [],
    endpointsChanged: Array.isArray(row.endpointsChanged) ? row.endpointsChanged.map(String) : [],
    schemasAdded: Array.isArray(row.schemasAdded) ? row.schemasAdded.map(String) : [],
    schemasRemoved: Array.isArray(row.schemasRemoved) ? row.schemasRemoved.map(String) : [],
    schemasChanged: Array.isArray(row.schemasChanged) ? row.schemasChanged.map(String) : [],
    securityChanged: row.securityChanged === true,
  }
}

export function parseSwaggerRevision(data: unknown): SwaggerSpecRevision {
  const row = (data && typeof data === 'object' ? data : {}) as Partial<SwaggerSpecRevision>
  return {
    id: typeof row.id === 'string' ? row.id : '',
    sourceId: typeof row.sourceId === 'string' ? row.sourceId : '',
    contentHash: typeof row.contentHash === 'string' ? row.contentHash : '',
    rawContent: typeof row.rawContent === 'string' ? row.rawContent : undefined,
    parsedSummary: row.parsedSummary && typeof row.parsedSummary === 'object'
      ? {
          title: typeof row.parsedSummary.title === 'string' ? row.parsedSummary.title : null,
          version: typeof row.parsedSummary.version === 'string' ? row.parsedSummary.version : null,
          description: typeof row.parsedSummary.description === 'string' ? row.parsedSummary.description : null,
          servers: Array.isArray(row.parsedSummary.servers) ? row.parsedSummary.servers.map(String) : [],
          tags: Array.isArray(row.parsedSummary.tags) ? row.parsedSummary.tags.map(String) : [],
          endpointCount: Number(row.parsedSummary.endpointCount ?? 0),
          schemaCount: Number(row.parsedSummary.schemaCount ?? 0),
          securitySchemeNames: Array.isArray(row.parsedSummary.securitySchemeNames)
            ? row.parsedSummary.securitySchemeNames.map(String)
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
    diffSummary: row.diffSummary ? parseSwaggerDiffSummary(row.diffSummary) : null,
    reviewStatus: typeof row.reviewStatus === 'string' ? row.reviewStatus : '',
    fetchedAt: typeof row.fetchedAt === 'string' ? row.fetchedAt : '',
    createdAt: typeof row.createdAt === 'string' ? row.createdAt : '',
    updatedAt: typeof row.updatedAt === 'string' ? row.updatedAt : '',
  }
}

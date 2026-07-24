import { describe, expect, it, vi, afterEach } from 'vitest'
import {
  emergencyDenyAll,
  getMcpAccessPolicy,
  getMcpPreflight,
  getSwaggerSpecDiff,
  listSwaggerSpecSources,
  publishSwaggerSpecRevision,
  listMcpServers,
  registerMcpServer,
} from '../api'
import { ApiError } from '../../../shared/api/errors'

// Mock the shared api client to decouple from URL resolution in test environments
const mockApiGet = vi.fn()
const mockApiPost = vi.fn()
const mockApiPut = vi.fn()
const mockApiDelete = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
    post: (...args: unknown[]) => mockApiPost(...args),
    put: (...args: unknown[]) => mockApiPut(...args),
    delete: (...args: unknown[]) => mockApiDelete(...args),
  },
  getAuthToken: vi.fn(() => null),
  setAuthToken: vi.fn(),
  removeAuthToken: vi.fn(),
  setOnUnauthorized: vi.fn(),
  fetchWithAuth: vi.fn(),
}))

function jsonResponse(data: unknown) {
  return { json: () => Promise.resolve(data) }
}

function errorResponse(status: number) {
  return {
    json: () => Promise.reject(new ApiError(status, status >= 500 ? 'SERVER_ERROR' : 'UNKNOWN', `HTTP ${status}`)),
  }
}

describe('mcp server api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('adapts the Reactor snake-case server contract into the admin view model', async () => {
    mockApiGet.mockReturnValue(jsonResponse([{
      server_id: 'srv-1',
      tenant_id: 'tenant-1',
      name: 'tools',
      transport: 'streamable_http',
      status: 'healthy',
      command: null,
      url: 'http://127.0.0.1:9000/mcp',
      auth_type: 'oauth',
      timeout_ms: 25000,
    }]))

    const [server] = await listMcpServers()

    expect(server).toMatchObject({
      id: 'srv-1',
      tenantId: 'tenant-1',
      transportType: 'streamable_http',
      status: 'CONNECTED',
      backendStatus: 'healthy',
      authType: 'oauth',
      timeoutMs: 25000,
    })
  })

  it('translates the admin registration draft to the authenticated Reactor contract', async () => {
    mockApiPost.mockReturnValue(jsonResponse({
      server_id: 'srv-2', tenant_id: 'tenant-1', name: 'tools',
      transport: 'streamable_http', status: 'registered', url: 'http://localhost:9000/mcp',
      command: null, auth_type: 'none', timeout_ms: 20000,
    }))

    await registerMcpServer({
      name: 'tools',
      transportType: 'STREAMABLE_HTTP',
      config: { url: 'http://localhost:9000/mcp', timeoutMs: 20000 },
    })

    expect(mockApiPost).toHaveBeenCalledWith('mcp/servers', {
      json: expect.objectContaining({
        name: 'tools',
        transport: 'streamable_http',
        url: 'http://localhost:9000/mcp',
        timeoutMs: 20000,
      }),
    })
    expect(mockApiPost.mock.calls[0][1].json).not.toHaveProperty('description')
    expect(mockApiPost.mock.calls[0][1].json).not.toHaveProperty('autoConnect')
    expect(mockApiPost.mock.calls[0][1].json).not.toHaveProperty('tenant_id')
  })

  it('parses policy metadata from admin proxy response', async () => {
    mockApiGet.mockReturnValue(jsonResponse({
      allowedJiraProjectKeys: ['DEV'],
      allowedConfluenceSpaceKeys: ['ENG'],
      allowedBitbucketRepositories: ['jarvis'],
      allowedSourceNames: ['payments', 'orders'],
      allowPreviewReads: true,
      allowPreviewWrites: false,
      allowDirectUrlLoads: false,
      publishedOnly: true,
      policySource: 'dynamic',
      dynamicEnabled: true,
      dynamicPolicy: {
        allowedJiraProjectKeys: ['DEV'],
        allowedConfluenceSpaceKeys: ['ENG'],
        allowedBitbucketRepositories: ['jarvis'],
        allowedSourceNames: ['payments'],
        allowPreviewReads: false,
        allowPreviewWrites: false,
        allowDirectUrlLoads: false,
        publishedOnly: true,
      },
    }))

    const result = await getMcpAccessPolicy('atlassian')

    expect(result.allowedJiraProjectKeys).toEqual(['DEV'])
    expect(result.allowedSourceNames).toEqual(['payments', 'orders'])
    expect(result.allowPreviewReads).toBe(true)
    expect(result.publishedOnly).toBe(true)
    expect(result.policySource).toBe('dynamic')
    expect(result.dynamicEnabled).toBe(true)
    expect(result.dynamicPolicy?.allowedSourceNames).toEqual(['payments'])
    expect(result.dynamicPolicy?.allowPreviewReads).toBe(false)
  })

  it('parses mcp preflight response for readiness panel', async () => {
    mockApiGet.mockReturnValue(jsonResponse({
      ok: true,
      readyForProduction: false,
      policySource: 'environment',
      checkedAt: '2026-03-07T09:00:00Z',
      summary: {
        passCount: 7,
        warnCount: 1,
        failCount: 0,
      },
      rateBudget: {
        observedWindow: 'process_lifetime',
        summary: {
          configuredRequestsPerSecond: 22,
          attentionServices: 1,
          rateLimitedServices: 1,
        },
        services: [
          {
            service: 'jira',
            configuredRequestsPerSecond: 8,
            requestTotal: 120,
            retryTotal: 2,
            status429Total: 1,
            attention: true,
          },
        ],
      },
      checks: [
        {
          name: 'admin_hmac',
          status: 'WARN',
          message: 'disabled',
          details: { hmacRequired: false },
        },
      ],
    }))

    const result = await getMcpPreflight('atlassian')

    expect(result.ok).toBe(true)
    expect(result.readyForProduction).toBe(false)
    expect(result.summary.warnCount).toBe(1)
    expect(result.rateBudget?.summary.rateLimitedServices).toBe(1)
    expect(result.rateBudget?.services[0].service).toBe('jira')
    expect(result.rateBudget?.services[0].status429Total).toBe(1)
    expect(result.checks).toHaveLength(1)
    expect(result.checks[0].name).toBe('admin_hmac')
    expect(result.checks[0].status).toBe('WARN')
  })

  it('parses generic swagger preflight response for readiness panel', async () => {
    mockApiGet.mockReturnValue(jsonResponse({
      status: 'ok',
      sourceCount: 2,
      publishedSourceCount: 2,
      cachedPublishedSpecs: 2,
      timestamp: '2026-03-07T09:10:00Z',
    }))

    const result = await getMcpPreflight('swagger')

    expect(result.kind).toBe('generic')
    expect(result.ok).toBe(true)
    expect(result.readyForProduction).toBe(true)
    expect(result.checkedAt).toBe('2026-03-07T09:10:00Z')
    expect(result.summary.passCount).toBe(1)
    expect(result.checks).toHaveLength(1)
    expect(result.checks[0].name).toBe('server_preflight')
    expect(result.checks[0].details?.sourceCount).toBe(2)
  })

  it('parses swagger source list from proxy response', async () => {
    mockApiGet.mockReturnValue(jsonResponse([
      {
        id: 'src-1',
        name: 'payments',
        url: 'https://example.com/payments/openapi.json',
        enabled: true,
        syncCron: '0 0 * * * *',
        jiraProjectKey: 'DEV',
        confluenceSpaceKey: 'ENG',
        bitbucketRepository: 'payments-service',
        serviceSlug: 'payments',
        ownerTeam: 'platform-payments',
        publishedRevisionId: 'rev-1',
        lastSyncStatus: 'SUCCESS',
        createdAt: '2026-03-09T09:00:00Z',
        updatedAt: '2026-03-09T10:00:00Z',
      },
    ]))

    const result = await listSwaggerSpecSources('swagger')

    expect(result).toHaveLength(1)
    expect(result[0].name).toBe('payments')
    expect(result[0].jiraProjectKey).toBe('DEV')
    expect(result[0].bitbucketRepository).toBe('payments-service')
    expect(result[0].publishedRevisionId).toBe('rev-1')
  })

  it('parses swagger diff response from proxy response', async () => {
    mockApiGet.mockReturnValue(jsonResponse({
      endpointsAdded: ['POST /payments'],
      endpointsRemoved: [],
      endpointsChanged: ['GET /payments/{id}'],
      schemasAdded: ['PaymentCreated'],
      schemasRemoved: [],
      schemasChanged: ['Payment'],
      securityChanged: true,
    }))

    const result = await getSwaggerSpecDiff('swagger', 'payments', 'rev-1', 'rev-2')

    expect(result.endpointsAdded).toEqual(['POST /payments'])
    expect(result.endpointsChanged).toEqual(['GET /payments/{id}'])
    expect(result.schemasChanged).toEqual(['Payment'])
    expect(result.securityChanged).toBe(true)
  })

  it('parses swagger publish result from proxy response', async () => {
    mockApiPost.mockReturnValue(jsonResponse({
      sourceName: 'payments',
      revisionId: 'rev-2',
      publishedAt: '2026-03-09T12:00:00Z',
      summary: {
        title: 'Payments API',
        version: '1.2.0',
        description: 'Payments service',
        servers: ['https://api.example.com'],
        tags: ['payments'],
        endpointCount: 12,
        schemaCount: 8,
        securitySchemeNames: ['bearerAuth'],
      },
    }))

    const result = await publishSwaggerSpecRevision('swagger', 'payments', 'rev-2')

    expect(result.sourceName).toBe('payments')
    expect(result.revisionId).toBe('rev-2')
    expect(result.summary.endpointCount).toBe(12)
  })

  it('sends emergency deny-all POST to the correct endpoint', async () => {
    mockApiPost.mockReturnValue(jsonResponse(null))

    await emergencyDenyAll('atlassian')

    expect(mockApiPost).toHaveBeenCalledWith(
      expect.stringContaining('atlassian/access-policy/emergency-deny-all'),
    )
  })

  it('throws ApiError on emergency deny-all failure', async () => {
    mockApiPost.mockReturnValue(errorResponse(500))

    await expect(emergencyDenyAll('atlassian')).rejects.toBeInstanceOf(ApiError)
    await expect(emergencyDenyAll('atlassian')).rejects.toSatisfy(
      (err: ApiError) => err.status === 500 && err.code === 'SERVER_ERROR',
    )
  })
})

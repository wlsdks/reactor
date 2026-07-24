import { http, HttpResponse } from 'msw'

const mockCacheStats = {
  enabled: true,
  semanticEnabled: true,
  totalExactHits: 1247,
  totalSemanticHits: 893,
  totalMisses: 312,
  hitRate: 0.873,
  config: {
    ttlMinutes: 60,
    maxSize: 1000,
    similarityThreshold: 0.92,
    maxCandidates: 50,
    cacheableTemperature: 0,
  },
}

const mockVectorStoreStats = {
  available: true,
  documentCount: 142,
}

const mockRuntimeSettings = [
  {
    key: 'cache.enabled',
    value: 'true',
    type: 'BOOLEAN',
    category: 'cache',
    description: 'Enable response caching',
    updatedBy: 'mock-admin',
    updatedAt: '2026-07-01T00:00:00Z',
  },
]

export { mockCacheStats, mockVectorStoreStats }

export const ragCacheHandlers = [
  http.get('/api/admin/platform/cache/stats', () => {
    return HttpResponse.json(mockCacheStats)
  }),

  http.get('/api/admin/platform/vectorstore/stats', () => {
    return HttpResponse.json(mockVectorStoreStats)
  }),

  http.post('/api/admin/platform/cache/invalidate', () => {
    return HttpResponse.json({ invalidated: 2140 })
  }),

  http.post('/api/admin/platform/cache/invalidate-key', () => {
    return HttpResponse.json({ invalidated: true, cacheEnabled: true })
  }),

  http.post('/api/admin/platform/cache/invalidate-by-pattern', () => {
    return HttpResponse.json({ invalidatedCount: 3, cacheEnabled: true })
  }),

  http.get('/api/admin/settings', () => {
    return HttpResponse.json(mockRuntimeSettings)
  }),

  http.get('/api/admin/settings/:key', ({ params }) => {
    const setting = mockRuntimeSettings.find((item) => item.key === params.key)
    return setting
      ? HttpResponse.json(setting)
      : HttpResponse.json({ error: 'Not found' }, { status: 404 })
  }),

  http.put('/api/admin/settings/:key', async ({ params, request }) => {
    const body = await request.json() as { value?: string }
    return HttpResponse.json({
      key: params.key,
      value: body.value ?? '',
      status: 'updated',
    })
  }),

  http.delete('/api/admin/settings/:key', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  http.post('/api/documents/search', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    const query = (body.query as string) || ''
    return HttpResponse.json([
      {
        id: 'doc-001',
        content: `Sample document matching "${query}" — This is a test result from the vector store with high relevance.`,
        metadata: { source: 'confluence', channel: 'engineering' },
        score: 0.94,
      },
      {
        id: 'doc-002',
        content: `Another relevant document for "${query}" — Contains technical specifications and API documentation.`,
        metadata: { source: 'notion', channel: 'product' },
        score: 0.87,
      },
      {
        id: 'doc-003',
        content: `Partial match for "${query}" — Related FAQ entry from the support knowledge base.`,
        metadata: { source: 'zendesk', channel: 'support' },
        score: 0.72,
      },
    ])
  }),
]

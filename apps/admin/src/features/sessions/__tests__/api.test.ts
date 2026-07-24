import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  getConversationOverview,
  listSessionsFeed,
  getAdminSessionDetail,
  listUsers,
  listUserSessions,
  deleteAdminSession,
  exportAdminSession,
  addSessionTag,
  removeSessionTag,
} from '../api'

const mockApiGet = vi.fn()
const mockApiPost = vi.fn()
const mockApiDelete = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
    post: (...args: unknown[]) => mockApiPost(...args),
    put: vi.fn(),
    delete: (...args: unknown[]) => mockApiDelete(...args),
  },
  getAuthToken: vi.fn(() => null),
  setAuthToken: vi.fn(),
  removeAuthToken: vi.fn(),
  setOnUnauthorized: vi.fn(),
}))

function jsonResponse(data: unknown) {
  return { json: () => Promise.resolve(data) }
}

function blobResponse(data: unknown) {
  return { blob: () => Promise.resolve(new Blob([JSON.stringify(data)], { type: 'application/json' })) }
}

function voidResponse() {
  return { then: (fn: (v: unknown) => unknown) => Promise.resolve(fn(undefined)) }
}

const mockOverview = {
  period: '7d',
  days: 7,
  totalSessions: 150,
  uniqueUsers: 20,
  statusCounts: { completed: 145, failed: 5 },
}

const mockPaginatedSessions = {
  items: [{ sessionId: 'sess_1', userId: 'user_001', channel: 'web', messageCount: 5, preview: 'Hello', lastActivity: Date.now(), trust: 'clean', feedback: null, tags: [] }],
  total: 50,
  offset: 0,
  limit: 30,
}

const mockSessionDetail = {
  sessionId: 'sess_1',
  userId: 'user_001',
  channel: 'web',
  model: null,
  messageCount: 3,
  startedAt: Date.now() - 60000,
  lastActivity: Date.now(),
  trust: 'clean',
  feedback: 'positive',
  tags: [],
  messages: [
    { id: 1, role: 'user', content: 'Hello', timestamp: Date.now() - 60000 },
    { id: 2, role: 'assistant', content: 'Hi!', timestamp: Date.now() - 58000 },
  ],
}

describe('sessions api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('getConversationOverview calls admin/sessions/overview with period', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockOverview))

    const result = await getConversationOverview('30d')

    expect(mockApiGet).toHaveBeenCalledWith('admin/sessions/overview', { searchParams: { period: '30d' } })
    expect(result).toEqual({
      totalSessions: 150,
      activeUsers: 20,
      statusCounts: { completed: 145, failed: 5 },
    })
  })

  it('normalizes the current compact overview contract into a safe view model', async () => {
    mockApiGet.mockReturnValue(jsonResponse({
      period: '7d',
      days: 7,
      totalSessions: 2,
      statusCounts: { completed: 2 },
      uniqueUsers: 1,
    }))

    await expect(getConversationOverview('7d')).resolves.toEqual({
      totalSessions: 2,
      activeUsers: 1,
      statusCounts: { completed: 2 },
    })
  })

  it('fail-closes malformed overview numbers and collections', async () => {
    mockApiGet.mockReturnValue(jsonResponse({
      totalSessions: 'NaN',
      uniqueUsers: Infinity,
      statusCounts: { completed: 'bad' },
    }))

    const result = await getConversationOverview('7d')

    expect(result.totalSessions).toBe(0)
    expect(result.activeUsers).toBe(0)
    expect(result.statusCounts.completed).toBe(0)
    expect(result).not.toHaveProperty('trend')
  })

  it('listSessionsFeed calls admin/sessions with supported search and pagination', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockPaginatedSessions))

    const result = await listSessionsFeed({ q: 'grounded' }, 10, 30)

    expect(mockApiGet).toHaveBeenCalledWith('admin/sessions', { searchParams: expect.any(URLSearchParams) })
    const params = mockApiGet.mock.calls[0][1].searchParams as URLSearchParams
    expect(params.get('q')).toBe('grounded')
    expect(params.get('offset')).toBe('10')
    expect(params.get('limit')).toBe('30')
    expect(result.items).toHaveLength(1)
    expect(result.total).toBe(50)
  })

  it('normalizes the current admin session summary without inventing legacy metrics', async () => {
    mockApiGet.mockReturnValue(jsonResponse({
      items: [{
        sessionId: 'run_1234567890abcdef',
        threadId: 'thread_ops',
        userId: 'local-user',
        status: 'completed',
        preview: 'Operational question',
        createdAt: '2026-07-10T12:00:00Z',
        updatedAt: '2026-07-10T12:01:00Z',
        channel: 'api',
        traceId: 'trace_abcdef1234567890',
      }],
      total: 1,
      offset: 0,
      limit: 30,
    }))

    const result = await listSessionsFeed({}, 0, 30)

    expect(result.items[0]).toMatchObject({
      sessionId: 'run_1234567890abcdef',
      threadId: 'thread_ops',
      traceId: 'trace_abcdef1234567890',
      status: 'completed',
      channel: 'api',
      createdAt: new Date('2026-07-10T12:00:00Z').getTime(),
      updatedAt: new Date('2026-07-10T12:01:00Z').getTime(),
    })
    expect(result.items[0].messageCount).toBeUndefined()
    expect(result.items[0].trust).toBeUndefined()
  })

  it('listSessionsFeed does not emit unsupported backend filters', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockPaginatedSessions))

    await listSessionsFeed({}, 0, 30)

    const params = mockApiGet.mock.calls[0][1].searchParams as URLSearchParams
    expect(params.has('dateFrom')).toBe(false)
    expect(params.has('dateTo')).toBe(false)
    expect(params.has('channel')).toBe(false)
    expect(params.has('trust')).toBe(false)
  })

  it('getAdminSessionDetail calls admin/sessions/:id', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockSessionDetail))

    const result = await getAdminSessionDetail('sess_1')

    expect(mockApiGet).toHaveBeenCalledWith('admin/sessions/sess_1')
    expect(result.sessionId).toBe('sess_1')
    expect(result.messages).toHaveLength(2)
    expect(result.channel).toBe('web')
    expect(result.messages[0]).toMatchObject({ role: 'user' })
  })

  it('listUsers calls admin/users with search params', async () => {
    const mockUsers = { items: [{ userId: 'user_001', sessionCount: 10 }], total: 1, offset: 0, limit: 30 }
    mockApiGet.mockReturnValue(jsonResponse(mockUsers))

    const result = await listUsers({ q: 'test', offset: 0, limit: 10 })

    expect(mockApiGet).toHaveBeenCalledWith('admin/users', {
      searchParams: { q: 'test', offset: '0', limit: '10' },
    })
    expect(result.items[0]).toHaveProperty('userId')
    expect(result.items[0]).toHaveProperty('sessionCount')
  })

  it('normalizes current user activity timestamps and last-session identity', async () => {
    mockApiGet.mockReturnValue(jsonResponse({
      items: [{
        userId: 'local-user',
        sessionCount: 2,
        lastActiveAt: '2026-07-10T12:23:16.653867+00:00',
        lastSessionId: 'run_ddc0e9a063ab40f4aa73703fb141f96d',
      }],
      total: 1,
      offset: 0,
      limit: 30,
    }))

    const result = await listUsers({ offset: 0, limit: 30 })

    expect(result.items[0]).toMatchObject({
      userId: 'local-user',
      sessionCount: 2,
      lastActiveAt: new Date('2026-07-10T12:23:16.653867+00:00').getTime(),
      lastSessionId: 'run_ddc0e9a063ab40f4aa73703fb141f96d',
    })
    expect(result.items[0].totalMessages).toBeUndefined()
  })

  it('listUserSessions calls admin/users/:id/sessions', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockPaginatedSessions))

    const result = await listUserSessions('user_001', {}, 0, 30)

    expect(mockApiGet).toHaveBeenCalledWith('admin/users/user_001/sessions', { searchParams: expect.any(URLSearchParams) })
    expect(result.items).toHaveLength(1)
  })

  it('deleteAdminSession calls DELETE admin/sessions/:id', async () => {
    mockApiDelete.mockReturnValue(voidResponse())

    await expect(deleteAdminSession('sess_1')).resolves.toBeUndefined()

    expect(mockApiDelete).toHaveBeenCalledWith('admin/sessions/sess_1')
  })

  it('exportAdminSession calls GET with format and returns blob', async () => {
    mockApiGet.mockReturnValue(blobResponse({ sessionId: 'sess_1' }))

    const blob = await exportAdminSession('sess_1', 'json')

    expect(mockApiGet).toHaveBeenCalledWith('admin/sessions/sess_1/export', { searchParams: { format: 'json' } })
    expect(blob).toBeInstanceOf(Blob)
  })

  it('addSessionTag calls POST with label and comment', async () => {
    const mockTag = { id: 'tag_1', label: 'escalated', comment: 'Needs review', createdBy: 'admin', createdAt: Date.now() }
    mockApiPost.mockReturnValue(jsonResponse(mockTag))

    const result = await addSessionTag('sess_1', 'escalated', 'Needs review')

    expect(mockApiPost).toHaveBeenCalledWith('admin/sessions/sess_1/tags', { json: { label: 'escalated', comment: 'Needs review' } })
    expect(result.label).toBe('escalated')
    expect(result.comment).toBe('Needs review')
    expect(result).toHaveProperty('id')
  })

  it('removeSessionTag calls DELETE admin/sessions/:id/tags/:tagId', async () => {
    mockApiDelete.mockReturnValue(voidResponse())

    await expect(removeSessionTag('sess_1', 'tag_abc')).resolves.toBeUndefined()

    expect(mockApiDelete).toHaveBeenCalledWith('admin/sessions/sess_1/tags/tag_abc')
  })
})

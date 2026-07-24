import { describe, it, expect, vi, afterEach } from 'vitest'
import { listAllApprovals, approveToolCall, rejectToolCall } from '../api'

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
}))

function jsonResponse(data: unknown) {
  return { json: () => Promise.resolve(data) }
}

const mockApproval = {
  id: 'approval-1',
  status: 'pending',
  toolName: 'create_issue',
  requestedBy: 'user-1',
  createdAt: '2026-03-01T00:00:00Z',
}

describe('approvals api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('listAllApprovals returns array without status filter', async () => {
    mockApiGet.mockReturnValue(jsonResponse([mockApproval]))

    const result = await listAllApprovals()

    expect(Array.isArray(result)).toBe(true)
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('approval-1')
  })

  it('adapts the Reactor approval lifecycle and safe metadata contract', async () => {
    mockApiGet.mockReturnValue(jsonResponse([{
      approval_id: 'approval-2',
      run_id: 'run-2',
      tool_id: 'Slack:post_message',
      status: 'expired',
      requested_by: 'operator-2',
      requested_at: '2026-07-11T12:00:00Z',
      decided_at: null,
      decided_by: null,
      decision_reason: null,
      request_payload: {
        tool_risk_level: 'external_side_effect',
        tool_timeout_ms: 45000,
        idempotency_key: 'idem-2',
      },
    }]))

    const [result] = await listAllApprovals('TIMED_OUT')

    expect(mockApiGet).toHaveBeenCalledWith('approvals', {
      searchParams: { limit: 200, status: 'expired' },
    })
    expect(result).toMatchObject({
      id: 'approval-2',
      runId: 'run-2',
      toolName: 'Slack:post_message',
      status: 'TIMED_OUT',
      riskLevel: 'external_side_effect',
      timeoutMs: 45000,
      idempotencyKey: 'idem-2',
    })
  })

  it('listAllApprovals passes status as searchParam', async () => {
    mockApiGet.mockReturnValue(jsonResponse([mockApproval]))

    await listAllApprovals('pending')

    expect(mockApiGet).toHaveBeenCalledWith(
      'approvals',
      expect.objectContaining({ searchParams: expect.objectContaining({ status: 'pending', limit: 200 }) }),
    )
  })

  it('listAllApprovals called with no args includes limit', async () => {
    mockApiGet.mockReturnValue(jsonResponse([]))

    await listAllApprovals()

    expect(mockApiGet).toHaveBeenCalledWith('approvals', { searchParams: { limit: 200 } })
  })

  it('approveToolCall sends POST to correct endpoint and returns response', async () => {
    const mockResponse = { id: 'approval-1', status: 'approved' }
    mockApiPost.mockReturnValue(jsonResponse(mockResponse))

    const result = await approveToolCall('approval-1')

    expect(mockApiPost).toHaveBeenCalledWith('approvals/approval-1/approve', { json: {} })
    expect(result).toHaveProperty('id', 'approval-1')
    expect(result).toHaveProperty('status', 'approved')
  })

  it('rejectToolCall sends POST with reason and returns response', async () => {
    const mockResponse = { id: 'approval-1', status: 'rejected' }
    mockApiPost.mockReturnValue(jsonResponse(mockResponse))

    const result = await rejectToolCall('approval-1', 'not allowed')

    expect(mockApiPost).toHaveBeenCalledWith(
      'approvals/approval-1/reject',
      { json: { reason: 'not allowed' } },
    )
    expect(result).toHaveProperty('status', 'rejected')
  })

  it('rejectToolCall sends POST without reason when omitted', async () => {
    mockApiPost.mockReturnValue(jsonResponse({ id: 'approval-1', status: 'rejected' }))

    await rejectToolCall('approval-1')

    expect(mockApiPost).toHaveBeenCalledWith(
      'approvals/approval-1/reject',
      { json: { reason: undefined } },
    )
  })
})

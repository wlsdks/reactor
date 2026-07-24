import { describe, it, expect, vi, afterEach } from 'vitest'
import { logout, changePassword } from '../api'

const mockApiPost = vi.fn()
const { mockKyCreate } = vi.hoisted(() => ({
  mockKyCreate: vi.fn(() => ({ post: vi.fn() })),
}))

vi.mock('ky', () => ({
  default: { create: mockKyCreate },
}))

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: vi.fn(),
    post: (...args: unknown[]) => mockApiPost(...args),
    put: vi.fn(),
    delete: vi.fn(),
  },
  getAuthToken: vi.fn(() => null),
  setAuthToken: vi.fn(),
  removeAuthToken: vi.fn(),
  setOnUnauthorized: vi.fn(),
}))

function thenableResponse() {
  return { then: (fn: (v: unknown) => unknown) => Promise.resolve(fn(undefined)) }
}

describe('auth api (authenticated calls)', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('logout sends POST to auth/logout', async () => {
    mockApiPost.mockReturnValue(thenableResponse())

    await logout()

    expect(mockApiPost).toHaveBeenCalledWith('auth/logout')
  })

  it('changePassword sends POST with current and new password', async () => {
    mockApiPost.mockReturnValue(thenableResponse())

    await changePassword({
      currentPassword: 'old-pass',
      newPassword: 'new-pass',
    })

    expect(mockApiPost).toHaveBeenCalledWith(
      'auth/change-password',
      expect.objectContaining({
        json: { currentPassword: 'old-pass', newPassword: 'new-pass' },
      }),
    )
  })
})

describe('auth api (public login calls)', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('normalizes a FastAPI login failure into the shared API error contract', async () => {
    vi.resetModules()
    await import('../api')

    const config = mockKyCreate.mock.calls.at(-1)?.[0] as {
      hooks?: { beforeError?: Array<(error: { response?: Response }) => Promise<never>> }
    }
    const beforeError = config.hooks?.beforeError?.[0]
    expect(beforeError).toBeTypeOf('function')

    await expect(beforeError?.({
      response: new Response(JSON.stringify({ detail: 'JWT authentication is not configured' }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      }),
    })).rejects.toSatisfy(
      (error: unknown) => typeof error === 'object'
        && error !== null
        && (error as { name?: string }).name === 'ApiError'
        && (error as { status?: number }).status === 503
        && (error as { serverMessage?: string }).serverMessage === 'JWT authentication is not configured',
    )
  })
})

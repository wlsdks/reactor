import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useAuthForm } from '../useAuthForm'

// Mock useAuth
const mockLogin = vi.fn<(email: string, password: string) => Promise<boolean>>()
const mockClearError = vi.fn()

vi.mock('../context', () => ({
  useAuth: () => ({
    login: mockLogin,
    clearError: mockClearError,
  }),
}))

// Mock authApi
vi.mock('../api', () => ({
  register: vi.fn(),
  iamLogin: vi.fn(),
  exchangeToken: vi.fn(),
  iamLogout: vi.fn(),
  IAM_ENABLED: false,
}))

// Mock i18next — return the key itself as translation
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}))

// Mock constants — self-registration enabled by default
let selfRegistrationEnabled = true
vi.mock('../../../shared/lib/constants', () => ({
  get AUTH_SELF_REGISTRATION_ENABLED() {
    return selfRegistrationEnabled
  },
  PASSWORD_MIN_LENGTH: 8,
}))

// Lazy import so mocks are in place
async function getAuthApi() {
  const mod = await import('../api')
  return mod
}

describe('useAuthForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockLogin.mockResolvedValue(true)
    selfRegistrationEnabled = true
  })

  it('starts in login mode with empty fields', () => {
    const { result } = renderHook(() => useAuthForm())

    expect(result.current.mode).toBe('login')
    expect(result.current.name).toBe('')
    expect(result.current.email).toBe('')
    expect(result.current.password).toBe('')
    expect(result.current.confirmPassword).toBe('')
    expect(result.current.localError).toBeNull()
    expect(result.current.registerMessage).toBeNull()
    expect(result.current.submitting).toBe(false)
  })

  it('switchMode changes mode and clears errors', () => {
    const { result } = renderHook(() => useAuthForm())

    // Set an error first
    act(() => {
      result.current.switchMode('register')
    })

    expect(result.current.mode).toBe('register')
    expect(mockClearError).toHaveBeenCalled()

    act(() => {
      result.current.switchMode('login')
    })

    expect(result.current.mode).toBe('login')
  })

  it('handleLogin calls auth login with email and password', async () => {
    const { result } = renderHook(() => useAuthForm())

    act(() => {
      result.current.setEmail('user@example.com')
      result.current.setPassword('secret123')
    })

    let ok: boolean
    await act(async () => {
      ok = await result.current.handleLogin()
    })

    expect(ok!).toBe(true)
    expect(mockLogin).toHaveBeenCalledWith('user@example.com', 'secret123')
    expect(mockClearError).toHaveBeenCalled()
  })

  it('handleRegister validates password length', async () => {
    const { result } = renderHook(() => useAuthForm())

    act(() => {
      result.current.setName('Test User')
      result.current.setEmail('test@example.com')
      result.current.setPassword('short')
      result.current.setConfirmPassword('short')
    })

    let ok: boolean
    await act(async () => {
      ok = await result.current.handleRegister()
    })

    expect(ok!).toBe(false)
    expect(result.current.localError).toBe('auth.passwordMinLength')
  })

  it('handleRegister validates password match', async () => {
    const { result } = renderHook(() => useAuthForm())

    act(() => {
      result.current.setName('Test User')
      result.current.setEmail('test@example.com')
      result.current.setPassword('password123')
      result.current.setConfirmPassword('differentpassword')
    })

    let ok: boolean
    await act(async () => {
      ok = await result.current.handleRegister()
    })

    expect(ok!).toBe(false)
    expect(result.current.localError).toBe('auth.passwordMismatch')
  })

  it('handleRegister validates name is required', async () => {
    const { result } = renderHook(() => useAuthForm())

    act(() => {
      result.current.setName('  ')
      result.current.setEmail('test@example.com')
      result.current.setPassword('password123')
      result.current.setConfirmPassword('password123')
    })

    let ok: boolean
    await act(async () => {
      ok = await result.current.handleRegister()
    })

    expect(ok!).toBe(false)
    expect(result.current.localError).toBe('auth.nameRequired')
  })

  it('handleRegister rejects when self-registration is disabled', async () => {
    selfRegistrationEnabled = false
    const { result } = renderHook(() => useAuthForm())

    act(() => {
      result.current.setName('Test User')
      result.current.setEmail('test@example.com')
      result.current.setPassword('password123')
      result.current.setConfirmPassword('password123')
    })

    let ok: boolean
    await act(async () => {
      ok = await result.current.handleRegister()
    })

    expect(ok!).toBe(false)
    expect(result.current.localError).toBe('auth.registrationDisabled')
  })

  it('handleRegister calls api and auto-logs in', async () => {
    const authApi = await getAuthApi()
    vi.mocked(authApi.register).mockResolvedValue({
      email: 'test@example.com',
      userId: '1',
    })

    const { result } = renderHook(() => useAuthForm())

    act(() => {
      result.current.setName('Test')
      result.current.setEmail('test@example.com')
      result.current.setPassword('password123')
      result.current.setConfirmPassword('password123')
    })

    let ok: boolean
    await act(async () => {
      ok = await result.current.handleRegister()
    })

    expect(ok!).toBe(true)
    expect(authApi.register).toHaveBeenCalledWith({
      name: 'Test',
      email: 'test@example.com',
      password: 'password123',
    })
    expect(mockLogin).toHaveBeenCalledWith('test@example.com', 'password123')
  })

  it('handleRegister shows success message when auto-login fails', async () => {
    const authApi = await getAuthApi()
    vi.mocked(authApi.register).mockResolvedValue({
      email: 'test@example.com',
      userId: '1',
    })
    mockLogin.mockResolvedValueOnce(false)

    const { result } = renderHook(() => useAuthForm())

    act(() => {
      result.current.setName('Test')
      result.current.setEmail('test@example.com')
      result.current.setPassword('password123')
      result.current.setConfirmPassword('password123')
    })

    let ok: boolean
    await act(async () => {
      ok = await result.current.handleRegister()
    })

    expect(ok!).toBe(false)
    expect(result.current.registerMessage).toBe('auth.registerSuccess')
    expect(result.current.mode).toBe('login')
  })

})

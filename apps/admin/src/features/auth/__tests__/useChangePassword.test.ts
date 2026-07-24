import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useChangePassword } from '../useChangePassword'

vi.mock('../api', () => ({
  changePassword: vi.fn(),
  iamLogin: vi.fn(),
  exchangeToken: vi.fn(),
  iamLogout: vi.fn(),
  IAM_ENABLED: false,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

import * as authApi from '../api'

const mockChangePassword = authApi.changePassword as ReturnType<typeof vi.fn>

describe('useChangePassword', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('starts with closed state and empty fields', () => {
    const { result } = renderHook(() => useChangePassword())

    expect(result.current.isOpen).toBe(false)
    expect(result.current.currentPassword).toBe('')
    expect(result.current.newPassword).toBe('')
    expect(result.current.confirmPassword).toBe('')
    expect(result.current.error).toBeNull()
    expect(result.current.success).toBeNull()
    expect(result.current.isSubmitting).toBe(false)
  })

  it('opens modal and resets all fields', () => {
    const { result } = renderHook(() => useChangePassword())

    act(() => { result.current.setCurrentPassword('old') })
    act(() => { result.current.setNewPassword('new') })
    act(() => { result.current.open() })

    expect(result.current.isOpen).toBe(true)
    expect(result.current.currentPassword).toBe('')
    expect(result.current.newPassword).toBe('')
    expect(result.current.confirmPassword).toBe('')
    expect(result.current.error).toBeNull()
    expect(result.current.success).toBeNull()
  })

  it('closes modal', () => {
    const { result } = renderHook(() => useChangePassword())

    act(() => { result.current.open() })
    expect(result.current.isOpen).toBe(true)

    act(() => { result.current.close() })
    expect(result.current.isOpen).toBe(false)
  })

  it('sets error when required fields are empty', async () => {
    const { result } = renderHook(() => useChangePassword())

    await act(async () => { await result.current.submit() })

    expect(result.current.error).toBe('auth.passwordRequired')
    expect(mockChangePassword).not.toHaveBeenCalled()
  })

  it('sets error when new password is too short', async () => {
    const { result } = renderHook(() => useChangePassword())

    act(() => { result.current.setCurrentPassword('oldpass123') })
    act(() => { result.current.setNewPassword('short') })
    act(() => { result.current.setConfirmPassword('short') })

    await act(async () => { await result.current.submit() })

    expect(result.current.error).toBe('auth.passwordMinLength')
    expect(mockChangePassword).not.toHaveBeenCalled()
  })

  it('sets error when passwords do not match', async () => {
    const { result } = renderHook(() => useChangePassword())

    act(() => { result.current.setCurrentPassword('oldpass123') })
    act(() => { result.current.setNewPassword('newpassword1') })
    act(() => { result.current.setConfirmPassword('newpassword2') })

    await act(async () => { await result.current.submit() })

    expect(result.current.error).toBe('auth.passwordMismatch')
    expect(mockChangePassword).not.toHaveBeenCalled()
  })

  it('calls API and sets success on successful submit', async () => {
    mockChangePassword.mockResolvedValue(undefined)
    const { result } = renderHook(() => useChangePassword())

    act(() => { result.current.setCurrentPassword('oldpass123') })
    act(() => { result.current.setNewPassword('newpassword1') })
    act(() => { result.current.setConfirmPassword('newpassword1') })

    await act(async () => { await result.current.submit() })

    expect(mockChangePassword).toHaveBeenCalledWith({
      currentPassword: 'oldpass123',
      newPassword: 'newpassword1',
    })
    expect(result.current.success).toBe('auth.passwordChanged')
    expect(result.current.error).toBeNull()
    expect(result.current.currentPassword).toBe('')
    expect(result.current.newPassword).toBe('')
    expect(result.current.confirmPassword).toBe('')
    expect(result.current.isSubmitting).toBe(false)
  })

  it('uses fallback i18n key when API returns no message', async () => {
    mockChangePassword.mockResolvedValue(undefined)
    const { result } = renderHook(() => useChangePassword())

    act(() => { result.current.setCurrentPassword('oldpass123') })
    act(() => { result.current.setNewPassword('newpassword1') })
    act(() => { result.current.setConfirmPassword('newpassword1') })

    await act(async () => { await result.current.submit() })

    expect(result.current.success).toBe('auth.passwordChanged')
  })

  it('sets error message on API failure', async () => {
    mockChangePassword.mockRejectedValue(new Error('Current password incorrect'))
    const { result } = renderHook(() => useChangePassword())

    act(() => { result.current.setCurrentPassword('wrongpass') })
    act(() => { result.current.setNewPassword('newpassword1') })
    act(() => { result.current.setConfirmPassword('newpassword1') })

    await act(async () => { await result.current.submit() })

    expect(result.current.error).toBe('Current password incorrect')
    expect(result.current.success).toBeNull()
    expect(result.current.isSubmitting).toBe(false)
  })
})

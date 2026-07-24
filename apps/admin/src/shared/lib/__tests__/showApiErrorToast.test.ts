import { describe, it, expect, beforeEach, vi } from 'vitest'
import { showApiErrorToast } from '../showApiErrorToast'
import { useToastStore } from '../../store/toast.store'
import { ApiError, NetworkError } from '../../api/errors'
import '../../i18n/config'

beforeEach(() => {
  // Drop any toasts queued by previous tests so assertions are positional.
  const state = useToastStore.getState()
  for (const toast of state.toasts) state.removeToast(toast.id)
})

function lastToast() {
  const list = useToastStore.getState().toasts
  return list[list.length - 1]
}

describe('showApiErrorToast', () => {
  it('shows an error toast with the localized message', () => {
    showApiErrorToast(ApiError.fromResponse(404, null))
    const toast = lastToast()
    expect(toast.type).toBe('error')
    expect(toast.message).toBe('리소스를 찾을 수 없어요')
    // 404 has no recovery → no action button.
    expect(toast.action).toBeUndefined()
  })

  it('appends the hint on a new line when present', () => {
    showApiErrorToast(ApiError.fromResponse(403, null))
    const toast = lastToast()
    expect(toast.message).toContain('권한이 없어요')
    expect(toast.message).toContain('이 작업은 ADMIN 권한이 필요해요')
    expect(toast.message.split('\n').length).toBeGreaterThanOrEqual(2)
  })

  it('routes onRetry into the retry recovery action', () => {
    const onRetry = vi.fn()
    showApiErrorToast(ApiError.fromResponse(500, null), { onRetry })
    const toast = lastToast()
    expect(toast.action?.label).toBe('다시 시도')
    toast.action?.onAction()
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('routes onLogin into the login recovery action', () => {
    const onLogin = vi.fn()
    showApiErrorToast(ApiError.fromResponse(401, null), { onLogin })
    const toast = lastToast()
    expect(toast.action?.label).toBe('다시 로그인')
    toast.action?.onAction()
    expect(onLogin).toHaveBeenCalledTimes(1)
  })

  it('omits the action button when retry handler is not provided', () => {
    showApiErrorToast(ApiError.fromResponse(500, null))
    const toast = lastToast()
    expect(toast.action).toBeUndefined()
  })

  it('omits the action button when login handler is not provided', () => {
    showApiErrorToast(ApiError.fromResponse(401, null))
    const toast = lastToast()
    expect(toast.action).toBeUndefined()
  })

  it('handles NetworkError with retry recovery', () => {
    const onRetry = vi.fn()
    showApiErrorToast(new NetworkError(), { onRetry })
    const toast = lastToast()
    expect(toast.message).toBe('네트워크 연결을 확인해 주세요')
    expect(toast.action?.label).toBe('다시 시도')
    toast.action?.onAction()
    expect(onRetry).toHaveBeenCalled()
  })

  it('returns the resolved payload so callers can re-use it', () => {
    const resolved = showApiErrorToast(ApiError.fromResponse(429, null))
    expect(resolved.message).toBe('요청이 너무 많아요')
    expect(resolved.hint).toBe('잠시 후 다시 시도해 주세요')
    expect(resolved.recovery?.type).toBe('retry')
  })
})

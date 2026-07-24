import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { copyToClipboard } from '../clipboard'
import { useToastStore } from '../../store/toast.store'

function clearToasts() {
  // Reset store between tests so assertions on toast contents stay isolated.
  useToastStore.setState({ toasts: [] })
}

describe('copyToClipboard', () => {
  beforeEach(() => {
    clearToasts()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    clearToasts()
  })

  it('uses navigator.clipboard.writeText when available', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText: writeTextMock } })

    const ok = await copyToClipboard('hello world')

    expect(writeTextMock).toHaveBeenCalledWith('hello world')
    expect(ok).toBe(true)
  })

  it('falls back to textarea execCommand when clipboard API throws', async () => {
    const writeTextMock = vi.fn().mockRejectedValue(new Error('Not allowed'))
    vi.stubGlobal('navigator', { clipboard: { writeText: writeTextMock } })

    const execCommandMock = vi.fn().mockReturnValue(true)
    document.execCommand = execCommandMock

    const ok = await copyToClipboard('fallback text')

    expect(execCommandMock).toHaveBeenCalledWith('copy')
    expect(ok).toBe(true)
  })

  it('emits a success toast by default with the supplied label', async () => {
    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    })

    const ok = await copyToClipboard('abc-123', { label: 'ID' })

    expect(ok).toBe(true)
    const toasts = useToastStore.getState().toasts
    expect(toasts).toHaveLength(1)
    expect(toasts[0].type).toBe('success')
    expect(toasts[0].message).toContain('ID')
  })

  it('respects toastType override', async () => {
    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    })

    await copyToClipboard('value', { label: 'ID', toastType: 'info' })

    const toasts = useToastStore.getState().toasts
    expect(toasts).toHaveLength(1)
    expect(toasts[0].type).toBe('info')
  })

  it('suppresses toast when silent is set', async () => {
    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    })

    const ok = await copyToClipboard('value', { silent: true })

    expect(ok).toBe(true)
    expect(useToastStore.getState().toasts).toHaveLength(0)
  })

  it('emits an error toast and returns false when both APIs fail', async () => {
    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error('fail')) },
    })
    document.execCommand = vi.fn().mockReturnValue(false)

    const ok = await copyToClipboard('value')

    expect(ok).toBe(false)
    const toasts = useToastStore.getState().toasts
    expect(toasts).toHaveLength(1)
    expect(toasts[0].type).toBe('error')
  })

  it('still invokes legacy onSuccess callback after a successful copy', async () => {
    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
    const onSuccess = vi.fn()

    await copyToClipboard('value', { onSuccess, silent: true })

    expect(onSuccess).toHaveBeenCalledOnce()
  })
})

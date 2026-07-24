import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, act } from '../../../test/utils'
import { ToastContainer } from '../ToastContainer'
import {
  useToastStore,
  getDefaultDuration,
  MAX_VISIBLE_TOASTS,
  selectVisibleToasts,
  selectOverflowCount,
  selectAllToastsSorted,
} from '../../store/toast.store'

// Reset store state before each test
beforeEach(() => {
  useToastStore.setState({ toasts: [], expandQueue: false })
})

describe('ToastContainer', () => {
  it('renders nothing when there are no toasts', () => {
    const { container } = render(<ToastContainer />)
    expect(container.innerHTML).toBe('')
  })

  it('renders a success toast', () => {
    useToastStore.setState({
      toasts: [{ id: 'toast-1', type: 'success', message: 'Item created successfully' }],
    })
    render(<ToastContainer />)
    expect(screen.getByText('Item created successfully')).toBeInTheDocument()
    expect(screen.getByText('common.toast.types.success')).toBeInTheDocument()
  })

  it('renders an error toast with exclamation icon', () => {
    useToastStore.setState({
      toasts: [{ id: 'toast-2', type: 'error', message: 'Something went wrong' }],
    })
    render(<ToastContainer />)
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('!')).toBeInTheDocument()
  })

  it('renders an info toast', () => {
    useToastStore.setState({
      toasts: [{ id: 'toast-3', type: 'info', message: 'New update available' }],
    })
    render(<ToastContainer />)
    expect(screen.getByText('New update available')).toBeInTheDocument()
    expect(screen.getByText('common.toast.types.info')).toBeInTheDocument()
  })

  it('renders a warning toast', () => {
    useToastStore.setState({
      toasts: [{ id: 'toast-4', type: 'warning', message: 'Approaching rate limit' }],
    })
    render(<ToastContainer />)
    expect(screen.getByText('Approaching rate limit')).toBeInTheDocument()
    expect(screen.getByText('common.toast.types.warning')).toBeInTheDocument()
  })

  it('renders multiple toasts simultaneously', () => {
    useToastStore.setState({
      toasts: [
        { id: 'toast-a', type: 'success', message: 'First toast' },
        { id: 'toast-b', type: 'error', message: 'Second toast' },
        { id: 'toast-c', type: 'info', message: 'Third toast' },
      ],
    })
    render(<ToastContainer />)
    expect(screen.getByText('First toast')).toBeInTheDocument()
    expect(screen.getByText('Second toast')).toBeInTheDocument()
    expect(screen.getByText('Third toast')).toBeInTheDocument()
    expect(screen.getAllByRole('alert')).toHaveLength(3)
  })

  it('has aria-live="polite" on the container for screen readers', () => {
    useToastStore.setState({
      toasts: [{ id: 'toast-5', type: 'info', message: 'Accessible toast' }],
    })
    const { container } = render(<ToastContainer />)
    const liveRegion = container.firstElementChild as HTMLElement
    expect(liveRegion.getAttribute('aria-live')).toBe('polite')
  })

  it('has aria-atomic="true" on the container', () => {
    useToastStore.setState({
      toasts: [{ id: 'toast-6', type: 'info', message: 'Atomic toast' }],
    })
    const { container } = render(<ToastContainer />)
    const liveRegion = container.firstElementChild as HTMLElement
    expect(liveRegion.getAttribute('aria-atomic')).toBe('true')
  })

  it('each toast has role="alert"', () => {
    useToastStore.setState({
      toasts: [
        { id: 'toast-7', type: 'success', message: 'Alert one' },
        { id: 'toast-8', type: 'error', message: 'Alert two' },
      ],
    })
    render(<ToastContainer />)
    const alerts = screen.getAllByRole('alert')
    expect(alerts).toHaveLength(2)
  })

  it('dismisses a toast when the close button is clicked', () => {
    // Both toasts share the same priority bucket so the rendered order
    // matches the insertion order (createdAt tie-breaker).
    useToastStore.setState({
      toasts: [
        { id: 'toast-9', type: 'success', message: 'Will be dismissed', createdAt: 2 },
        { id: 'toast-10', type: 'success', message: 'Will remain', createdAt: 1 },
      ],
    })
    render(<ToastContainer />)
    expect(screen.getAllByRole('alert')).toHaveLength(2)

    // Click the first close button — newest same-priority toast surfaces first.
    const closeButtons = screen.getAllByLabelText('Close')
    fireEvent.click(closeButtons[0])

    // The dismissed toast should be removed from the store
    const { toasts } = useToastStore.getState()
    expect(toasts).toHaveLength(1)
    expect(toasts[0].message).toBe('Will remain')
  })

  it('close button has accessible aria-label', () => {
    useToastStore.setState({
      toasts: [{ id: 'toast-11', type: 'info', message: 'Toast with close button' }],
    })
    render(<ToastContainer />)
    expect(screen.getByLabelText('Close')).toBeInTheDocument()
  })

  it('renders success toast with checkmark SVG icon', () => {
    useToastStore.setState({
      toasts: [{ id: 'toast-12', type: 'success', message: 'Has checkmark' }],
    })
    const { container } = render(<ToastContainer />)
    expect(container.querySelector('.toast-success-icon')).toBeInTheDocument()
    expect(container.querySelector('.toast-success-icon svg')).toBeInTheDocument()
  })

  it('does not render checkmark icon for non-success toasts', () => {
    useToastStore.setState({
      toasts: [{ id: 'toast-13', type: 'info', message: 'No checkmark' }],
    })
    const { container } = render(<ToastContainer />)
    expect(container.querySelector('.toast-success-icon')).not.toBeInTheDocument()
  })

  describe('text wrapping for long Korean messages', () => {
    it('applies word-break: keep-all and overflow-wrap: anywhere to message', () => {
      useToastStore.setState({
        toasts: [
          {
            id: 'toast-wrap-1',
            type: 'info',
            message:
              '매우 긴 한국어 메시지가 한 줄로 넘치지 않고 자연스럽게 줄바꿈되어야 합니다. 이것은 토스트가 가로 스크롤을 만들지 않도록 보장하기 위함입니다.',
          },
        ],
      })
      render(<ToastContainer />)
      const messageEl = screen.getByText(/매우 긴 한국어 메시지/)
      expect(messageEl).toBeInTheDocument()
      // jsdom does not compute layout, but inline styles are observable.
      expect(messageEl).toHaveStyle({ wordBreak: 'keep-all' })
      expect(messageEl).toHaveStyle({ overflowWrap: 'anywhere' })
    })

    it('container drops the fixed 380px maxWidth and uses a responsive maxWidth', () => {
      useToastStore.setState({
        toasts: [{ id: 'toast-wrap-2', type: 'info', message: '짧은 메시지' }],
      })
      const { container } = render(<ToastContainer />)
      const liveRegion = container.firstElementChild as HTMLElement
      // jsdom drops unknown CSS functions like clamp() from style.width but keeps
      // calc() in maxWidth — so we assert on the responsive maxWidth fallback.
      const styleAttr = liveRegion.getAttribute('style') ?? ''
      expect(styleAttr).not.toMatch(/max-width:\s*380px/)
      expect(liveRegion.style.maxWidth).toContain('calc(100vw')
    })
  })

  describe('action button', () => {
    it('renders an action button when action is provided', () => {
      useToastStore.setState({
        toasts: [
          {
            id: 'toast-action-1',
            type: 'info',
            message: '메시지',
            action: { label: '실행', onAction: () => {} },
          },
        ],
      })
      render(<ToastContainer />)
      expect(screen.getByRole('button', { name: '실행' })).toBeInTheDocument()
    })

    it('does not render an action button when no action provided', () => {
      useToastStore.setState({
        toasts: [{ id: 'toast-action-2', type: 'info', message: '메시지' }],
      })
      render(<ToastContainer />)
      // Only one button (the close button) when no action
      expect(screen.getAllByRole('button')).toHaveLength(1)
    })

    it('calls onAction and closes the toast by default when action button is clicked', () => {
      const onAction = vi.fn()
      useToastStore.setState({
        toasts: [
          {
            id: 'toast-action-3',
            type: 'info',
            message: '메시지',
            action: { label: '실행', onAction },
          },
        ],
      })
      render(<ToastContainer />)
      fireEvent.click(screen.getByRole('button', { name: '실행' }))
      expect(onAction).toHaveBeenCalledTimes(1)
      expect(useToastStore.getState().toasts).toHaveLength(0)
    })

    it('keeps the toast when closeOnAction is false', () => {
      const onAction = vi.fn()
      useToastStore.setState({
        toasts: [
          {
            id: 'toast-action-4',
            type: 'info',
            message: '메시지',
            action: { label: '실행', onAction, closeOnAction: false },
          },
        ],
      })
      render(<ToastContainer />)
      fireEvent.click(screen.getByRole('button', { name: '실행' }))
      expect(onAction).toHaveBeenCalledTimes(1)
      expect(useToastStore.getState().toasts).toHaveLength(1)
    })

    it('action button uses font-weight 510', () => {
      useToastStore.setState({
        toasts: [
          {
            id: 'toast-action-5',
            type: 'info',
            message: '메시지',
            action: { label: '실행', onAction: () => {} },
          },
        ],
      })
      render(<ToastContainer />)
      const actionBtn = screen.getByRole('button', { name: '실행' })
      expect(actionBtn).toHaveStyle({ fontWeight: '510' })
    })
  })

  describe('default durations by type', () => {
    it('info toast defaults to 4000ms', () => {
      expect(getDefaultDuration('info', false)).toBe(4000)
    })
    it('success toast defaults to 4000ms', () => {
      expect(getDefaultDuration('success', false)).toBe(4000)
    })
    it('warning toast defaults to 6000ms', () => {
      expect(getDefaultDuration('warning', false)).toBe(6000)
    })
    it('error toast defaults to 8000ms', () => {
      expect(getDefaultDuration('error', false)).toBe(8000)
    })
    it('adds 2000ms when an action is present', () => {
      expect(getDefaultDuration('info', true)).toBe(6000)
      expect(getDefaultDuration('success', true)).toBe(6000)
      expect(getDefaultDuration('warning', true)).toBe(8000)
      expect(getDefaultDuration('error', true)).toBe(10000)
    })
  })

  describe('auto-dismiss with fake timers', () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })
    afterEach(() => {
      vi.useRealTimers()
    })

    it('info toast auto-dismisses after 4000ms', () => {
      act(() => {
        useToastStore.getState().addToast({ type: 'info', message: '정보' })
      })
      expect(useToastStore.getState().toasts).toHaveLength(1)
      act(() => {
        vi.advanceTimersByTime(3999)
      })
      expect(useToastStore.getState().toasts).toHaveLength(1)
      act(() => {
        vi.advanceTimersByTime(2)
      })
      expect(useToastStore.getState().toasts).toHaveLength(0)
    })

    it('error toast auto-dismisses after 8000ms', () => {
      act(() => {
        useToastStore.getState().addToast({ type: 'error', message: '에러' })
      })
      act(() => {
        vi.advanceTimersByTime(7999)
      })
      expect(useToastStore.getState().toasts).toHaveLength(1)
      act(() => {
        vi.advanceTimersByTime(2)
      })
      expect(useToastStore.getState().toasts).toHaveLength(0)
    })

    it('action presence extends duration by 2000ms', () => {
      act(() => {
        useToastStore.getState().addToast({
          type: 'info',
          message: '정보',
          action: { label: '실행', onAction: () => {} },
        })
      })
      // Default info=4000, with action=6000
      act(() => {
        vi.advanceTimersByTime(4500)
      })
      expect(useToastStore.getState().toasts).toHaveLength(1)
      act(() => {
        vi.advanceTimersByTime(2000)
      })
      expect(useToastStore.getState().toasts).toHaveLength(0)
    })

    it('explicit duration overrides type defaults', () => {
      act(() => {
        useToastStore.getState().addToast({
          type: 'error',
          message: '짧게',
          duration: 1000,
        })
      })
      act(() => {
        vi.advanceTimersByTime(1100)
      })
      expect(useToastStore.getState().toasts).toHaveLength(0)
    })
  })

  describe('pause-on-hover', () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })
    afterEach(() => {
      vi.useRealTimers()
    })

    it('pauses dismissal timer on mouseenter and resumes on mouseleave', () => {
      act(() => {
        useToastStore.getState().addToast({ type: 'info', message: '호버 테스트' })
      })
      render(<ToastContainer />)

      const toastEl = screen.getByRole('alert')

      // Advance halfway (2s of 4s)
      act(() => {
        vi.advanceTimersByTime(2000)
      })
      expect(useToastStore.getState().toasts).toHaveLength(1)

      // Hover to pause
      act(() => {
        fireEvent.mouseEnter(toastEl)
      })

      // Advance well past original expiry while paused
      act(() => {
        vi.advanceTimersByTime(10_000)
      })
      expect(useToastStore.getState().toasts).toHaveLength(1)

      // Leave to resume — remaining was ~2000ms
      act(() => {
        fireEvent.mouseLeave(toastEl)
      })

      act(() => {
        vi.advanceTimersByTime(1900)
      })
      expect(useToastStore.getState().toasts).toHaveLength(1)

      act(() => {
        vi.advanceTimersByTime(200)
      })
      expect(useToastStore.getState().toasts).toHaveLength(0)
    })
  })

  describe('queue overflow', () => {
    it('exposes MAX_VISIBLE_TOASTS = 5', () => {
      expect(MAX_VISIBLE_TOASTS).toBe(5)
    })

    it('renders only 5 toasts plus a "1 more" pill when 6 are queued', () => {
      const toasts = Array.from({ length: 6 }, (_, i) => ({
        id: `toast-overflow-${i}`,
        type: 'info' as const,
        message: `메시지 ${i + 1}`,
        createdAt: i + 1,
      }))
      useToastStore.setState({ toasts, expandQueue: false })

      render(<ToastContainer />)

      expect(screen.getAllByRole('alert')).toHaveLength(MAX_VISIBLE_TOASTS)
      const pill = screen.getByRole('button', { name: 'Show all' })
      expect(pill).toBeInTheDocument()
      expect(pill).toHaveTextContent('1 more')
    })

    it('does not render the overflow pill when 5 or fewer toasts are queued', () => {
      const toasts = Array.from({ length: MAX_VISIBLE_TOASTS }, (_, i) => ({
        id: `toast-fit-${i}`,
        type: 'info' as const,
        message: `메시지 ${i + 1}`,
        createdAt: i + 1,
      }))
      useToastStore.setState({ toasts, expandQueue: false })

      render(<ToastContainer />)

      expect(screen.getAllByRole('alert')).toHaveLength(MAX_VISIBLE_TOASTS)
      expect(screen.queryByRole('button', { name: 'Show all' })).not.toBeInTheDocument()
    })

    it('expands to render all toasts when the overflow pill is clicked', () => {
      const toasts = Array.from({ length: 8 }, (_, i) => ({
        id: `toast-expand-${i}`,
        type: 'info' as const,
        message: `메시지 ${i + 1}`,
        createdAt: i + 1,
      }))
      useToastStore.setState({ toasts, expandQueue: false })

      render(<ToastContainer />)

      expect(screen.getAllByRole('alert')).toHaveLength(MAX_VISIBLE_TOASTS)
      const pill = screen.getByRole('button', { name: 'Show all' })

      fireEvent.click(pill)

      expect(useToastStore.getState().expandQueue).toBe(true)
      expect(screen.getAllByRole('alert')).toHaveLength(8)
      expect(screen.getByRole('button', { name: 'Collapse' })).toBeInTheDocument()
    })

    it('priority sort surfaces error toasts first when types are mixed', () => {
      const toasts = [
        { id: 'a', type: 'success' as const, message: 's-1', createdAt: 1 },
        { id: 'b', type: 'info' as const, message: 'i-1', createdAt: 2 },
        { id: 'c', type: 'warning' as const, message: 'w-1', createdAt: 3 },
        { id: 'd', type: 'error' as const, message: 'e-1', createdAt: 4 },
        { id: 'e', type: 'success' as const, message: 's-2', createdAt: 5 },
        { id: 'f', type: 'info' as const, message: 'i-2', createdAt: 6 },
      ]
      useToastStore.setState({ toasts, expandQueue: false })

      const visible = selectVisibleToasts({ toasts })
      expect(visible[0].type).toBe('error')
      expect(visible[1].type).toBe('warning')
      // Within same priority, newest first.
      expect(visible[2].type).toBe('info')
      expect(visible[2].message).toBe('i-2')
      expect(visible[3].type).toBe('info')
      expect(visible[3].message).toBe('i-1')
      expect(visible[4].type).toBe('success')
      expect(visible[4].message).toBe('s-2')

      // Success s-1 should be the one pushed into overflow.
      expect(selectOverflowCount({ toasts })).toBe(1)
      const all = selectAllToastsSorted({ toasts })
      expect(all[all.length - 1].message).toBe('s-1')

      render(<ToastContainer />)
      const renderedAlerts = screen.getAllByRole('alert')
      expect(renderedAlerts).toHaveLength(MAX_VISIBLE_TOASTS)
      expect(renderedAlerts[0]).toHaveTextContent('e-1')
      expect(renderedAlerts[1]).toHaveTextContent('w-1')
    })

    it('collapses the expanded view when ESC is pressed', () => {
      const toasts = Array.from({ length: 7 }, (_, i) => ({
        id: `toast-esc-${i}`,
        type: 'info' as const,
        message: `메시지 ${i + 1}`,
        createdAt: i + 1,
      }))
      useToastStore.setState({ toasts, expandQueue: true })

      render(<ToastContainer />)

      // All 7 are visible while expanded.
      expect(screen.getAllByRole('alert')).toHaveLength(7)

      act(() => {
        fireEvent.keyDown(document, { key: 'Escape' })
      })

      expect(useToastStore.getState().expandQueue).toBe(false)
      expect(screen.getAllByRole('alert')).toHaveLength(MAX_VISIBLE_TOASTS)
    })

    it('overflow pill exposes aria-expanded reflecting state', () => {
      const toasts = Array.from({ length: 6 }, (_, i) => ({
        id: `toast-aria-${i}`,
        type: 'info' as const,
        message: `메시지 ${i + 1}`,
        createdAt: i + 1,
      }))
      useToastStore.setState({ toasts, expandQueue: false })

      render(<ToastContainer />)
      const pill = screen.getByRole('button', { name: 'Show all' })
      expect(pill.getAttribute('aria-expanded')).toBe('false')

      fireEvent.click(pill)

      const collapsePill = screen.getByRole('button', { name: 'Collapse' })
      expect(collapsePill.getAttribute('aria-expanded')).toBe('true')
    })
  })
})

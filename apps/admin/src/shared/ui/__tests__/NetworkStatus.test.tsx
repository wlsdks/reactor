import { describe, it, expect } from 'vitest'
import { render, screen, act } from '../../../test/utils'
import { NetworkStatus } from '../NetworkStatus'

describe('NetworkStatus', () => {
  it('renders nothing when online', () => {
    Object.defineProperty(navigator, 'onLine', { value: true, writable: true, configurable: true })
    const { container } = render(<NetworkStatus />)
    expect(container.firstChild).toBeNull()
  })

  it('shows banner when offline', () => {
    Object.defineProperty(navigator, 'onLine', { value: false, writable: true, configurable: true })
    render(<NetworkStatus />)
    expect(screen.getByText(/offline/i)).toBeInTheDocument()
    Object.defineProperty(navigator, 'onLine', { value: true, writable: true, configurable: true })
  })

  it('responds to offline event', () => {
    Object.defineProperty(navigator, 'onLine', { value: true, writable: true, configurable: true })
    render(<NetworkStatus />)
    expect(screen.queryByText(/offline/i)).not.toBeInTheDocument()

    act(() => {
      Object.defineProperty(navigator, 'onLine', { value: false, writable: true, configurable: true })
      window.dispatchEvent(new Event('offline'))
    })
    expect(screen.getByText(/offline/i)).toBeInTheDocument()

    act(() => {
      Object.defineProperty(navigator, 'onLine', { value: true, writable: true, configurable: true })
      window.dispatchEvent(new Event('online'))
    })
    expect(screen.queryByText(/offline/i)).not.toBeInTheDocument()
  })
})

import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { StatusBar } from '../ui/StatusBar'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'chatInspector.response_meta.success': 'Success',
        'chatInspector.response_meta.failed': 'Failed',
      }
      if (key === 'chatInspector.response_meta.duration') return `${opts?.ms}ms`
      if (key === 'chatInspector.response_meta.tokens') return `${opts?.count} tok`
      return map[key] ?? key
    },
  }),
}))

describe('StatusBar', () => {
  it('shows success badge when success is true', () => {
    render(<StatusBar success={true} />)
    expect(screen.getByText('Success')).toBeInTheDocument()
  })

  it('shows failed badge when success is false', () => {
    render(<StatusBar success={false} />)
    expect(screen.getByText('Failed')).toBeInTheDocument()
  })

  it('shows duration when provided', () => {
    render(<StatusBar success={true} durationMs={523} />)
    expect(screen.getByText('523ms')).toBeInTheDocument()
  })

  it('hides duration when null', () => {
    render(<StatusBar success={true} />)
    expect(screen.queryByText(/ms$/)).not.toBeInTheDocument()
  })

  it('shows formatted token count when provided', () => {
    render(<StatusBar success={true} totalTokens={1204} />)
    expect(screen.getByText('1,204 tok')).toBeInTheDocument()
  })

  it('hides token count when null', () => {
    render(<StatusBar success={true} />)
    expect(screen.queryByText(/tok$/)).not.toBeInTheDocument()
  })

  it('shows all badges together', () => {
    render(<StatusBar success={true} durationMs={100} totalTokens={500} />)
    expect(screen.getByText('Success')).toBeInTheDocument()
    expect(screen.getByText('100ms')).toBeInTheDocument()
    expect(screen.getByText('500 tok')).toBeInTheDocument()
  })
})

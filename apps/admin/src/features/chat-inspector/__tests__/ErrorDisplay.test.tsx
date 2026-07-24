import { describe, it, expect } from 'vitest'
import { render, screen } from '../../../test/utils'
import { ErrorDisplay } from '../ui/ErrorDisplay'

describe('ErrorDisplay', () => {
  it('keeps raw error code and message in collapsed technical details', () => {
    render(<ErrorDisplay errorCode="RATE_LIMITED" errorMessage="Rate limit exceeded" />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('chatInspector.errors.responseFailed')
    expect(alert).toHaveTextContent('chatInspector.errors.rateLimited')
    expect(alert).not.toHaveTextContent('RATE_LIMITED')
    expect(alert).not.toHaveTextContent('Rate limit exceeded')
    expect(screen.getByText('RATE_LIMITED').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('Rate limit exceeded').closest('details')).not.toHaveAttribute('open')
  })

  it('renders a localized timeout explanation for code-only failures', () => {
    render(<ErrorDisplay errorCode="TIMEOUT" errorMessage={null} />)
    expect(screen.getByRole('alert')).toHaveTextContent('chatInspector.errors.timeout')
    expect(screen.getByText('TIMEOUT').closest('details')).not.toHaveAttribute('open')
  })

  it('keeps an unclassified message outside the primary error announcement', () => {
    render(<ErrorDisplay errorCode={null} errorMessage="Something went wrong" />)
    expect(screen.getByRole('alert')).toHaveTextContent('chatInspector.errors.unknown')
    expect(screen.getByRole('alert')).not.toHaveTextContent('Something went wrong')
    expect(screen.getByText('Something went wrong').closest('details')).not.toHaveAttribute('open')
  })

  it('renders nothing when both are null', () => {
    const { container } = render(<ErrorDisplay errorCode={null} errorMessage={null} />)
    expect(container.firstChild).toBeNull()
  })
})

import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '../../../test/utils'
import { WorkspaceUnavailable } from '../WorkspaceUnavailable'

describe('WorkspaceUnavailable', () => {
  it('keeps technical recovery guidance collapsed and exposes one retry path', () => {
    const onRetry = vi.fn()
    render(
      <MemoryRouter>
        <WorkspaceUnavailable
          title="Unable to load jobs"
          description="The current counts are not verified."
          retryLabel="Try again"
          retryingLabel="Checking"
          onRetry={onRetry}
          secondaryAction={{ label: 'Open status', to: '/health' }}
          guide={{
            title: 'Resolve connection',
            steps: ['Check account', 'Check status', 'Retry'],
            technicalLabel: 'Technical detail',
            technicalDetail: 'HTTP 503',
          }}
        />
      </MemoryRouter>,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('Unable to load jobs')
    expect(screen.getByRole('link', { name: 'Open status' })).toHaveAttribute('href', '/health')
    expect(screen.getByText('Resolve connection').closest('details')).not.toHaveAttribute('open')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})

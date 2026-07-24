import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { render, screen } from '../../../test/utils'
import {
  RELEASE_LANGSMITH_SYNC_PATH,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
} from '../../releaseWorkflow'
import { ReleaseReportLink, ReleaseReportList, ReleaseReportMap } from '../ReleaseReportLink'

describe('ReleaseReportLink', () => {
  it('routes known release reports through the shared release resolver', () => {
    render(
      <MemoryRouter>
        <ReleaseReportLink report="langsmith_eval_sync" includeStep />
      </MemoryRouter>,
    )

    const link = screen.getByRole('link', {
      name: 'Open Langsmith Eval Sync',
    })
    expect(link).toHaveAttribute('href', RELEASE_LANGSMITH_SYNC_PATH)
    expect(link).toHaveClass('release-report-link')
    expect(link).not.toHaveTextContent('langsmith_eval_sync')
  })

  it('uses the reviewed-feedback label for the feedback promotion gate', () => {
    render(
      <MemoryRouter>
        <ReleaseReportLink report="feedback_promotion" includeStep />
      </MemoryRouter>,
    )

    const link = screen.getByRole('link', {
      name: 'Open Feedback promotion',
    })
    expect(link).toHaveTextContent('Feedback promotion')
    expect(link).not.toHaveTextContent('feedback_promotion')
  })

  it('renders unknown reports without creating a broken link', () => {
    render(
      <MemoryRouter>
        <ReleaseReportLink report="custom_internal_report" includeStep />
      </MemoryRouter>,
    )

    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('Connected check material')).toBeInTheDocument()
    expect(screen.queryByText('custom_internal_report')).not.toBeInTheDocument()
  })

  it('renders report lists and report file maps with shared step badges', () => {
    render(
      <MemoryRouter>
        <ReleaseReportList reports={['langsmith_eval_sync']} includeStep />
        <ReleaseReportMap reports={{ langsmith_eval_sync: 'reports/langsmith-eval-sync.json' }} includeStep />
      </MemoryRouter>,
    )

    const links = screen.getAllByRole('link', {
      name: 'Open Langsmith Eval Sync',
    })
    expect(links).toHaveLength(2)
    links.forEach((link) => {
      expect(link).toHaveAttribute('href', RELEASE_LANGSMITH_SYNC_PATH)
    })
    expect(screen.getByText(/reports\/langsmith-eval-sync\.json/)).toBeInTheDocument()
  })
})

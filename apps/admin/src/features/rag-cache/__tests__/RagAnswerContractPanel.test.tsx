import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../../../test/utils'
import { RagAnswerContractPanel } from '../ui/RagAnswerContractPanel'
import { RELEASE_WORKFLOW_PATHS_BY_ID } from '../../../shared/releaseWorkflow'

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    Link: ({ to, ...props }: React.ComponentProps<typeof actual.Link>) => (
      <a {...props} href={typeof to === 'string' ? to : String(to)} />
    ),
  }
})

const baseProps = {
  vectorStoreStats: { available: true, documentCount: 12 },
  ragPolicy: {
    configEnabled: true,
    dynamicEnabled: true,
    effective: {
      enabled: true,
      requireReview: true,
      allowedChannels: [],
      minQueryChars: 10,
      minResponseChars: 20,
      blockedPatterns: [],
    },
    stored: null,
  },
  pendingCandidatesCount: 2,
  statusStats: [{ status: 'APPROVED', count: 3 }],
  releaseRagEvidence: {
    status: 'verified',
    vectorStore: 'PGVector',
    researchAnswerContract: {
      citationStyle: 'manifest_ids',
      requiresCitationIds: true,
      uncitedClaimsAllowed: false,
    },
  },
  onJumpToCandidates: vi.fn(),
}

describe('RagAnswerContractPanel', () => {
  it('presents one compact answer summary with direct actions', () => {
    render(<RagAnswerContractPanel {...baseProps} />)

    expect(screen.getByRole('heading', { name: 'ragCachePage.answerContract.operatorTitle' })).toBeInTheDocument()
    expect(screen.getByText('ragCachePage.answerContract.prepareDocuments')).toBeInTheDocument()
    expect(screen.getByText('ragCachePage.answerContract.reviewWeakAnswers')).toBeInTheDocument()
    expect(screen.queryByText('Readiness 집계')).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'ragCachePage.answerContract.openDocuments' })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.ingest,
    )
  })

  it('keeps technical release evidence collapsed and preserves the review action', async () => {
    const user = userEvent.setup()
    const onJumpToCandidates = vi.fn()
    render(<RagAnswerContractPanel {...baseProps} onJumpToCandidates={onJumpToCandidates} />)

    const details = screen.getByText('ragCachePage.answerContract.technicalDetails').closest('details')
    expect(details).not.toHaveAttribute('open')
    await user.click(screen.getByRole('button', { name: 'ragCachePage.answerContract.openReviewQueue' }))
    expect(onJumpToCandidates).toHaveBeenCalledTimes(1)
  })

  it('explains unavailable search without exposing raw contract names', () => {
    render(
      <RagAnswerContractPanel
        {...baseProps}
        vectorStoreStats={{ available: false, documentCount: 0 }}
        releaseRagEvidence={null}
      />,
    )

    expect(screen.getByText('ragCachePage.answerContract.checkAnswerBlocked')).toBeInTheDocument()
    expect(screen.queryByText('ragIngestionLifecycle')).not.toBeInTheDocument()
  })
})

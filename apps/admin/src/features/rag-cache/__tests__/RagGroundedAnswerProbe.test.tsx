import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { i18n, render, screen, waitFor } from '../../../test/utils'
import * as ragCacheApi from '../api'
import type { RagAnswerProbeResult } from '../types'
import { RagGroundedAnswerProbe } from '../ui/RagGroundedAnswerProbe'

vi.mock('../api', () => ({
  askGroundedRag: vi.fn(),
  promoteWeakRagAnswer: vi.fn(),
}))

const askGroundedRagMock = vi.mocked(ragCacheApi.askGroundedRag)
const promoteWeakRagAnswerMock = vi.mocked(ragCacheApi.promoteWeakRagAnswer)

function renderProbe(initialEntry = '/rag-cache?tab=rag') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <RagGroundedAnswerProbe />
    </MemoryRouter>,
  )
}

function probeResult(overrides: Partial<RagAnswerProbeResult> = {}): RagAnswerProbeResult {
  return {
    query: 'What is the release policy?',
    content: 'The release policy requires citations [doc_policy:0].',
    success: true,
    status: 'grounded',
    runId: 'run-grounded-1',
    model: 'ollama:gemma4:12b',
    durationMs: 120,
    grounded: true,
    evidenceStatus: 'grounded',
    citationIds: ['doc_policy:0'],
    sourceLabels: ['policy://release'],
    missingEvidence: [],
    operatorAction: null,
    blockReason: null,
    retrievalSummary: {
      ragToolResultCount: 1,
      chunkCount: 2,
      citationCount: 1,
      citationStatus: 'grounded',
    },
    answerExtraction: {
      status: 'available',
      matchedCitationCount: 1,
      hashMismatchCount: 0,
      missingChunkCount: 0,
    },
    recoverySteps: [],
    answerContract: {
      status: 'grounded',
      citationIds: ['doc_policy:0'],
      sourceLabels: ['policy://release'],
      citationStyle: 'manifest_ids',
      uncitedClaimsAllowed: false,
    },
    ...overrides,
  }
}

describe('RagGroundedAnswerProbe', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.addResourceBundle('en', 'translation', {
      'ragCachePage.answerProbe.title': 'Grounded answer probe',
      'ragCachePage.answerProbe.description': 'Check an answer with its sources.',
      'ragCachePage.answerProbe.question': 'Question',
      'ragCachePage.answerProbe.placeholder': 'Ask indexed documents...',
      'ragCachePage.answerProbe.run': 'Run grounded answer',
      'ragCachePage.answerProbe.result': 'Grounded answer result',
      'ragCachePage.answerProbe.status.grounded': 'Grounded',
      'ragCachePage.answerProbe.status.weak': 'Weak evidence',
      'ragCachePage.answerProbe.status.failed': 'Failed',
      'ragCachePage.answerProbe.missingRunId': 'Missing run ID',
      'ragCachePage.answerProbe.evidenceStatus': 'Evidence status',
      'ragCachePage.answerProbe.citationIds': 'Citation IDs',
      'ragCachePage.answerProbe.sourceLabels': 'Source labels',
      'ragCachePage.answerProbe.sourceLabel': 'Source document {{index}}',
      'ragCachePage.answerProbe.citationStyle': 'Citation style',
      'ragCachePage.answerProbe.uncitedClaims': 'Uncited claims',
      'ragCachePage.answerProbe.allowed': 'Allowed',
      'ragCachePage.answerProbe.blocked': 'Blocked',
      'ragCachePage.answerProbe.missingEvidence': 'Missing evidence',
      'ragCachePage.answerProbe.operatorAction': 'Operator action',
      'ragCachePage.answerProbe.expectedDocument': 'Expected document',
      'ragCachePage.answerProbe.expectedDocumentMatched': 'Expected document cited',
      'ragCachePage.answerProbe.expectedDocumentMismatch': 'Expected document not cited',
      'ragCachePage.answerProbe.retrievedChunks': 'Retrieved chunks',
      'ragCachePage.answerProbe.matchedCitations': 'Matched citations',
      'ragCachePage.answerProbe.hashMismatches': 'Hash mismatches',
      'ragCachePage.answerProbe.missingChunks': 'Missing chunks',
      'ragCachePage.answerProbe.citationEvidence': 'Citation evidence',
      'ragCachePage.answerProbe.citationMarker': 'Reference {{index}}',
      'ragCachePage.answerProbe.unverifiedCitation': 'Source needs review',
      'ragCachePage.answerProbe.sourceEvidence': 'Source evidence',
      'ragCachePage.answerProbe.recoverySteps': 'Recovery steps',
      'ragCachePage.answerProbe.promote': 'Send weak answer to feedback review',
      'ragCachePage.answerProbe.promoted': '{{feedbackId}} entered {{status}} review.',
      'ragCachePage.answerProbe.openFeedback': 'Open feedback review',
      'ragCachePage.answerProbe.technicalDetails': 'Developer result details',
    }, true, true)
  })

  it('shows human-readable citations first and keeps raw evidence in a closed disclosure', async () => {
    askGroundedRagMock.mockResolvedValue(probeResult())
    const user = userEvent.setup()
    renderProbe()

    await user.type(screen.getByLabelText('Question'), 'What is the release policy?')
    await user.click(screen.getByRole('button', { name: 'Run grounded answer' }))

    await waitFor(() => expect(screen.getByText('Grounded')).toBeInTheDocument())
    expect(screen.getByText('The release policy requires citations [Reference 1].')).toBeInTheDocument()
    expect(screen.getByText('Source document 1')).toBeInTheDocument()
    const details = screen.getByText('Developer result details').closest('details')
    expect(details).not.toHaveAttribute('open')
    expect(screen.getAllByText('doc_policy:0')[0]).not.toBeVisible()
    expect(screen.getByText('policy://release')).not.toBeVisible()
    await user.click(screen.getByText('Developer result details'))
    expect(screen.getByText('run-grounded-1')).toBeInTheDocument()
    expect(screen.getAllByText('doc_policy:0')).toHaveLength(2)
    expect(screen.getByText('manifest_ids')).toBeInTheDocument()
    expect(screen.getByText('Blocked')).toBeInTheDocument()
    expect(screen.getByText('Grounded')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('1/1')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send weak answer to feedback review' })).not.toBeInTheDocument()
  })

  it('checks the expected ingested document against actual citation evidence', async () => {
    const result = probeResult()
    askGroundedRagMock.mockResolvedValue(result)
    promoteWeakRagAnswerMock.mockResolvedValue({
      feedbackId: 'fb-source-mismatch',
      reviewStatus: 'inbox',
      runId: 'run-grounded-1',
      nextActionIds: ['promote-eval-case'],
    })
    const user = userEvent.setup()
    renderProbe('/rag-cache?tab=rag&question=What+is+the+release+policy%3F&expectedDocumentId=other-document')

    expect(screen.getByLabelText('Question')).toHaveValue('What is the release policy?')
    await user.click(screen.getByRole('button', { name: 'Run grounded answer' }))

    expect(await screen.findByText('Expected document not cited')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Send weak answer to feedback review' }))
    await waitFor(() => expect(promoteWeakRagAnswerMock).toHaveBeenCalledWith(result, {
      expectedDocumentId: 'other-document',
    }))
  })

  it('submits weak answer provenance to the feedback promotion workflow', async () => {
    const weakResult = probeResult({
      content: 'Evidence is unavailable.',
      status: 'weak',
      grounded: false,
      evidenceStatus: 'missing',
      citationIds: [],
      sourceLabels: [],
      missingEvidence: ['rag_citations'],
      operatorAction: 'retry_with_grounded_rag',
      answerContract: null,
    })
    askGroundedRagMock.mockResolvedValue(weakResult)
    promoteWeakRagAnswerMock.mockResolvedValue({
      feedbackId: 'fb-weak-1',
      reviewStatus: 'inbox',
      runId: 'run-grounded-1',
      nextActionIds: ['promote-eval-case'],
    })
    const user = userEvent.setup()
    renderProbe()

    await user.type(screen.getByLabelText('Question'), 'What is missing?')
    await user.click(screen.getByRole('button', { name: 'Run grounded answer' }))
    await user.click(await screen.findByRole('button', { name: 'Send weak answer to feedback review' }))

    await waitFor(() => expect(promoteWeakRagAnswerMock).toHaveBeenCalledWith(weakResult))
    expect(screen.getByRole('status')).toHaveTextContent('fb-weak-1 entered inbox review.')
    expect(screen.getByRole('link', { name: 'Open feedback review' })).toHaveAttribute(
      'href',
      '/feedback#feedback-promotion',
    )
  })
})

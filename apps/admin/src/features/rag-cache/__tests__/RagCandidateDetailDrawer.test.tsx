import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen, i18n } from '../../../test/utils'
import { RagCandidateDetailDrawer } from '../ui/RagCandidateDetailDrawer'
import type { RagCandidate } from '../types'

function buildCandidate(overrides: Partial<RagCandidate> = {}): RagCandidate {
  return {
    id: 'candidate-1',
    runId: 'run-1',
    query: 'What changed in release readiness?',
    response: 'The answer is weak without citations.',
    channel: 'slack',
    status: 'PENDING',
    capturedAt: 1783434726000,
    nextActions: [],
    ...overrides,
  }
}

describe('RagCandidateDetailDrawer', () => {
  it('keeps candidate decisions readable and release evidence closed', async () => {
    i18n.addResourceBundle(
      'en',
      'translation',
      {
        'ragCachePage.candidates.title': 'Answer review',
        'ragCachePage.candidates.detailDescription': 'Review the question and answer before making a decision.',
        'ragCachePage.candidates.query': 'User question',
        'ragCachePage.candidates.response': 'Answer',
        'ragCachePage.candidates.nextChecks': 'Additional checks',
        'ragCachePage.candidates.nextChecksDescription': 'Check these operating conditions before approval.',
        'ragCachePage.candidates.actionKind.sync': 'Check evaluation data sync',
        'ragCachePage.candidates.actionKind.readiness': 'Check release readiness',
        'ragCachePage.candidates.actionKind.review': 'Check the operating decision',
        'ragCachePage.candidates.actionState.ready': 'Ready for review',
        'ragCachePage.candidates.actionState.blocked': 'Action needed',
        'ragCachePage.candidates.actionState.pending': 'Waiting for review',
        'ragCachePage.candidates.technicalDetails': 'Developer details',
        'ragCachePage.candidates.candidateId': 'Candidate ID',
        'ragCachePage.candidates.sourceRun': 'Source run',
        'ragCachePage.candidates.ingestedDocument': 'Ingested document',
        'ragCachePage.candidates.actionId': 'Action ID',
        'ragCachePage.candidates.actionLabel': 'Original action label',
        'ragCachePage.candidates.runbook': 'Runbook',
        'ragCachePage.candidates.runbookCommand': 'Run command',
        'ragCachePage.candidates.runbookRemediation': 'Remediation command',
        'ragCachePage.candidates.runbookEnv': 'Env command',
        'ragCachePage.candidates.runbookReadiness': 'Readiness command',
        'ragCachePage.candidates.dataset': 'Dataset',
        'ragCachePage.candidates.caseFile': 'Case file',
        'ragCachePage.candidates.runFile': 'Run file',
        'ragCachePage.candidates.reportFile': 'Report file',
        'ragCachePage.candidates.diagnosticsApi': 'Diagnostics API',
        'ragCachePage.candidates.readinessFile': 'Readiness file',
        'ragCachePage.candidates.requiredReadinessReports': 'Required readiness reports',
        'ragCachePage.candidates.readinessReports': 'Readiness reports',
        'ragCachePage.candidates.minorBoundaryReports': 'Minor boundary reports',
        'ragCachePage.candidates.promotionCoverage': 'Promotion coverage',
        'ragCachePage.candidates.citationMarkerContract': 'Citation marker contract',
        'ragCachePage.candidates.approve': 'Approve',
        'ragCachePage.candidates.reject': 'Reject',
        'ragCachePage.candidates.statusLabels.pending': 'Pending',
      },
      true,
      true,
    )

    const user = userEvent.setup()
    render(
      <RagCandidateDetailDrawer
        candidate={buildCandidate({
          readyNextActionIds: ['sync-case'],
          blockedNextActionIds: ['run-readiness'],
          nextActionStates: {
            'sync-case': 'ready',
            'run-readiness': 'blocked',
          },
          nextActions: [
            {
              id: 'sync-case',
              label: 'Sync promoted RAG case',
              sourceRunId: 'run-candidate-1',
              datasetName: 'reactor-release-regression',
              caseFile: 'evals/cases/rag.yaml',
              runFile: 'reports/eval-run.json',
              diagnosticsApi: '/admin/rag/candidates/candidate-1/diagnostics',
              reportFile: 'langsmith_eval_sync',
              evalCaseId: 'case_rag_candidate_grounded_citation',
              command: 'reactor-documents ask --collection rag-ingestion-candidate --output summary',
              remediationCommand: 'uv run reactor-langsmith-eval-sync --preflight-only',
              envFileCommand: 'printf LANGSMITH_API_KEY=...',
              releaseReadinessCommand:
                'reactor-release-smoke-run --readiness-output reports/release-readiness.json',
            },
            {
              id: 'run-readiness',
              label: 'Regenerate release readiness',
              releaseReadinessCommand:
                'reactor-release-smoke-run --readiness-output reports/release-readiness.json',
              releaseReadinessFile: 'reports/release-readiness.json',
            },
          ],
        })}
        onClose={vi.fn()}
        onRequestApprove={vi.fn()}
        onRequestReject={vi.fn()}
        approvePending={false}
        rejectPending={false}
      />,
    )

    expect(screen.getByText('Answer review')).toBeInTheDocument()
    expect(screen.getByText('What changed in release readiness?')).toBeInTheDocument()
    expect(screen.getByText('The answer is weak without citations.')).toBeInTheDocument()
    expect(screen.getByText('Check evaluation data sync')).toBeInTheDocument()
    expect(screen.getByText('Check release readiness')).toBeInTheDocument()
    expect(screen.getByText('Ready for review')).toBeInTheDocument()
    expect(screen.getByText('Action needed')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()

    const details = screen.getByText('Developer details').closest('details')
    expect(details).not.toHaveAttribute('open')
    expect(screen.getByText('sync-case')).not.toBeVisible()
    expect(screen.getByText('Sync promoted RAG case')).not.toBeVisible()
    expect(screen.getByText('reactor-release-regression')).not.toBeVisible()

    await user.click(screen.getByText('Developer details'))

    expect(screen.getByText('sync-case')).toBeVisible()
    expect(screen.getByText('run-readiness')).toBeVisible()
    expect(screen.getByText('Sync promoted RAG case')).toBeVisible()
    expect(screen.getByText('reactor-release-regression')).toBeVisible()
    expect(screen.getByText('evals/cases/rag.yaml')).toBeVisible()
    expect(screen.getByText('reports/eval-run.json')).toBeVisible()
    expect(screen.getByText('/admin/rag/candidates/candidate-1/diagnostics')).toBeVisible()
    expect(screen.getAllByLabelText('Runbook')).toHaveLength(2)
  })
})

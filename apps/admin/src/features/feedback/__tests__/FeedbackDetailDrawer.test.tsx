import { describe, expect, it, vi } from 'vitest'
import { render, screen, i18n } from '../../../test/utils'
import { FeedbackDetailDrawer } from '../ui/FeedbackDetailDrawer'
import {
  RELEASE_LANGSMITH_SYNC_PATH,
} from '../../../shared/releaseWorkflow'
import type { FeedbackEntry } from '../types'

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    Link: ({ to, ...props }: React.ComponentProps<typeof actual.Link>) => (
      <a {...props} href={typeof to === 'string' ? to : String(to)} data-router-link="true" />
    ),
  }
})

function buildFeedbackEntry(overrides: Partial<FeedbackEntry> = {}): FeedbackEntry {
  return {
    feedbackId: 'feedback-1',
    query: 'Why is the answer weak?',
    response: 'The answer did not cite sources.',
    rating: 'thumbs_down',
    timestamp: '2026-07-07T00:00:00Z',
    comment: null,
    runId: 'run-1',
    intent: null,
    domain: null,
    model: null,
    promptVersion: null,
    toolsUsed: null,
    durationMs: null,
    tags: null,
    templateId: null,
    reviewStatus: 'done',
    reviewTags: [],
    reviewedBy: null,
    reviewedAt: null,
    reviewNote: null,
    version: 1,
    updatedAt: '2026-07-07T00:00:00Z',
    ...overrides,
  }
}

describe('FeedbackDetailDrawer', () => {
  it('shows release handoff actions that only carry metadata evidence', () => {
    i18n.addResourceBundle(
      'en',
      'translation',
      {
        'feedbackPage.releaseHandoff': 'Release handoff',
        'feedbackPage.actionState': 'Action state',
        'feedbackPage.actionStateLabels.ready': 'Ready to process',
        'feedbackPage.actionStateLabels.blocked': 'Blocked',
        'feedbackPage.runbook': 'Runbook',
        'feedbackPage.runbookCommand': 'Run command',
        'feedbackPage.runbookRemediation': 'Remediation command',
        'feedbackPage.runbookEnv': 'Env command',
        'feedbackPage.runbookReadiness': 'Readiness command',
        'feedbackPage.run': 'Run',
        'feedbackPage.runAvailable': 'Linked',
        'feedbackPage.feedbackId': 'Feedback identifier',
        'feedbackPage.selectedTitle': 'Selected feedback',
        'feedbackPage.columns.created': 'Created',
        'feedbackPage.query': 'Query',
        'feedbackPage.response': 'Response',
        'feedbackPage.metadata': 'Metadata',
        'feedbackPage.sourceRun': 'Source run',
        'feedbackPage.dataset': 'Dataset',
        'feedbackPage.caseFile': 'Case file',
        'feedbackPage.runFile': 'Run file',
        'feedbackPage.reportFile': 'Report file',
        'feedbackPage.diagnosticsApi': 'Diagnostics API',
        'feedbackPage.openFeedbackPromotion': 'Open feedback promotion',
        'feedbackPage.openLangsmithSync': 'Open LangSmith sync',
        'nav.releaseCockpit': 'Release cockpit',
        'feedbackPage.requiredReadinessReports': 'Required readiness reports',
        'feedbackPage.readinessReports': 'Readiness reports',
        'feedbackPage.minorBoundaryReports': 'Minor boundary reports',
        'feedbackPage.ratingLabels.thumbsDown': 'Thumbs down',
        'feedbackPage.statusLabels.done': 'Done',
        'feedbackPage.review.title': 'Review',
        'feedbackPage.review.status': 'Status',
        'feedbackPage.review.statusInbox': 'Inbox',
        'feedbackPage.review.statusDone': 'Done',
        'feedbackPage.review.tags': 'Tags',
        'feedbackPage.review.note': 'Review note',
        'feedbackPage.review.notePlaceholder': 'Review note',
      },
      true,
      true,
    )

    render(
      <FeedbackDetailDrawer
        isLoading={false}
        selected={buildFeedbackEntry({
          blockedNextActionIds: ['rerun-readiness'],
          nextActionStates: {
            'promote-case': 'ready',
          },
          nextActions: [
            {
              id: 'promote-case',
              label: 'Promote weak answer to eval',
              evalCaseId: 'case_feedback_weak_answer',
              sourceRunId: 'run-feedback-1',
              datasetName: 'reactor-release-regression',
              caseFile: 'evals/cases/rag.yaml',
              runFile: 'reports/eval-run.json',
              diagnosticsApi: '/admin/rag/candidates/candidate-1/diagnostics',
              reportFile: 'langsmith_eval_sync',
              requiredReadinessReports: ['langsmith_eval_sync'],
              readinessReports: {
                langsmith_eval_sync: 'reports/langsmith-eval-sync.json',
              },
              command: 'reactor-admin feedback-export --rating thumbs_down --output json',
              remediationCommand: 'uv run reactor-langsmith-eval-sync --preflight-only',
              envFileCommand: 'printf LANGSMITH_API_KEY=...',
              releaseReadinessCommand:
                'reactor-release-smoke-run --readiness-output reports/release-readiness.json',
              minorBoundaryReports: ['langsmith_eval_sync'],
            },
            {
              id: 'rerun-readiness',
              label: 'Rerun release readiness after sync',
              releaseReadinessFile: 'reports/release-readiness.json',
            },
          ],
        })}
        onClose={vi.fn()}
        onDelete={vi.fn()}
      />,
    )

    expect(screen.getByText('Release handoff')).toBeInTheDocument()
    expect(screen.getByText('promote-case')).toBeInTheDocument()
    expect(screen.getByText('Ready to process')).toBeInTheDocument()
    expect(screen.getByText('rerun-readiness')).toBeInTheDocument()
    expect(screen.getByText('Blocked')).toBeInTheDocument()
    expect(screen.getByText('Promote weak answer to eval')).toBeInTheDocument()
    expect(screen.getByText('Rerun release readiness after sync')).toBeInTheDocument()
    expect(screen.getByText('run-feedback-1')).toBeInTheDocument()
    expect(screen.getByText('reactor-release-regression')).toBeInTheDocument()
    expect(screen.getByText('evals/cases/rag.yaml')).toBeInTheDocument()
    expect(screen.getByText('reports/eval-run.json')).toBeInTheDocument()
    expect(screen.getByText('Diagnostics API')).toBeInTheDocument()
    expect(screen.getByText('/admin/rag/candidates/candidate-1/diagnostics')).toBeInTheDocument()
    expect(screen.getAllByLabelText('Runbook')).toHaveLength(1)
    expect(screen.getByText('Run command')).toBeInTheDocument()
    expect(screen.getByText('reactor-admin feedback-export --rating thumbs_down --output json')).toBeInTheDocument()
    expect(screen.getByText('Remediation command')).toBeInTheDocument()
    expect(screen.getByText('uv run reactor-langsmith-eval-sync --preflight-only')).toBeInTheDocument()
    expect(screen.getByText('Env command')).toBeInTheDocument()
    expect(screen.getByText('printf LANGSMITH_API_KEY=...')).toBeInTheDocument()
    expect(screen.getAllByText('Readiness command').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' })).not.toBeInTheDocument()
    expect(document.querySelectorAll('details.feedback-technical-details')).toHaveLength(3)
    const reportLinks = screen.getAllByRole('link', {
      name: 'Open Langsmith Eval Sync',
    })
    expect(reportLinks.length).toBeGreaterThanOrEqual(3)
    reportLinks.forEach((link) => {
      expect(link).toHaveAttribute('href', RELEASE_LANGSMITH_SYNC_PATH)
      expect(link).toHaveAttribute('data-router-link', 'true')
      expect(link).toHaveTextContent('Langsmith Eval Sync')
    })
  })
})

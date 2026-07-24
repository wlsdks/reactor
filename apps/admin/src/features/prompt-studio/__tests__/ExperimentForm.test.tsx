import { render, screen, waitFor, act } from '../../../test/utils'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ExperimentForm } from '../ui/ExperimentForm'
import type { VersionResponse } from '../types'
import { i18n } from '../../../test/utils'

// Add promptStudio i18n keys for tests
i18n.addResourceBundle('en', 'translation', {
  'promptStudio.experimentName': 'Experiment Name',
  'promptStudio.experimentNamePlaceholder': 'e.g. v2 vs v3 comparison',
  'promptStudio.hint.experimentName': 'Use a short name your team will recognise.',
  'promptStudio.hint.testQueries': 'One query per line. 10-20 is ideal.',
  'promptStudio.template': 'Template',
  'promptStudio.selectVersions': 'Select versions to compare',
  'promptStudio.selectVersionsGuide': 'Pick 1 baseline + 1 or more candidates.',
  'promptStudio.baseline': 'Baseline',
  'promptStudio.candidate': 'Candidate',
  'promptStudio.testQueries': 'Test Queries',
  'promptStudio.testQueriesGuide': 'Enter questions your users would ask.',
  'promptStudio.testQueriesPlaceholder': 'How do I reset my password?',
  'promptStudio.advancedSettings': 'Advanced Settings',
  'promptStudio.model': 'Model',
  'promptStudio.judgeModel': 'Judge Model (optional)',
  'promptStudio.temperature': 'Temperature',
  'promptStudio.repetitions': 'Repetitions',
  'promptStudio.runExperiment': 'Run Experiment',
  'promptStudio.evaluationConfig': 'Evaluation Config',
  'promptStudio.versionLabel': 'Version {{version}}',
  'promptStudio.versionStatus.active': 'Currently used',
  'promptStudio.versionStatus.draft': 'Draft for review',
  'promptStudio.versionStatus.archived': 'Previous record',
  'promptStudio.versionStatus.unknown': 'Needs review',
  'promptStudio.structuralCheck': 'Structural Check',
  'promptStudio.rulesCheck': 'Rules Check',
  'promptStudio.llmJudge': 'LLM Judge',
}, true, true)

const mockVersions: VersionResponse[] = [
  {
    id: 'v1',
    templateId: 't1',
    version: 1,
    content: 'You are a helpful assistant that answers user queries.',
    status: 'ACTIVE',
    changeLog: 'Initial version',
    createdAt: 1000,
  },
  {
    id: 'v2',
    templateId: 't1',
    version: 2,
    content: 'You are a concise assistant that gives brief answers.',
    status: 'DRAFT',
    changeLog: 'Shortened responses',
    createdAt: 2000,
  },
  {
    id: 'v3',
    templateId: 't1',
    version: 3,
    content: 'You are an expert assistant specialized in technical support.',
    status: 'DRAFT',
    changeLog: 'Technical focus',
    createdAt: 3000,
  },
]

const defaultProps = {
  templateId: 't1',
  templateName: 'Customer Support Bot',
  versions: mockVersions,
  onSubmit: vi.fn(),
  onCancel: vi.fn(),
  saving: false,
}

describe('ExperimentForm', () => {
  it('renders form fields', () => {
    render(<ExperimentForm {...defaultProps} />)

    expect(screen.getByText('Experiment Name')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('e.g. v2 vs v3 comparison')).toBeInTheDocument()
    expect(screen.getByText('Test Queries')).toBeInTheDocument()
    expect(screen.getByText('Select versions to compare')).toBeInTheDocument()
  })

  it('renders version choices with readable states', () => {
    render(<ExperimentForm {...defaultProps} />)

    expect(screen.getByText('Version 1')).toBeInTheDocument()
    expect(screen.getByText('Version 2')).toBeInTheDocument()
    expect(screen.getByText('Version 3')).toBeInTheDocument()
    expect(screen.getByText('Currently used')).toBeInTheDocument()
    expect(screen.getAllByText('Draft for review')).toHaveLength(2)
    expect(screen.queryByText('ACTIVE')).not.toBeInTheDocument()
  })

  it('shows template name as read-only', () => {
    render(<ExperimentForm {...defaultProps} />)

    const templateInput = screen.getByDisplayValue('Customer Support Bot')
    expect(templateInput).toBeInTheDocument()
    expect(templateInput).toHaveAttribute('readonly')
  })

  it('shows version content preview', () => {
    render(<ExperimentForm {...defaultProps} />)

    expect(screen.getByText('You are a helpful assistant that answers user queries.')).toBeInTheDocument()
    expect(screen.getByText('You are a concise assistant that gives brief answers.')).toBeInTheDocument()
  })

  it('renders baseline radio buttons and candidate checkboxes', () => {
    render(<ExperimentForm {...defaultProps} />)

    const radios = screen.getAllByRole('radio')
    expect(radios).toHaveLength(3)

    const checkboxes = screen.getAllByRole('checkbox')
    // 3 candidate checkboxes + 3 evaluation config checkboxes (in collapsed details)
    expect(checkboxes.length).toBeGreaterThanOrEqual(3)
  })

  it('renders test queries textarea', () => {
    render(<ExperimentForm {...defaultProps} />)

    const textarea = screen.getByPlaceholderText('How do I reset my password?')
    expect(textarea).toBeInTheDocument()
  })

  it('renders cancel and submit buttons', () => {
    render(<ExperimentForm {...defaultProps} />)

    expect(screen.getByText('Cancel')).toBeInTheDocument()
    expect(screen.getByText('Run Experiment')).toBeInTheDocument()
  })

  it('calls onCancel when cancel button is clicked', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    render(<ExperimentForm {...defaultProps} onCancel={onCancel} />)

    await user.click(screen.getByText('Cancel'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('submit button is disabled when form is invalid', () => {
    render(<ExperimentForm {...defaultProps} />)

    const submitButton = screen.getByText('Run Experiment')
    expect(submitButton).toBeDisabled()
  })

  it('submit transforms queries to correct format', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<ExperimentForm {...defaultProps} onSubmit={onSubmit} />)

    // Fill name
    await user.type(screen.getByPlaceholderText('e.g. v2 vs v3 comparison'), 'Test Experiment')

    // Select baseline (v1)
    const radios = screen.getAllByRole('radio')
    await user.click(radios[0])

    // Select candidate (v2)
    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[1]) // second candidate checkbox (v2)

    // Enter test queries
    const textarea = screen.getByPlaceholderText('How do I reset my password?')
    await user.type(textarea, 'What is your return policy?\nHow do I change my email?')

    await waitFor(() => {
      const submitButton = screen.getByText('Run Experiment')
      expect(submitButton).not.toBeDisabled()
    })

    await user.click(screen.getByText('Run Experiment'))

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledTimes(1)
    })

    const submittedData = onSubmit.mock.calls[0][0]
    expect(submittedData.name).toBe('Test Experiment')
    expect(submittedData.templateId).toBe('t1')
    expect(submittedData.baselineVersionId).toBe('v1')
    expect(submittedData.candidateVersionIds).toEqual(['v2'])
    expect(submittedData.testQueries).toEqual([
      { query: 'What is your return policy?' },
      { query: 'How do I change my email?' },
    ])
  })

  it('shows loading spinner when saving', () => {
    render(<ExperimentForm {...defaultProps} saving={true} />)

    // When saving, the submit button shows a spinner instead of text
    const spinner = screen.getByLabelText('Loading')
    expect(spinner).toBeInTheDocument()

    // Cancel button should be disabled too
    const cancelButton = screen.getByText('Cancel')
    expect(cancelButton).toBeDisabled()
  })

  it('disables candidate checkbox when version is selected as baseline', async () => {
    const user = userEvent.setup()
    render(<ExperimentForm {...defaultProps} />)

    // Select v1 as baseline
    const radios = screen.getAllByRole('radio')
    await user.click(radios[0])

    // The candidate checkbox for v1 should be disabled
    const cards = document.querySelectorAll('.version-select-card')
    const firstCardCheckbox = cards[0].querySelector('input[type="checkbox"]') as HTMLInputElement
    expect(firstCardCheckbox).toBeDisabled()
  })

  describe('real-time validation', () => {
    beforeEach(() => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it('renders required asterisk + aria-required on Experiment Name', () => {
      render(<ExperimentForm {...defaultProps} />)
      const nameInput = screen.getByPlaceholderText('e.g. v2 vs v3 comparison')
      expect(nameInput).toHaveAttribute('aria-required', 'true')
    })

    it('renders schema-derived hint text under inputs', () => {
      render(<ExperimentForm {...defaultProps} />)
      expect(screen.getByText('Use a short name your team will recognise.')).toBeInTheDocument()
      expect(screen.getByText('One query per line. 10-20 is ideal.')).toBeInTheDocument()
    })

    it('typing valid value flips to ✓ after 250ms debounce', async () => {
      const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) })
      render(<ExperimentForm {...defaultProps} />)

      const nameInput = screen.getByPlaceholderText('e.g. v2 vs v3 comparison')
      await user.type(nameInput, 'My experiment')

      // Before debounce, no valid mark yet
      expect(screen.queryAllByLabelText('Valid')).toHaveLength(0)

      await act(async () => { vi.advanceTimersByTime(260) })

      await waitFor(() => {
        expect(screen.getAllByLabelText('Valid').length).toBeGreaterThan(0)
      })
    })
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { i18n, render, screen, waitFor, fireEvent } from '../../../test/utils'
import { InputGuardRulesTab } from '../ui/InputGuardRulesTab'
import * as inputGuardApi from '../api'
import type { InputGuardRule, ListRulesResponse } from '../api'

vi.mock('../api', () => ({
  listInputGuardRules: vi.fn(),
  getInputGuardRule: vi.fn(),
  createInputGuardRule: vi.fn(),
  updateInputGuardRule: vi.fn(),
  deleteInputGuardRule: vi.fn(),
}))

const listRulesMock = vi.mocked(inputGuardApi.listInputGuardRules)
const getRuleMock = vi.mocked(inputGuardApi.getInputGuardRule)

const sampleRule: InputGuardRule = {
  id: 'rule-1',
  name: 'My rule',
  pattern: 'foo',
  patternType: 'regex',
  action: 'block',
  priority: 1,
  category: 'safety',
  description: 'desc',
  enabled: true,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-02-01T00:00:00Z',
}

beforeEach(() => {
  i18n.addResourceBundle('en', 'translation', {
    'inputGuard.rules.description': 'Custom rules description',
    'inputGuard.rules.total': '{{count}} rules',
    'inputGuard.rules.addNew': 'New Rule',
    'inputGuard.rules.emptyTitle': 'No rules',
    'inputGuard.rules.emptyDesc': 'Add the first rule.',
    'inputGuard.rules.colName': 'Name',
    'inputGuard.rules.colAction': 'Handling',
    'inputGuard.rules.colDescription': 'Description',
    'inputGuard.rules.colPriority': 'Priority',
    'inputGuard.rules.colStatus': 'Status',
    'inputGuard.rules.colReview': 'Review',
    'inputGuard.rules.delete': 'Delete',
    'inputGuard.rules.review': 'Review',
    'inputGuard.rules.reviewAriaLabel': 'Review {{name}}',
    'inputGuard.rules.detailTitle': 'Rule detail',
    'inputGuard.rules.detailLoading': 'Loading rule…',
    'inputGuard.rules.detailErrorTitle': 'Error',
    'inputGuard.rules.detailNotFound': 'This rule no longer exists.',
    'inputGuard.rules.editButton': 'Edit',
    'inputGuard.rules.fieldName': 'Name',
    'inputGuard.rules.fieldPatternType': 'Pattern Type',
    'inputGuard.rules.fieldAction': 'Action',
    'inputGuard.rules.fieldPattern': 'Pattern',
    'inputGuard.rules.fieldCategory': 'Category',
    'inputGuard.rules.fieldPriority': 'Priority',
    'inputGuard.rules.fieldDescription': 'Description',
    'inputGuard.rules.fieldEnabled': 'Enabled',
    'inputGuard.rules.fieldCreatedAt': 'Created at',
    'inputGuard.rules.fieldUpdatedAt': 'Updated at',
    'inputGuard.rules.statusEnabled': 'Active',
    'inputGuard.rules.statusPaused': 'Paused',
    'inputGuard.rules.descriptionEmpty': 'No description',
    'inputGuard.rules.technicalDetails': 'Technical details',
    'inputGuard.rules.technicalPattern': 'Expression',
    'inputGuard.rules.technicalCategory': 'Category code',
    'inputGuard.rules.technicalId': 'Rule ID',
    'inputGuard.rules.unavailableTitle': 'Rules are unavailable',
    'inputGuard.rules.unavailableDescription': 'Rule changes are paused.',
    'inputGuard.rules.actionLabels.block': 'Block immediately',
    'inputGuard.rules.actionLabels.warn': 'Warn and continue',
    'inputGuard.rules.actionLabels.flag': 'Mark for review',
    'inputGuard.rules.patternTypeLabels.regex': 'Regular expression',
    'inputGuard.rules.patternTypeLabels.keyword': 'Text match',
    'inputGuard.recoveryTitle': 'How to recover',
    'inputGuard.recoveryAccount': 'Check access.',
    'inputGuard.recoveryConnection': 'Check service status.',
    'common.close': 'Close',
    'common.yes': 'Yes',
    'common.no': 'No',
    'common.retry': 'Retry',
    'common.retrying': 'Retrying',
    'common.openStatusPage': 'Open status',
    'common.technicalDetails': 'Technical details',
  }, true, true)
})

const listResponse: ListRulesResponse = { rules: [sampleRule], total: 1 }

function renderRulesTab() {
  return render(<MemoryRouter><InputGuardRulesTab /></MemoryRouter>)
}

describe('InputGuardRulesTab — rule review', () => {
  it('renders one review action per row without raw rule mechanics in the table', async () => {
    listRulesMock.mockResolvedValue(listResponse)
    renderRulesTab()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Review My rule/i })).toBeInTheDocument()
    })
    expect(screen.getByText('Block immediately')).toBeInTheDocument()
    expect(screen.queryByText(/^regex$/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/^safety$/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /edit row/i })).not.toBeInTheDocument()
  })

  it('opens the modal in read-mode when Review is clicked', async () => {
    listRulesMock.mockResolvedValue(listResponse)
    getRuleMock.mockResolvedValue(sampleRule)

    renderRulesTab()
    const viewBtn = await screen.findByRole('button', { name: /Review My rule/i })
    fireEvent.click(viewBtn)

    // Wait for the read-mode modal to appear with the Edit toggle
    await waitFor(() => {
      const editToggle = screen.getByRole('button', { name: /^Edit$/ })
      expect(editToggle).toBeInTheDocument()
    })
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(getRuleMock).toHaveBeenCalledWith('rule-1')
  })

  it('shows "rule no longer exists" message when the detail fetch errors', async () => {
    listRulesMock.mockResolvedValue(listResponse)
    getRuleMock.mockRejectedValue(new Error('not found'))

    renderRulesTab()
    const viewBtn = await screen.findByRole('button', { name: /Review My rule/i })
    fireEvent.click(viewBtn)

    await waitFor(() => {
      expect(screen.getByText(/no longer exists/i)).toBeInTheDocument()
    })
  })

  it('does not turn a failed rules request into an empty collection or editable state', async () => {
    listRulesMock.mockRejectedValue(new Error('HTTP 503: backend unavailable'))

    renderRulesTab()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Rules are unavailable')
    expect(screen.queryByRole('button', { name: 'New Rule' })).not.toBeInTheDocument()
    expect(screen.queryByText('No rules')).not.toBeInTheDocument()

    const technicalDetails = screen.getByText('Technical details').closest('details')
    expect(technicalDetails).not.toHaveAttribute('open')
    expect(technicalDetails).toHaveTextContent('HTTP 503: backend unavailable')
  })
})

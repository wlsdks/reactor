import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, i18n, render, screen, waitFor } from '../../../test/utils'
import { OutputGuardRuleModal } from '../ui/OutputGuardRuleModal'
import * as outputGuardApi from '../api'
import type { OutputGuardRule } from '../types'

vi.mock('../api', () => ({
  listRules: vi.fn(),
  listRuleAudits: vi.fn(),
  createRule: vi.fn(),
  updateRule: vi.fn(),
  deleteRule: vi.fn(),
  simulateGuard: vi.fn(),
}))

const createRuleMock = vi.mocked(outputGuardApi.createRule)

function buildRule(overrides: Partial<OutputGuardRule> = {}): OutputGuardRule {
  return {
    id: 'rule-1',
    name: 'Credit card blocker',
    pattern: '\\b\\d{4}-\\d{4}-\\d{4}-\\d{4}\\b',
    action: 'REJECT',
    priority: 10,
    enabled: true,
    createdAt: 1710000000000,
    updatedAt: 1710003600000,
    ...overrides,
  }
}

const noop = () => {}

describe('OutputGuardRuleModal', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'common.name': 'Name',
      'common.save': 'Save',
      'common.cancel': 'Cancel',
      'common.enabled': 'Enabled',
      'common.toast.created': 'Created',
      'common.toast.updated': 'Updated',
      'outputGuardPage.createRule': 'Create Rule',
      'outputGuardPage.editRule': 'Edit Rule',
      'outputGuardPage.modePreset': 'Preset',
      'outputGuardPage.modeKeyword': 'Keyword',
      'outputGuardPage.modeRegex': 'Regex',
      'outputGuardPage.preset.email': 'Email Address',
      'outputGuardPage.preset.phone': 'Phone Number',
      'outputGuardPage.preset.apiKey': 'API Key / Token',
      'outputGuardPage.preset.creditCard': 'Credit Card',
      'outputGuardPage.preset.rrn': 'ID Number',
      'outputGuardPage.preset.bankAccount': 'Bank Account',
      'outputGuardPage.keywordLabel': 'Keywords',
      'outputGuardPage.keywordHelp': 'Separate with commas. Responses containing these words will be filtered.',
      'outputGuardPage.keywordPlaceholder': 'e.g. Phoenix, Titan, confidential',
      'outputGuardPage.ruleAction': 'Action',
      'outputGuardPage.rulePriority': 'Priority',
      'outputGuardPage.regexPattern': 'Regex Pattern',
      'outputGuardPage.validation.invalidRegex': 'Regex pattern is invalid: {{message}}',
    }, true, true)

    createRuleMock.mockResolvedValue(buildRule({ id: 'new-rule' }))
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when closed', () => {
    render(
      <OutputGuardRuleModal open={false} onClose={noop} onSaved={noop} />,
    )
    expect(screen.queryByText('Create Rule')).not.toBeInTheDocument()
  })

  it('renders 3 mode tabs in create mode', () => {
    render(
      <OutputGuardRuleModal open={true} onClose={noop} onSaved={noop} />,
    )
    expect(screen.getByText('Preset')).toBeInTheDocument()
    expect(screen.getByText('Keyword')).toBeInTheDocument()
    expect(screen.getByText('Regex')).toBeInTheDocument()
  })

  it('does not render mode tabs in edit mode', () => {
    const rule = buildRule()
    render(
      <OutputGuardRuleModal open={true} onClose={noop} onSaved={noop} rule={rule} />,
    )
    expect(screen.queryByText('Preset')).not.toBeInTheDocument()
    expect(screen.queryByText('Keyword')).not.toBeInTheDocument()
    // "Regex" as a tab should not be present; "Regex Pattern" label is OK
    expect(screen.queryByRole('button', { name: 'Regex' })).not.toBeInTheDocument()
  })

  it('renders 6 preset cards in preset mode', () => {
    render(
      <OutputGuardRuleModal open={true} onClose={noop} onSaved={noop} />,
    )
    expect(screen.getByText('Email Address')).toBeInTheDocument()
    expect(screen.getByText('Phone Number')).toBeInTheDocument()
    expect(screen.getByText('API Key / Token')).toBeInTheDocument()
    expect(screen.getByText('Credit Card')).toBeInTheDocument()
    expect(screen.getByText('ID Number')).toBeInTheDocument()
    expect(screen.getByText('Bank Account')).toBeInTheDocument()
  })

  it('selecting preset fills form fields', async () => {
    render(
      <OutputGuardRuleModal open={true} onClose={noop} onSaved={noop} />,
    )

    // Click Email Address preset
    fireEvent.click(screen.getByText('Email Address'))

    // After clicking, the form fields should appear with pre-filled values
    await waitFor(() => {
      const nameInput = screen.getByLabelText(/^Name/i) as HTMLInputElement
      expect(nameInput.value).toBe('Email Address')
    })

    // Action should be pre-filled to MASK
    const actionSelect = screen.getByLabelText('Action') as HTMLSelectElement
    expect(actionSelect.value).toBe('MASK')

    // Priority should be 100
    const priorityInput = screen.getByLabelText(/^Priority/i) as HTMLInputElement
    expect(priorityInput.value).toBe('100')
  })

  it('keyword mode converts comma-separated words to regex pattern', async () => {
    render(
      <OutputGuardRuleModal open={true} onClose={noop} onSaved={noop} />,
    )

    // Switch to keyword mode
    fireEvent.click(screen.getByText('Keyword'))

    // Type keywords
    const keywordsInput = screen.getByLabelText(/^Keywords/i)
    fireEvent.change(keywordsInput, { target: { value: 'Phoenix, Titan' } })

    // The generated pattern should be displayed
    await waitFor(() => {
      expect(screen.getByText('(?:Phoenix|Titan)')).toBeInTheDocument()
    })
  })

  it('regex mode shows pattern input directly', () => {
    render(
      <OutputGuardRuleModal open={true} onClose={noop} onSaved={noop} />,
    )

    // Switch to regex mode
    fireEvent.click(screen.getByText('Regex'))

    // Pattern textarea should be visible
    expect(screen.getByLabelText(/^Regex Pattern/i)).toBeInTheDocument()
  })

  it('calls onSaved after successful creation', async () => {
    const onSaved = vi.fn()
    const onClose = vi.fn()

    render(
      <OutputGuardRuleModal open={true} onClose={onClose} onSaved={onSaved} />,
    )

    // Switch to regex mode for direct input
    fireEvent.click(screen.getByText('Regex'))

    // Fill name
    fireEvent.change(screen.getByLabelText(/^Name/i), {
      target: { value: 'Test Rule' },
    })

    // Fill pattern
    fireEvent.change(screen.getByLabelText(/^Regex Pattern/i), {
      target: { value: 'test-pattern' },
    })

    // Submit form
    fireEvent.click(screen.getByText('Save'))

    await waitFor(() => {
      expect(createRuleMock).toHaveBeenCalled()
    })

    const callArgs = createRuleMock.mock.calls[0][0] as Record<string, unknown>
    expect(callArgs).toMatchObject({
      name: 'Test Rule',
      pattern: 'test-pattern',
      action: 'MASK',
      priority: 100,
      enabled: true,
    })

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalled()
      expect(onClose).toHaveBeenCalled()
    })
  })
})

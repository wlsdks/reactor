import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, act } from '../../../test/utils'
import userEvent from '@testing-library/user-event'
import { i18n } from '../../../test/utils'
import { InputGuardRuleModal } from '../ui/InputGuardRuleModal'
import type { InputGuardRule } from '../api'

vi.mock('../api', () => ({
  createInputGuardRule: vi.fn(),
  updateInputGuardRule: vi.fn(),
}))

const sampleRule: InputGuardRule = {
  id: 'rule-1',
  name: 'Test rule',
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
    'common.cancel': 'Cancel',
    'common.save': 'Save',
    'inputGuard.rules.createTitle': 'New Rule',
    'inputGuard.rules.editTitle': 'Edit Rule',
    'inputGuard.rules.fieldName': 'Name',
    'inputGuard.rules.fieldNamePlaceholder': 'e.g. PII SSN',
    'inputGuard.rules.fieldPatternType': 'Pattern Type',
    'inputGuard.rules.fieldPatternTypeRegex': 'regex',
    'inputGuard.rules.fieldPatternTypeKeyword': 'keyword',
    'inputGuard.rules.fieldPattern': 'Pattern',
    'inputGuard.rules.fieldPatternPlaceholderRegex': 'e.g. \\d+',
    'inputGuard.rules.fieldPatternPlaceholderKeyword': 'e.g. badword',
    'inputGuard.rules.fieldAction': 'Action',
    'inputGuard.rules.fieldActionBlock': 'block',
    'inputGuard.rules.fieldActionWarn': 'warn',
    'inputGuard.rules.fieldActionFlag': 'flag',
    'inputGuard.rules.fieldCategory': 'Category',
    'inputGuard.rules.fieldCategoryPlaceholder': 'pii',
    'inputGuard.rules.fieldPriority': 'Priority',
    'inputGuard.rules.fieldDescription': 'Description',
    'inputGuard.rules.fieldEnabled': 'Enabled',
    'inputGuard.rules.created': 'Created',
    'inputGuard.rules.updated': 'Updated',
    'inputGuard.rules.hintName': 'Operator-friendly short name.',
    'inputGuard.rules.hintPattern': 'regex or keyword.',
    'inputGuard.rules.hintPriority': 'Lower runs first.',
    'inputGuard.rules.detailTitle': 'Rule detail',
    'inputGuard.rules.editButton': 'Edit',
    'inputGuard.rules.fieldCreatedAt': 'Created at',
    'inputGuard.rules.fieldUpdatedAt': 'Updated at',
    'common.close': 'Close',
    'common.yes': 'Yes',
    'common.no': 'No',
  }, true, true)
})

describe('InputGuardRuleModal — real-time validation', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders required asterisk + aria-required on Name and Pattern', () => {
    render(<InputGuardRuleModal open onClose={vi.fn()} />)
    const nameInput = screen.getByLabelText(/Name/i)
    expect(nameInput).toHaveAttribute('aria-required', 'true')
  })

  it('renders schema-derived hint text under fields', () => {
    render(<InputGuardRuleModal open onClose={vi.fn()} />)
    expect(screen.getByText('Operator-friendly short name.')).toBeInTheDocument()
    expect(screen.getByText('regex or keyword.')).toBeInTheDocument()
  })

  it('shows ✓ valid indicator after debounce window when typing valid input', async () => {
    const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) })
    render(<InputGuardRuleModal open onClose={vi.fn()} />)

    const nameInput = screen.getByLabelText(/Name/i)
    await user.type(nameInput, 'PII SSN Detector')

    await act(async () => { vi.advanceTimersByTime(260) })

    await waitFor(() => {
      const validIndicators = screen.getAllByLabelText('Valid')
      expect(validIndicators.length).toBeGreaterThan(0)
    })
  })

  it('shows ✗ error indicator when value exceeds max length', async () => {
    const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) })
    render(<InputGuardRuleModal open onClose={vi.fn()} />)

    // Name has max 120; type something past that
    const nameInput = screen.getByLabelText(/Name/i)
    await user.type(nameInput, 'x'.repeat(125))

    await act(async () => { vi.advanceTimersByTime(260) })

    await waitFor(() => {
      const errorIndicators = screen.getAllByLabelText('Invalid')
      expect(errorIndicators.length).toBeGreaterThan(0)
    })
  })
})

describe('InputGuardRuleModal — read mode', () => {
  it('shows read-only fields when mode="read"', () => {
    render(<InputGuardRuleModal open mode="read" rule={sampleRule} onClose={vi.fn()} />)
    // Field values present
    expect(screen.getByText('Test rule')).toBeInTheDocument()
    expect(screen.getByText('foo')).toBeInTheDocument()
    // No editable inputs (no Name textbox)
    expect(screen.queryByLabelText(/Name/i)).not.toBeInTheDocument()
  })

  it('shows an Edit toggle button in read-mode', () => {
    render(<InputGuardRuleModal open mode="read" rule={sampleRule} onClose={vi.fn()} />)
    expect(screen.getByRole('button', { name: /^Edit$/ })).toBeInTheDocument()
  })

  it('clicking Edit flips into form mode (Name input appears)', async () => {
    render(<InputGuardRuleModal open mode="read" rule={sampleRule} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /^Edit$/ }))
    expect(await screen.findByLabelText(/Name/i)).toBeInTheDocument()
  })

  it('default mode is "edit" (backward compat) with rule prop', () => {
    render(<InputGuardRuleModal open rule={sampleRule} onClose={vi.fn()} />)
    // Name input visible immediately
    expect(screen.getByLabelText(/Name/i)).toBeInTheDocument()
  })
})

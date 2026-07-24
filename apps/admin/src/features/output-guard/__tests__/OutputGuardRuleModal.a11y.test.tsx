import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, i18n, render, screen, waitFor } from '../../../test/utils'
import { OutputGuardRuleModal } from '../ui/OutputGuardRuleModal'

vi.mock('../api', () => ({
  listRules: vi.fn(),
  listRuleAudits: vi.fn(),
  createRule: vi.fn(),
  updateRule: vi.fn(),
  deleteRule: vi.fn(),
  simulateGuard: vi.fn(),
}))

const noop = () => {}

describe('OutputGuardRuleModal — form a11y', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'common.name': 'Name',
      'common.save': 'Save',
      'common.cancel': 'Cancel',
      'common.enabled': 'Enabled',
      'outputGuardPage.createRule': 'Create Rule',
      'outputGuardPage.modePreset': 'Preset',
      'outputGuardPage.modeKeyword': 'Keyword',
      'outputGuardPage.modeRegex': 'Regex',
      'outputGuardPage.regexPattern': 'Regex Pattern',
      'outputGuardPage.ruleAction': 'Action',
      'outputGuardPage.rulePriority': 'Priority',
      'outputGuardPage.preset.email': 'Email Address',
      'outputGuardPage.preset.phone': 'Phone Number',
      'outputGuardPage.preset.apiKey': 'API Key / Token',
      'outputGuardPage.preset.creditCard': 'Credit Card',
      'outputGuardPage.preset.rrn': 'ID Number',
      'outputGuardPage.preset.bankAccount': 'Bank Account',
    }, true, true)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('marks Name and Regex Pattern as required in regex mode', () => {
    render(<OutputGuardRuleModal open onClose={noop} onSaved={noop} />)
    fireEvent.click(screen.getByText('Regex'))

    const nameInput = screen.getByLabelText(/Name/i)
    expect(nameInput).toHaveAttribute('aria-required', 'true')

    const patternInput = screen.getByLabelText(/Regex Pattern/i)
    expect(patternInput).toHaveAttribute('aria-required', 'true')
  })

  it('toggles aria-invalid + aria-describedby when Name is cleared', async () => {
    render(<OutputGuardRuleModal open onClose={noop} onSaved={noop} />)
    fireEvent.click(screen.getByText('Regex'))

    const nameInput = screen.getByLabelText(/Name/i) as HTMLInputElement
    // Initial state: no error
    expect(nameInput.getAttribute('aria-invalid')).toBe('false')
    expect(nameInput.getAttribute('aria-describedby')).toBeNull()

    // Make name dirty then clear it -> error
    fireEvent.change(nameInput, { target: { value: 'Some rule' } })
    fireEvent.change(nameInput, { target: { value: '' } })

    await waitFor(() => {
      expect(nameInput.getAttribute('aria-invalid')).toBe('true')
      expect(nameInput.getAttribute('aria-describedby')).toBe('rule-name-error')
    })

    const errorEl = document.getElementById('rule-name-error')
    expect(errorEl).not.toBeNull()
    expect(errorEl?.getAttribute('role')).toBe('alert')
  })
})

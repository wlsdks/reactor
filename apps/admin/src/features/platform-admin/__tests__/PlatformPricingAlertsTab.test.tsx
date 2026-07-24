import { describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '../../../test/utils'
import { PlatformPricingAlertsTab } from '../ui/PlatformPricingAlertsTab'

const baseProps = {
  pricing: [],
  alertRules: [],
  activeAlerts: [],
  saving: false,
  pricingForm: { provider: '', model: '', promptPricePer1m: '0', completionPricePer1m: '0', cachedInputPricePer1m: '0', reasoningPricePer1m: '0', batchPromptPricePer1m: '0', batchCompletionPricePer1m: '0' },
  ruleForm: { name: '', description: '', metric: 'error_rate', threshold: '0.1', windowMinutes: '15', type: 'STATIC_THRESHOLD' as const, severity: 'WARNING' as const, tenantId: '', enabled: true, platformOnly: true },
  onPricingFormChange: vi.fn(),
  onRuleFormChange: vi.fn(),
  onUpsertPricing: vi.fn(),
  onSaveAlertRule: vi.fn(),
  onDeleteRule: vi.fn(),
  onResolveAlert: vi.fn(),
  onRetry: vi.fn(),
}

function renderAlerts(overrides: Partial<ComponentProps<typeof PlatformPricingAlertsTab>> = {}) {
  return render(<MemoryRouter><PlatformPricingAlertsTab {...baseProps} section="alerts" {...overrides} /></MemoryRouter>)
}

describe('PlatformPricingAlertsTab alerts', () => {
  it('keeps the large rule form collapsed and uses human option labels', async () => {
    const user = userEvent.setup()
    renderAlerts()

    expect(document.querySelector('form')).not.toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: 'modelsPage.createAlertRule' })[0])
    expect(document.querySelector('form')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '고정 임계값' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '긴급' })).toBeInTheDocument()
    expect(screen.queryByText('STATIC_THRESHOLD')).not.toBeInTheDocument()
  })

  it('renders typed incidents without raw enum badges', () => {
    renderAlerts({
      activeAlerts: [{ id: 'a-1', ruleId: 'r-1', tenantId: null, severity: 'CRITICAL', status: 'FIRING', message: 'Latency exceeded', metricValue: 520, threshold: 500, firedAt: Date.UTC(2026, 6, 11), resolvedAt: null, acknowledgedBy: null }],
    })

    expect(screen.getByText('긴급')).toBeInTheDocument()
    expect(screen.getByText('520 / 500')).toBeInTheDocument()
    expect(screen.queryByText('CRITICAL')).not.toBeInTheDocument()
    expect(document.querySelectorAll('.badge')).toHaveLength(0)
  })
})

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, waitFor } from '../../../test/utils'
import { RetentionTab } from '../ui/RetentionTab'
import * as api from '../api'
import type { RetentionPolicy } from '../types'

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return {
    ...actual,
    getRetentionPolicy: vi.fn(),
    updateRetentionPolicy: vi.fn(),
  }
})

const getPolicyMock = vi.mocked(api.getRetentionPolicy)
const updatePolicyMock = vi.mocked(api.updateRetentionPolicy)

const mockPolicy: RetentionPolicy = {
  sessionRetentionDays: 90,
  conversationRetentionDays: 365,
  auditRetentionDays: 730,
  metricRetentionDays: 180,
  checkpointRetentionDays: 90,
}

function renderRetentionTab() {
  return render(<MemoryRouter><RetentionTab /></MemoryRouter>)
}

describe('RetentionTab', () => {
  beforeEach(() => {
    getPolicyMock.mockResolvedValue(mockPolicy)
    updatePolicyMock.mockResolvedValue(mockPolicy)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders title and description', async () => {
    renderRetentionTab()
    await waitFor(() => {
      expect(screen.getByText('retentionTab.title')).toBeInTheDocument()
      expect(screen.getByText('retentionTab.description')).toBeInTheDocument()
    })
  })

  it('renders form inputs for every backend retention field', async () => {
    const { container } = renderRetentionTab()
    await waitFor(() => {
      expect(screen.getByLabelText('retentionTab.sessionRetention')).toBeInTheDocument()
      expect(screen.getByLabelText('retentionTab.conversationRetention')).toBeInTheDocument()
      expect(screen.getByLabelText('retentionTab.auditRetention')).toBeInTheDocument()
      expect(screen.getByLabelText('retentionTab.metricRetention')).toBeInTheDocument()
      expect(screen.getByLabelText('retentionTab.checkpointRetention')).toBeInTheDocument()
    })
    expect(container.querySelectorAll('.retention-tab__field')).toHaveLength(5)
    expect(screen.getByText('retentionTab.fieldDescriptions.sessionRetention')).toBeInTheDocument()
    expect(screen.getByText('retentionTab.fieldDescriptions.checkpointRetention')).toBeInTheDocument()
  })

  it('renders save and reset buttons', async () => {
    renderRetentionTab()
    await waitFor(() => {
      expect(screen.getByText('Save')).toBeInTheDocument()
      expect(screen.getByText('retentionTab.resetDefaults')).toBeInTheDocument()
    })
  })

  it('displays the current values in the editable controls', async () => {
    renderRetentionTab()
    await waitFor(() => {
      expect(screen.getByLabelText('retentionTab.sessionRetention')).toHaveValue(90)
      expect(screen.getByLabelText('retentionTab.conversationRetention')).toHaveValue(365)
      expect(screen.getByLabelText('retentionTab.auditRetention')).toHaveValue(730)
      expect(screen.getByLabelText('retentionTab.metricRetention')).toHaveValue(180)
      expect(screen.getByLabelText('retentionTab.checkpointRetention')).toHaveValue(90)
    })
  })

  it('renders aria-invalid attributes on inputs', async () => {
    renderRetentionTab()
    await waitFor(() => {
      const input = screen.getByLabelText('retentionTab.sessionRetention')
      expect(input).toHaveAttribute('aria-invalid', 'false')
    })
  })

  it('fails safe when the current retention policy cannot be loaded', async () => {
    getPolicyMock.mockRejectedValue(new Error('retention unavailable'))

    renderRetentionTab()

    expect(await screen.findByRole('alert')).toHaveTextContent('retentionTab.unavailableTitle')
    expect(screen.queryByLabelText('retentionTab.sessionRetention')).not.toBeInTheDocument()
    expect(screen.queryByText('retentionTab.resetDefaults')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'retentionTab.openHealth' })).toHaveAttribute('href', '/health')
  })
})

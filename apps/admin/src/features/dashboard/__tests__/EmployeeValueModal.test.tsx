import { render, screen } from '../../../test/utils'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import { EmployeeValueModal } from '../ui/EmployeeValueModal'
import type { DashboardEmployeeValueSummary } from '../types'

const mockData: DashboardEmployeeValueSummary = {
  observedResponses: 10,
  groundedResponses: 5,
  groundedRatePercent: 50,
  blockedResponses: 2,
  interactiveResponses: 8,
  scheduledResponses: 2,
  answerModes: { Interactive: 8, Scheduled: 2 },
  channels: [{ key: 'Admin', count: 5 }],
  lanes: [
    {
      answerMode: 'Interactive',
      observedResponses: 8,
      groundedResponses: 4,
      blockedResponses: 1,
      groundedRatePercent: 50,
    },
  ],
  toolFamilies: [{ key: 'Search', count: 3 }],
  topMissingQueries: [],
}

describe('EmployeeValueModal', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <MemoryRouter>
        <EmployeeValueModal open={false} onClose={vi.fn()} employeeValue={mockData} />
      </MemoryRouter>,
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders modal with title when open', () => {
    render(
      <MemoryRouter>
        <EmployeeValueModal open={true} onClose={vi.fn()} employeeValue={mockData} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('renders value snapshot data', () => {
    render(
      <MemoryRouter>
        <EmployeeValueModal open={true} onClose={vi.fn()} employeeValue={mockData} />
      </MemoryRouter>,
    )
    const metaGrid = document.querySelector('.meta-grid')!
    expect(metaGrid).toBeInTheDocument()
    // Observed responses: 10
    expect(metaGrid.textContent).toContain('10')
    // Grounded coverage: 50%
    expect(metaGrid.textContent).toContain('50%')
  })

  it('returns null when employeeValue is undefined', () => {
    const { container } = render(
      <MemoryRouter>
        <EmployeeValueModal open={true} onClose={vi.fn()} employeeValue={undefined} />
      </MemoryRouter>,
    )
    expect(container.innerHTML).toBe('')
  })
})

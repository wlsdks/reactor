import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, waitFor, i18n, fireEvent } from '../../../test/utils'
import { RagCandidatesTab } from '../ui/RagCandidatesTab'
import * as ragCacheApi from '../api'
import type { RagCandidate } from '../types'

// RagCandidatesTab now reads URL state (for the saved-views scope), so every
// render needs a Router context. Wrap once at the call-site to avoid
// duplicating the boilerplate in every test.
function renderTab() {
  return render(
    <MemoryRouter>
      <RagCandidatesTab />
    </MemoryRouter>,
  )
}

vi.mock('../api', () => ({
  listRagCandidates: vi.fn(),
  approveRagCandidate: vi.fn(),
  rejectRagCandidate: vi.fn(),
  bulkApproveRagCandidates: vi.fn(),
  bulkRejectRagCandidates: vi.fn(),
}))

const listRagCandidatesMock = vi.mocked(ragCacheApi.listRagCandidates)
const bulkApproveMock = vi.mocked(ragCacheApi.bulkApproveRagCandidates)
const bulkRejectMock = vi.mocked(ragCacheApi.bulkRejectRagCandidates)

function buildCandidate(id: string, overrides: Partial<RagCandidate> = {}): RagCandidate {
  return {
    id,
    query: `Query ${id}`,
    response: `Response ${id}`,
    channel: 'web',
    status: 'PENDING',
    capturedAt: 1700000000000,
    ...overrides,
  }
}

describe('RagCandidatesTab — bulk actions', () => {
  beforeEach(() => {
    i18n.addResourceBundle(
      'en',
      'translation',
      {
        'common.toast.updated': 'Updated',
        'ragCachePage.candidates.title': 'Candidate Review',
        'ragCachePage.candidates.queue': 'Review Queue',
        'ragCachePage.candidates.empty': 'No candidates found',
        'ragCachePage.candidates.filterStatus': 'Status',
        'ragCachePage.candidates.statusAll': 'All',
        'ragCachePage.candidates.approve': 'Approve',
        'ragCachePage.candidates.reject': 'Reject',
        'ragCachePage.candidates.approveConfirm': 'Approve this candidate?',
        'ragCachePage.candidates.rejectConfirm': 'Reject this candidate?',
        'ragCachePage.candidates.query': 'Query',
        'ragCachePage.candidates.response': 'Response',
        'ragCachePage.candidates.channel': 'Channel',
        'ragCachePage.candidates.capturedAt': 'Captured At',
        'ragCachePage.candidates.status': 'Status',
        'ragCachePage.candidates.selectAll': 'Select all pending candidates',
        'ragCachePage.candidates.selectRow': 'Select candidate: {{query}}',
        'ragCachePage.candidates.bulkBarLabel': 'Bulk actions',
        'ragCachePage.candidates.bulkSelected': '{{count}} items selected',
        'ragCachePage.candidates.bulkApprove': 'Approve selected',
        'ragCachePage.candidates.bulkReject': 'Reject selected',
        'ragCachePage.candidates.bulkClear': 'Clear selection',
        'ragCachePage.candidates.bulkApproveConfirm':
          'Approve {{count}} selected candidates?',
        'ragCachePage.candidates.bulkRejectConfirm':
          'Reject {{count}} selected candidates?',
        'ragCachePage.candidates.bulkStarted':
          '{{action}} {{count}} items in progress…',
        'ragCachePage.candidates.bulkSuccess': '{{action}} {{count}} items succeeded',
        'ragCachePage.candidates.bulkPartial':
          '{{success}} of {{total}} succeeded, {{failed}} failed',
        'ragCachePage.candidates.bulkAllFailed': 'All {{count}} items failed',
      },
      true,
      true,
    )
    bulkApproveMock.mockResolvedValue({ succeeded: [], failed: [] })
    bulkRejectMock.mockResolvedValue({ succeeded: [], failed: [] })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('does not render the bulk action bar when no items are selected', async () => {
    listRagCandidatesMock.mockResolvedValue([
      buildCandidate('a'),
      buildCandidate('b'),
    ])

    renderTab()

    await waitFor(() => {
      expect(screen.getByText('Query a')).toBeInTheDocument()
    })
    expect(screen.queryByRole('region', { name: 'Bulk actions' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve selected' })).not.toBeInTheDocument()
  })

  it('selects a single row via its checkbox and surfaces the bulk action bar', async () => {
    listRagCandidatesMock.mockResolvedValue([
      buildCandidate('a', { query: 'alpha' }),
      buildCandidate('b', { query: 'beta' }),
    ])
    const user = userEvent.setup()

    renderTab()

    const rowCheckbox = await screen.findByRole('checkbox', {
      name: /Select candidate: alpha/,
    })
    await user.click(rowCheckbox)

    expect(screen.getByText('1 items selected')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve selected' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject selected' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear selection' })).toBeInTheDocument()
  })

  it('select-all checkbox selects only PENDING rows and reflects all-selected state', async () => {
    listRagCandidatesMock.mockResolvedValue([
      buildCandidate('a'),
      buildCandidate('b'),
      buildCandidate('c', { status: 'APPROVED' }),
      buildCandidate('d', { status: 'REJECTED' }),
    ])
    const user = userEvent.setup()

    renderTab()

    const selectAll = await screen.findByRole('checkbox', {
      name: 'Select all pending candidates',
    })
    await user.click(selectAll)

    // Only 2 pending rows → 2 selected, non-pending rows untouched.
    expect(screen.getByText('2 items selected')).toBeInTheDocument()

    // Non-pending row checkbox is disabled.
    const rejectedCheckbox = screen.getByRole('checkbox', {
      name: /Select candidate: Query d/,
    })
    expect(rejectedCheckbox).toBeDisabled()
  })

  it('select-all toggles off when already all-selected', async () => {
    listRagCandidatesMock.mockResolvedValue([
      buildCandidate('a'),
      buildCandidate('b'),
    ])
    const user = userEvent.setup()

    renderTab()

    const selectAll = await screen.findByRole('checkbox', {
      name: 'Select all pending candidates',
    })
    await user.click(selectAll)
    expect(screen.getByText('2 items selected')).toBeInTheDocument()

    await user.click(selectAll)
    expect(screen.queryByText(/items selected/)).not.toBeInTheDocument()
  })

  it('clear selection button empties the selection', async () => {
    listRagCandidatesMock.mockResolvedValue([
      buildCandidate('a'),
      buildCandidate('b'),
    ])
    const user = userEvent.setup()

    renderTab()

    const selectAll = await screen.findByRole('checkbox', {
      name: 'Select all pending candidates',
    })
    await user.click(selectAll)
    await user.click(screen.getByRole('button', { name: 'Clear selection' }))

    expect(screen.queryByText(/items selected/)).not.toBeInTheDocument()
  })

  it('shift+click extends range selection from the previous anchor', async () => {
    listRagCandidatesMock.mockResolvedValue([
      buildCandidate('a'),
      buildCandidate('b'),
      buildCandidate('c'),
      buildCandidate('d'),
    ])
    const user = userEvent.setup()

    renderTab()

    const checkboxA = await screen.findByRole('checkbox', {
      name: /Select candidate: Query a/,
    })
    await user.click(checkboxA)
    expect(screen.getByText('1 items selected')).toBeInTheDocument()

    // Shift-click on row c should also select b.
    const checkboxC = screen.getByRole('checkbox', {
      name: /Select candidate: Query c/,
    })
    await user.keyboard('{Shift>}')
    fireEvent.click(checkboxC, { shiftKey: true })
    await user.keyboard('{/Shift}')

    await waitFor(() => {
      expect(screen.getByText('3 items selected')).toBeInTheDocument()
    })
  })

  it('bulk approve triggers confirm → calls bulkApproveRagCandidates', async () => {
    listRagCandidatesMock.mockResolvedValue([
      buildCandidate('a'),
      buildCandidate('b'),
    ])
    bulkApproveMock.mockResolvedValue({ succeeded: ['a', 'b'], failed: [] })

    const user = userEvent.setup()

    renderTab()

    const selectAll = await screen.findByRole('checkbox', {
      name: 'Select all pending candidates',
    })
    await user.click(selectAll)

    await user.click(screen.getByRole('button', { name: 'Approve selected' }))

    // Confirm dialog
    const confirmDialog = await screen.findByRole('dialog')
    const confirmButton = await screen.findByRole('button', { name: 'Confirm' })
    expect(confirmDialog).toContainElement(confirmButton)
    await user.click(confirmButton)

    await waitFor(() => {
      expect(bulkApproveMock).toHaveBeenCalledTimes(1)
    })
    expect(bulkApproveMock).toHaveBeenCalledWith(expect.arrayContaining(['a', 'b']))

    // Selection is cleared after success.
    await waitFor(() => {
      expect(screen.queryByText(/items selected/)).not.toBeInTheDocument()
    })
  })

  it('bulk reject calls bulkRejectRagCandidates on confirm', async () => {
    listRagCandidatesMock.mockResolvedValue([buildCandidate('a')])
    bulkRejectMock.mockResolvedValue({ succeeded: ['a'], failed: [] })

    const user = userEvent.setup()
    renderTab()

    const checkbox = await screen.findByRole('checkbox', {
      name: /Select candidate: Query a/,
    })
    await user.click(checkbox)
    await user.click(screen.getByRole('button', { name: 'Reject selected' }))

    await screen.findByRole('dialog')
    const rejectConfirmButton = screen.getByRole('button', { name: 'Confirm' })
    await user.click(rejectConfirmButton)

    await waitFor(() => {
      expect(bulkRejectMock).toHaveBeenCalledWith(['a'])
    })
  })

  it('keeps non-pending rows non-selectable', async () => {
    listRagCandidatesMock.mockResolvedValue([
      buildCandidate('approved1', { status: 'APPROVED', query: 'already-approved' }),
    ])

    renderTab()

    const approvedCheckbox = await screen.findByRole('checkbox', {
      name: /Select candidate: already-approved/,
    })
    expect(approvedCheckbox).toBeDisabled()

    const selectAll = screen.getByRole('checkbox', {
      name: 'Select all pending candidates',
    })
    expect(selectAll).toBeDisabled()
  })
})

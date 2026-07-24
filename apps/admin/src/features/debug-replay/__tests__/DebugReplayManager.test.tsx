import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, i18n, render, screen, waitFor } from '../../../test/utils'
import { DebugReplayManager } from '../ui/DebugReplayManager'
import * as debugReplayApi from '../api'
import type { DebugReplayCapture } from '../types'

vi.mock('../api', () => ({
  listDebugReplayCaptures: vi.fn(),
  getDebugReplayCapture: vi.fn(),
}))

const listCapturesMock = vi.mocked(debugReplayApi.listDebugReplayCaptures)
const getCaptureMock = vi.mocked(debugReplayApi.getDebugReplayCapture)

function buildCapture(overrides: Partial<DebugReplayCapture> = {}): DebugReplayCapture {
  return {
    id: 'cap-001',
    tenantId: 'default',
    userHash: 'abc123def456',
    capturedAt: '2026-04-24T10:00:00Z',
    userPrompt: 'Why did my request fail?',
    errorCode: 'MODEL_TIMEOUT',
    errorMessage: 'Upstream timeout',
    modelId: 'gpt-4o-mini',
    toolsAttempted: 'search_docs',
    expiresAt: '2026-05-01T10:00:00Z',
    ...overrides,
  }
}

function renderManager() {
  const router = createMemoryRouter(
    [{ path: '/', element: <DebugReplayManager /> }],
    { initialEntries: ['/'] },
  )
  return { ...render(<RouterProvider router={router} />), router }
}

describe('DebugReplayManager', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'debugReplayPage.title': 'Failed response recovery',
      'debugReplayPage.description': 'Review a failed request before opening a safe response test.',
      'debugReplay.listTitle': 'Failed requests to review',
      'debugReplay.listCount': '{{count}} recent records',
      'debugReplay.reviewTitle': 'Selected request',
      'debugReplay.selectPrompt': 'Select a request to review its input and failure reason.',
      'debugReplay.prompt': 'Request input',
      'debugReplay.promptUnavailable': 'No saved request input',
      'debugReplay.openReplayTest': 'Open response test with this input',
      'debugReplay.replaySafety': 'Only prefills the test screen and does not run automatically.',
      'debugReplay.replayUnavailable': 'Required reproduction data is missing.',
      'debugReplay.failureReason': 'What went wrong',
      'debugReplay.technicalDetails': 'Developer record information',
      'debugReplay.captureId': 'Record ID',
      'debugReplay.errorCode': 'Error code',
      'debugReplay.errorMessage': 'Original error message',
      'debugReplay.model': 'Model',
      'debugReplay.tools': 'Tools',
      'debugReplay.userHash': 'Anonymous user hash',
      'debugReplay.expiresAt': 'Expires at',
      'debugReplay.empty': 'No recent failed responses',
      'debugReplay.emptyDescription': 'Failed response records will appear here.',
      'debugReplay.openInspector': 'Open response test',
      'debugReplay.unavailableTitle': 'Failed request records are unavailable',
      'debugReplay.unavailableDescription': 'The record list cannot be verified.',
      'debugReplay.openHealth': 'Open status',
      'debugReplay.recoveryGuideTitle': 'How to recover',
      'debugReplay.recoveryCheckAccount': 'Check account access.',
      'debugReplay.recoveryCheckStatus': 'Check Reactor status.',
      'debugReplay.recoveryRetry': 'Retry after recovery.',
      'debugReplay.technicalError': 'Technical detail',
      'debugReplay.detailUnavailableTitle': 'Could not open this request',
      'debugReplay.detailUnavailable': 'The request list is still available. Try again or choose another request.',
      'debugReplay.errors.modelTimeout': 'Model response timed out',
      'debugReplay.errors.unknown': 'Unknown cause',
      'debugReplay.errors.unclassified': 'Unclassified failure',
      'common.retry': 'Retry',
      'common.retrying': 'Retrying',
    }, true, true)
    listCapturesMock.mockResolvedValue([
      buildCapture(),
      buildCapture({
        id: 'cap-002',
        userPrompt: '   ', // blank — not replayable
        modelId: null,
        toolsAttempted: null,
      }),
    ])
    getCaptureMock.mockImplementation(async (id) => buildCapture({ id }))
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lets operators select a failed request before opening a prefilled response test', async () => {
    const { router } = renderManager()

    await waitFor(() => {
      expect(screen.getByText('Why did my request fail?')).toBeInTheDocument()
    })

    expect(screen.queryByRole('link', { name: 'Open response test with this input' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Why did my request fail\?/ }))

    const replayLink = await screen.findByRole('link', { name: 'Open response test with this input' })

    expect(router.state.location.search).toBe('?capture=cap-001')
    expect(screen.getByText('What went wrong')).toBeInTheDocument()

    const href = replayLink.getAttribute('href') ?? ''
    expect(href).toContain('/chat-inspector?')
    expect(href).toContain('message=Why+did+my+request+fail%3F')
    expect(href).toContain('model=gpt-4o-mini')
    expect(href).toContain('tools=search_docs')
    expect(href).toContain('diagnosticSource=debug-replay')
    expect(href).toContain('captureId=cap-001')
  })

  it('keeps raw identifiers hidden until the operator opens developer information', async () => {
    renderManager()

    await waitFor(() => {
      expect(screen.getByText('Why did my request fail?')).toBeInTheDocument()
    })

    expect(screen.queryByText('cap-001')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Why did my request fail\?/ }))
    await screen.findByText('Developer record information')
    expect(screen.getByText('cap-001')).not.toBeVisible()

    fireEvent.click(screen.getByText('Developer record information'))
    expect(screen.getByText('cap-001')).toBeVisible()
  })

  it('shows empty state when no captures exist', async () => {
    listCapturesMock.mockResolvedValueOnce([])
    renderManager()

    await waitFor(() => {
      expect(screen.getByText('No recent failed responses')).toBeInTheDocument()
    })
    expect(screen.queryByRole('link', { name: 'Reproduce' })).toBeNull()
    expect(screen.getByRole('link', { name: 'Open response test' }))
      .toHaveAttribute('href', '/chat-inspector')
  })

  it('fails closed when the capture list cannot be loaded', async () => {
    listCapturesMock.mockRejectedValueOnce(new Error('admin access required'))
    renderManager()

    expect(await screen.findByRole('alert')).toHaveTextContent('Failed request records are unavailable')
    expect(screen.queryByText('No recent failed responses')).toBeNull()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open status' })).toHaveAttribute('href', '/health')
  })

  it('retains the request list and provides retry recovery when a selected request cannot load', async () => {
    getCaptureMock.mockRejectedValueOnce(new Error('capture detail unavailable'))
    renderManager()

    await waitFor(() => {
      expect(screen.getByText('Why did my request fail?')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Why did my request fail\?/ }))

    expect(await screen.findByText('Could not open this request')).toBeInTheDocument()
    expect(screen.getByText('Why did my request fail?')).toBeInTheDocument()
    expect(screen.queryByText('capture detail unavailable')).not.toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('link', { name: 'Open response test with this input' })).toBeInTheDocument()
  })
})

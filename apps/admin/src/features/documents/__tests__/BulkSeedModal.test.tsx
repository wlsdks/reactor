import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n from 'i18next'
import { I18nextProvider, initReactI18next } from 'react-i18next'
import { LiveAnnouncerProvider } from '../../../shared/ui/LiveAnnouncer'
import koResources from '../../../shared/i18n/ko.json'
import { BulkSeedModal } from '../ui/BulkSeedModal'
import * as api from '../api'

// Spin up a focused Korean i18n instance for these tests so user-facing
// strings render exactly as they will in production. Using the real ko.json
// avoids drifting copy between fixtures and ships.
const testI18n = i18n.createInstance()

beforeAll(async () => {
  await testI18n.use(initReactI18next).init({
    lng: 'ko',
    fallbackLng: 'ko',
    resources: { ko: { translation: koResources } },
    interpolation: { escapeValue: false },
  })
})

function renderModal(overrides: { open?: boolean; onClose?: () => void } = {}) {
  const client = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  })
  const onClose = overrides.onClose ?? vi.fn()
  return {
    onClose,
    ...render(
      <QueryClientProvider client={client}>
        <I18nextProvider i18n={testI18n}>
          <LiveAnnouncerProvider>
            <BulkSeedModal open={overrides.open ?? true} onClose={onClose} />
          </LiveAnnouncerProvider>
        </I18nextProvider>
      </QueryClientProvider>,
    ),
  }
}

describe('BulkSeedModal — paste tab', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('does not render when closed', () => {
    renderModal({ open: false })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders with paste tab selected by default', () => {
    renderModal()
    const pasteTab = screen.getByRole('tab', { name: /JSON 붙여넣기/ })
    expect(pasteTab).toHaveAttribute('aria-selected', 'true')
  })

  it('parses valid JSON and shows preview rows', async () => {
    renderModal()
    const textarea = screen.getByLabelText(/JSON 입력/)
    fireEvent.change(textarea, {
      target: { value: JSON.stringify([{ key: 'k1', title: 'T1', content: 'C1' }]) },
    })
    await waitFor(
      () => {
        expect(screen.getByText('k1')).toBeInTheDocument()
        expect(screen.getByText('T1')).toBeInTheDocument()
      },
      { timeout: 1500 },
    )
  })

  it('shows parse error inline for malformed JSON', async () => {
    renderModal()
    const textarea = screen.getByLabelText(/JSON 입력/)
    fireEvent.change(textarea, { target: { value: '{ not json' } })
    await waitFor(
      () => {
        expect(screen.getByText(/파싱 실패/)).toBeInTheDocument()
      },
      { timeout: 1500 },
    )
  })

  it('disables submit when paste is empty', () => {
    renderModal()
    expect(screen.getByRole('button', { name: /시드/ })).toBeDisabled()
  })

  it('disables submit when entries array is empty', async () => {
    renderModal()
    const textarea = screen.getByLabelText(/JSON 입력/)
    fireEvent.change(textarea, { target: { value: '[]' } })
    await waitFor(
      () => {
        expect(screen.getByRole('button', { name: /시드/ })).toBeDisabled()
      },
      { timeout: 1500 },
    )
  })

  it('submits parsed entries via seedPolicyDocuments', async () => {
    const spy = vi.spyOn(api, 'seedPolicyDocuments').mockResolvedValue({
      documentCount: 1,
      chunkCount: 4,
      keys: ['k1'],
      durationMs: 200,
    })
    const { onClose } = renderModal()

    const textarea = screen.getByLabelText(/JSON 입력/)
    fireEvent.change(textarea, {
      target: { value: JSON.stringify([{ key: 'k1', title: 'T1', content: 'C1' }]) },
    })

    await waitFor(
      () => expect(screen.getByRole('button', { name: /1개 항목 시드/ })).toBeEnabled(),
      { timeout: 1500 },
    )

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /1개 항목 시드/ }))
    })

    await waitFor(() => expect(spy).toHaveBeenCalled())
    expect(spy.mock.calls[0][0]).toEqual([{ key: 'k1', title: 'T1', content: 'C1' }])
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('keeps modal open and surfaces partial-success when keys.length < entries.length', async () => {
    vi.spyOn(api, 'seedPolicyDocuments').mockResolvedValue({
      documentCount: 1,
      chunkCount: 4,
      keys: ['k1'],
      durationMs: 200,
    })
    const { onClose } = renderModal()

    const textarea = screen.getByLabelText(/JSON 입력/)
    fireEvent.change(textarea, {
      target: {
        value: JSON.stringify([
          { key: 'k1', title: 'T1', content: 'C1' },
          { key: 'k2', title: 'T2', content: 'C2' },
        ]),
      },
    })

    await waitFor(
      () => expect(screen.getByRole('button', { name: /2개 항목 시드/ })).toBeEnabled(),
      { timeout: 1500 },
    )

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /2개 항목 시드/ }))
    })

    await waitFor(() => {
      const announcer = screen.getByTestId('live-announcer-polite')
      expect(announcer.textContent ?? '').toMatch(/1\/2/)
    })
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('BulkSeedModal — manual tab', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('switches to manual tab and exposes + Add manual button', () => {
    renderModal()
    fireEvent.click(screen.getByRole('tab', { name: /수동 입력/ }))
    expect(screen.getByRole('button', { name: /수동 항목 추가/ })).toBeInTheDocument()
  })

  it('adding an entry creates a fieldset with an Entry 1 legend', () => {
    renderModal()
    fireEvent.click(screen.getByRole('tab', { name: /수동 입력/ }))
    fireEvent.click(screen.getByRole('button', { name: /수동 항목 추가/ }))
    expect(screen.getByRole('group', { name: /항목 1/ })).toBeInTheDocument()
  })

  it('caps manual entries at 20 with a guard message', () => {
    renderModal()
    fireEvent.click(screen.getByRole('tab', { name: /수동 입력/ }))
    const addBtn = screen.getByRole('button', { name: /수동 항목 추가/ })
    for (let i = 0; i < 20; i += 1) fireEvent.click(addBtn)
    expect(addBtn).toBeDisabled()
    expect(screen.getByText(/20개까지/)).toBeInTheDocument()
  })

  it('removing an entry shrinks the fieldset count', async () => {
    renderModal()
    fireEvent.click(screen.getByRole('tab', { name: /수동 입력/ }))
    const addBtn = screen.getByRole('button', { name: /수동 항목 추가/ })
    fireEvent.click(addBtn)
    fireEvent.click(addBtn)
    expect(screen.getAllByRole('group')).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: /1번 항목 제거/ }))
    await waitFor(() => expect(screen.getAllByRole('group')).toHaveLength(1))
  })

  it('submits manual entries via seedPolicyDocuments', async () => {
    const spy = vi.spyOn(api, 'seedPolicyDocuments').mockResolvedValue({
      documentCount: 1,
      chunkCount: 2,
      keys: ['m1'],
      durationMs: 80,
    })
    const { onClose } = renderModal()

    fireEvent.click(screen.getByRole('tab', { name: /수동 입력/ }))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /수동 항목 추가/ }))
    })
    await waitFor(() => expect(screen.getAllByRole('group')).toHaveLength(1))

    fireEvent.change(screen.getByLabelText(/^키$/), { target: { value: 'm1' } })
    fireEvent.change(screen.getByLabelText(/^제목$/), { target: { value: '수동 제목' } })
    fireEvent.change(screen.getByLabelText(/^내용$/), { target: { value: '수동 내용' } })

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /1개 항목 시드/ })).toBeEnabled(),
    )

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /1개 항목 시드/ }))
    })

    await waitFor(() => expect(spy).toHaveBeenCalled())
    expect(spy.mock.calls[0][0]).toEqual([
      { key: 'm1', title: '수동 제목', content: '수동 내용' },
    ])
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })
})

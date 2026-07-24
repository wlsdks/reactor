import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '../../../test/utils'
import { ChatInspectorManager } from '../ui/ChatInspectorManager'
import * as chatApi from '../api'
import { ApiError } from '../../../shared/api/errors'

vi.mock('../../personas/api', () => ({
  listPersonas: vi.fn().mockResolvedValue([]),
}))

vi.mock('../../sessions/api', () => ({
  listModels: vi.fn().mockResolvedValue({ models: [], defaultModel: '' }),
}))

vi.mock('../../prompts/api', () => ({
  listTemplates: vi.fn().mockResolvedValue([]),
}))

vi.mock('../api', () => ({
  sendChat: vi.fn(),
  streamChat: vi.fn(),
}))

const sendChatMock = vi.mocked(chatApi.sendChat)

function renderManager() {
  const router = createMemoryRouter(
    [{ path: '/chat-inspector', element: <ChatInspectorManager /> }],
    { initialEntries: ['/chat-inspector'] },
  )
  return { ...render(<RouterProvider router={router} />), router }
}

describe('ChatInspectorManager', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders one inspector workspace without duplicate release navigation', () => {
    renderManager()
    // Page title uses t('nav.chatInspector') → 'Chat Inspector'
    expect(screen.getByText('Chat Inspector')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' })).not.toBeInTheDocument()
    // Mode tabs: use i18n keys since no bundle is loaded for these keys
    expect(screen.getByText('chatInspector.modeChat')).toBeInTheDocument()
    expect(screen.getByText('chatInspector.modeStream')).toBeInTheDocument()
  })

  it('keeps stream mode addressable in the URL', () => {
    const { router } = renderManager()

    fireEvent.click(screen.getByRole('tab', { name: 'chatInspector.modeStream' }))

    expect(router.state.location.search).toBe('?mode=stream')
    expect(screen.getByRole('tab', { name: 'chatInspector.modeStream' })).toHaveAttribute('aria-selected', 'true')
  })

  it('does NOT render multipart tab or quick prompts', () => {
    renderManager()
    // No multipart / "File + Chat" tab
    expect(screen.queryByText('chatInspector.modeMultipart')).not.toBeInTheDocument()
    // No quick prompt buttons
    expect(screen.queryByText('chatInspector.quick.health')).not.toBeInTheDocument()
    expect(screen.queryByText('chatInspector.quick.summary')).not.toBeInTheDocument()
    expect(screen.queryByText('chatInspector.quick.incident')).not.toBeInTheDocument()
  })

  it('renders ConfigToolbar dropdowns', () => {
    renderManager()
    // ConfigToolbar renders labels linked to selects via htmlFor
    expect(screen.getByLabelText('chatInspector.config.persona')).toBeInTheDocument()
    expect(screen.getByLabelText('chatInspector.config.model')).toBeInTheDocument()
    expect(screen.getByLabelText('chatInspector.config.template')).toBeInTheDocument()
  })

  it('renders message textarea and run button on the same screen as configure', () => {
    renderManager()
    // After the wizard merge, configure (sidebar) and message+run (main) co-exist on one screen.
    expect(screen.getByLabelText('chatInspector.message')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'chatInspector.runChat' })).toBeInTheDocument()
  })

  it('keeps the question workflow before optional execution settings in reading order', () => {
    renderManager()

    const message = screen.getByLabelText('chatInspector.message')
    const persona = screen.getByLabelText('chatInspector.config.persona')

    expect(message.compareDocumentPosition(persona) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('keeps advanced execution settings in a closed native disclosure until requested', () => {
    renderManager()

    const advanced = screen.getByText('chatInspector.advanced').closest('details')
    expect(advanced).toBeInTheDocument()
    expect(advanced).not.toHaveAttribute('open')
  })

  it('does not render the legacy 3-step wizard step bar', () => {
    renderManager()
    // StepProgress is gone — no list with the steps aria-label, no step buttons.
    expect(screen.queryByRole('list', { name: 'chatInspectorPage.steps.ariaLabel' })).not.toBeInTheDocument()
    expect(screen.queryByTestId('step-progress-configure')).not.toBeInTheDocument()
    expect(screen.queryByTestId('step-progress-execute')).not.toBeInTheDocument()
    expect(screen.queryByTestId('step-progress-inspect')).not.toBeInTheDocument()
  })

  it('shows error when submitting empty message', async () => {
    renderManager()
    fireEvent.click(screen.getByRole('button', { name: 'chatInspector.runChat' }))

    await waitFor(() => {
      expect(screen.getByText('chatInspector.errors.messageRequired')).toBeInTheDocument()
    })
  })

  it('displays response with StatusBar after successful chat run', async () => {
    sendChatMock.mockResolvedValueOnce({
      content: 'Test response content',
      success: true,
      model: 'gemini-2.0-flash',
      toolsUsed: ['web_search'],
      durationMs: 523,
      metadata: { tokenUsage: { promptTokens: 100, completionTokens: 200, totalTokens: 300 } },
    })

    renderManager()
    fireEvent.change(screen.getByLabelText('chatInspector.message'), {
      target: { value: 'What is the system status?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'chatInspector.runChat' }))

    await waitFor(() => {
      expect(screen.getByText('Test response content')).toBeInTheDocument()
    })

    // StatusBar renders success/duration/tokens via i18n keys
    expect(screen.getByText('chatInspector.response_meta.success')).toBeInTheDocument()
    expect(screen.getByText('chatInspector.response_meta.duration')).toBeInTheDocument()
    expect(screen.getByText('chatInspector.response_meta.tokens')).toBeInTheDocument()

    const answer = screen.getByTestId('chat-inspector-response-content')
    expect(answer.tagName).toBe('DIV')
    expect(screen.getByText('gemini-2.0-flash').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('web_search').closest('details')).not.toHaveAttribute('open')

    expect(sendChatMock).toHaveBeenCalledTimes(1)
    expect(sendChatMock).toHaveBeenCalledWith(expect.objectContaining({ runtime: 'langgraph' }))
  })

  it('keeps failed response codes and messages out of the primary reading path', async () => {
    sendChatMock.mockResolvedValueOnce({
      content: null,
      success: false,
      toolsUsed: [],
      errorCode: 'RATE_LIMITED',
      errorMessage: 'Rate limit exceeded',
    })

    renderManager()
    fireEvent.change(screen.getByLabelText('chatInspector.message'), {
      target: { value: 'test query' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'chatInspector.runChat' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('chatInspector.errors.rateLimited')
    })
    expect(screen.getByRole('alert')).not.toHaveTextContent('RATE_LIMITED')
    expect(screen.getByRole('alert')).not.toHaveTextContent('Rate limit exceeded')
    expect(screen.getByText('RATE_LIMITED').closest('details')).not.toHaveAttribute('open')
  })

  it('hides raw server errors when the chat request rejects', async () => {
    sendChatMock.mockRejectedValueOnce(
      new ApiError(503, 'SERVER_ERROR', 'RagIngestionCandidateStore 미등록 — DB 미구성'),
    )

    renderManager()
    fireEvent.change(screen.getByLabelText('chatInspector.message'), { target: { value: 'test query' } })
    fireEvent.click(screen.getByRole('button', { name: 'chatInspector.runChat' }))

    const alert = await screen.findByRole('alert')
    expect(alert).not.toHaveTextContent('RagIngestionCandidateStore')
    expect(alert).not.toHaveTextContent('DB 미구성')
  })

  it('hides raw request URLs when the provider times out', async () => {
    sendChatMock.mockRejectedValueOnce(new Error('Request timed out: POST http://127.0.0.1:3001/api/chat'))

    renderManager()
    fireEvent.change(screen.getByLabelText('chatInspector.message'), { target: { value: 'test query' } })
    fireEvent.click(screen.getByRole('button', { name: 'chatInspector.runChat' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('chatInspector.errors.requestTimeout')
    expect(screen.queryByText(/127\.0\.0\.1/)).not.toBeInTheDocument()
  })

  it('keeps unclassified request details closed while showing a Korean recovery message', async () => {
    sendChatMock.mockRejectedValueOnce(new Error('InternalRunCoordinator failed to acquire a lease'))

    renderManager()
    fireEvent.change(screen.getByLabelText('chatInspector.message'), { target: { value: 'test query' } })
    fireEvent.click(screen.getByRole('button', { name: 'chatInspector.runChat' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('chatInspector.errors.requestFailed')
    expect(alert).not.toHaveTextContent('InternalRunCoordinator')
    expect(screen.getByText('InternalRunCoordinator failed to acquire a lease').closest('details')).not.toHaveAttribute('open')
  })

  it('Restart button clears the result and message', async () => {
    sendChatMock.mockResolvedValueOnce({
      content: 'Test response content',
      success: true,
      model: 'gemini-2.0-flash',
      toolsUsed: [],
      durationMs: 100,
    })

    renderManager()
    fireEvent.change(screen.getByLabelText('chatInspector.message'), {
      target: { value: 'first query' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'chatInspector.runChat' }))

    await waitFor(() => {
      expect(screen.getByText('Test response content')).toBeInTheDocument()
    })

    // Restart button is only mounted after a result exists
    fireEvent.click(screen.getByRole('button', { name: 'chatInspectorPage.steps.restart' }))

    // Message cleared, result removed, empty state shown again
    expect((screen.getByLabelText('chatInspector.message') as HTMLTextAreaElement).value).toBe('')
    expect(screen.queryByText('Test response content')).not.toBeInTheDocument()
  })
})

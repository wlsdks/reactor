import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '../../../test/utils'
import { PromptsManager } from '../ui/PromptsManager'
import * as promptsApi from '../api'
import type { TemplateDetailResponse, TemplateResponse } from '../types'

vi.mock('../api', () => ({
  listTemplates: vi.fn(),
  getTemplate: vi.fn(),
  createTemplate: vi.fn(),
  updateTemplate: vi.fn(),
  deleteTemplate: vi.fn(),
  createVersion: vi.fn(),
  activateVersion: vi.fn(),
  archiveVersion: vi.fn(),
}))

const listTemplatesMock = vi.mocked(promptsApi.listTemplates)
const getTemplateMock = vi.mocked(promptsApi.getTemplate)

function buildTemplate(overrides: Partial<TemplateResponse> = {}): TemplateResponse {
  return {
    id: 'tpl-1',
    name: 'Support Prompt v2',
    description: 'Customer support with empathy guidelines',
    createdAt: 1710000000000,
    updatedAt: 1710001000000,
    ...overrides,
  }
}

function buildTemplateDetail(overrides: Partial<TemplateDetailResponse> = {}): TemplateDetailResponse {
  return {
    ...buildTemplate(),
    activeVersion: {
      id: 'ver-1',
      templateId: 'tpl-1',
      version: 2,
      content: 'Answer with empathy and cite verified sources.',
      status: 'ACTIVE',
      changeLog: 'Clarified source guidance',
      createdAt: 1710002000000,
    },
    versions: [
      {
        id: 'ver-1',
        templateId: 'tpl-1',
        version: 2,
        content: 'Answer with empathy and cite verified sources.',
        status: 'ACTIVE',
        changeLog: 'Clarified source guidance',
        createdAt: 1710002000000,
      },
    ],
    ...overrides,
  }
}

function renderManager() {
  const router = createMemoryRouter(
    [{ path: '/', element: <PromptsManager /> }],
    { initialEntries: ['/'] },
  )
  return render(<RouterProvider router={router} />)
}

describe('PromptsManager', () => {
  beforeEach(() => {
    listTemplatesMock.mockResolvedValue([
      buildTemplate(),
      buildTemplate({ id: 'tpl-2', name: 'Sales Assistant Prompt', description: 'Sales-facing versioned prompt' }),
    ])
    getTemplateMock.mockResolvedValue(buildTemplateDetail())
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders the local template workflow without a duplicate release link', () => {
    renderManager()

    expect(screen.getByText('nav.prompts')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'prompts.createTemplate' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' })).not.toBeInTheDocument()
  })

  it('shows a compact selection list without row-level destructive actions', async () => {
    renderManager()

    await waitFor(() => {
      expect(screen.getByText('Support Prompt v2')).toBeInTheDocument()
      expect(screen.getByText('Sales Assistant Prompt')).toBeInTheDocument()
    })

    expect(screen.getByText('prompts.listCount')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
  })

  it('shows the verified empty state only after the list succeeds', async () => {
    listTemplatesMock.mockResolvedValueOnce([])
    renderManager()

    await waitFor(() => {
      expect(screen.getByText('prompts.empty')).toBeInTheDocument()
    })
  })

  it('fails closed when the list is unavailable and keeps the raw cause closed', async () => {
    listTemplatesMock.mockRejectedValue(new Error('HTTP 503'))
    renderManager()

    await waitFor(() => {
      expect(screen.getByText('prompts.unavailableTitle')).toBeInTheDocument()
    })

    expect(screen.queryByText('prompts.empty')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    const recovery = screen.getByText('prompts.recoveryGuideTitle').closest('details')
    expect(recovery).not.toHaveAttribute('open')
  })

  it('opens actions and readable change history only after selecting a template', async () => {
    renderManager()
    await screen.findByText('Support Prompt v2')

    fireEvent.click(screen.getByText('Support Prompt v2'))

    await waitFor(() => {
      expect(screen.getByText('Answer with empathy and cite verified sources.')).toBeInTheDocument()
    })

    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
    expect(screen.getByText('prompts.versionStatus.active')).toBeInTheDocument()
    expect(document.querySelector('.prompt-version__content')?.tagName).toBe('P')
    const technical = screen.getByText('prompts.technicalDetails').closest('details')
    expect(technical).not.toHaveAttribute('open')
  })

  it('shows create template form when the page action is selected', async () => {
    renderManager()
    await screen.findByText('Support Prompt v2')

    fireEvent.click(screen.getByRole('button', { name: 'prompts.createTemplate' }))

    await waitFor(() => {
      expect(screen.getAllByText('prompts.createTemplate').length).toBeGreaterThanOrEqual(2)
    })
  })
})

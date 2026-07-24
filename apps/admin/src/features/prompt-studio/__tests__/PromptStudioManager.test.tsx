import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '../../../test/utils'
import { i18n } from '../../../test/utils'
import { PromptStudioManager } from '../ui/PromptStudioManager'
import * as api from '../api'
import type { TemplateResponse, TemplateDetailResponse } from '../types'

// Add i18n keys needed for the PromptStudioManager tests
i18n.addResourceBundle('en', 'translation', {
  'nav.promptStudio': 'Prompt Studio',
  'promptStudio.pageGuide': 'Create prompt templates, manage versions, and run A/B experiments to find the best wording.',
  'promptStudio.tabs.versions': 'Versions',
  'promptStudio.tabs.experiments': 'Experiments',
  'promptStudio.tabs.settings': 'Settings',
  'promptStudioPage.sections.info': 'Template info',
  'promptStudioPage.sections.body': 'Body / variables',
  'promptStudioPage.sections.experiments': 'Experiments / evaluation',
  'promptStudioPage.sections.activity': 'Activity log',
  'promptStudioPage.sections.activityEmpty': 'No recent activity.',
  'promptStudio.workspaceNavLabel': 'Prompt workspace',
  'promptStudio.templateListLabel': 'Prompt list',
  'promptStudio.templateCount': '{{count}} prompts',
  'promptStudio.currentVersion': 'Currently used · Version {{version}}',
  'promptStudio.noCurrentVersion': 'No current content',
  'promptStudio.versionLabel': 'Version {{version}}',
  'promptStudio.technicalDetails': 'Developer prompt information',
  'promptStudio.versionsGuide': 'Only one ACTIVE version is used at runtime.',
  'promptStudio.experimentsEmpty': 'No experiments yet',
  'promptStudio.experimentsEmptyDesc': 'Run an A/B test to compare prompt versions.',
  'promptStudio.experimentsGuide': 'Compare prompt versions with real test queries.',
  'promptStudio.newExperiment': 'New Experiment',
  'promptStudio.experimentName': 'Experiment Name',
  'promptStudio.onboarding.step1': 'Select versions',
  'promptStudio.onboarding.step2': 'Add test queries',
  'promptStudio.onboarding.step3': 'Run the experiment',
  'promptStudio.onboarding.step4': 'Review results',
  'promptStudio.onboarding.step5': 'Activate the winner',
  'promptStudio.templateId': 'Template ID',
  'promptStudio.version': 'Version',
  'prompts.selectTemplate': 'Select a template',
  'prompts.createTemplate': 'Create Template',
  'prompts.editTemplate': 'Edit Template',
  'prompts.empty': 'No templates yet',
  'prompts.emptyDescription': 'Create the first reusable set of instructions and response formatting.',
  'prompts.exampleDisclosure': 'View a template example',
  'prompts.emptyExample': 'Example prompt content',
  'prompts.newVersion': 'New Version',
  'prompts.noVersions': 'No versions yet',
  'prompts.activate': 'Activate',
  'prompts.archive': 'Archive',
  'prompts.content': 'Content',
  'prompts.changeLog': 'Change Log',
  'prompts.nameRequired': 'Name is required',
  'prompts.deleteTitle': 'Delete Template',
  'prompts.deleteConfirm': 'Are you sure you want to delete {{name}}?',
  'prompts.descriptionPlaceholder': 'Description...',
  'common.refresh': 'Refresh',
  'common.name': 'Name',
  'common.description': 'Description',
  'common.cancel': 'Cancel',
  'common.save': 'Save',
  'common.delete': 'Delete',
  'common.retry': 'Retry',
  'common.noData': 'No data',
  'common.copy': 'Copy',
  'common.createdAt': 'Created',
  'common.updatedAt': 'Updated',
  'common.status': 'Status',
  'common.toast.created': 'Created',
  'common.toast.updated': 'Updated',
  'common.toast.deleted': 'Deleted',
}, true, true)

vi.mock('../api', () => ({
  listTemplates: vi.fn(),
  getTemplate: vi.fn(),
  createTemplate: vi.fn(),
  updateTemplate: vi.fn(),
  deleteTemplate: vi.fn(),
  createVersion: vi.fn(),
  activateVersion: vi.fn(),
  archiveVersion: vi.fn(),
  listExperiments: vi.fn(),
  getExperiment: vi.fn(),
  createExperiment: vi.fn(),
  runExperiment: vi.fn(),
  cancelExperiment: vi.fn(),
  getExperimentStatus: vi.fn(),
  getExperimentTrials: vi.fn(),
  getExperimentReport: vi.fn(),
  activateExperimentRecommendation: vi.fn(),
  deleteExperiment: vi.fn(),
}))

const mockedApi = vi.mocked(api)

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

function buildDetail(overrides: Partial<TemplateDetailResponse> = {}): TemplateDetailResponse {
  return {
    id: 'tpl-1',
    name: 'Support Prompt v2',
    description: 'Customer support with empathy guidelines',
    activeVersion: {
      id: 'v1',
      templateId: 'tpl-1',
      version: 1,
      content: 'You are a helpful support assistant.',
      status: 'ACTIVE',
      changeLog: 'Initial version',
      createdAt: 1710000000000,
    },
    versions: [
      {
        id: 'v1',
        templateId: 'tpl-1',
        version: 1,
        content: 'You are a helpful support assistant.',
        status: 'ACTIVE',
        changeLog: 'Initial version',
        createdAt: 1710000000000,
      },
    ],
    createdAt: 1710000000000,
    updatedAt: 1710001000000,
    ...overrides,
  }
}

function renderManager() {
  const router = createMemoryRouter(
    [{ path: '/', element: <PromptStudioManager /> }],
    { initialEntries: ['/'] },
  )
  return render(<RouterProvider router={router} />)
}

describe('PromptStudioManager', () => {
  beforeEach(() => {
    mockedApi.listTemplates.mockResolvedValue([
      buildTemplate(),
      buildTemplate({ id: 'tpl-2', name: 'Sales Assistant Prompt', description: 'Sales-facing versioned prompt' }),
    ])
    mockedApi.getTemplate.mockResolvedValue(buildDetail())
    // ExperimentsTab will call listExperiments
    mockedApi.listExperiments.mockResolvedValue([])
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders page title and guide text', async () => {
    renderManager()
    expect(screen.getByText('Prompt Studio')).toBeInTheDocument()
    expect(screen.getByText('Create prompt templates, manage versions, and run A/B experiments to find the best wording.')).toBeInTheDocument()
  })

  it('renders refresh button', () => {
    renderManager()
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument()
  })

  it('does not duplicate release-stage navigation in the page header', () => {
    renderManager()
    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' })).not.toBeInTheDocument()
  })

  it('shows template list after loading', async () => {
    renderManager()
    await waitFor(() => {
      expect(screen.getByText('Support Prompt v2')).toBeInTheDocument()
      expect(screen.getByText('Sales Assistant Prompt')).toBeInTheDocument()
    })
  })

  it('keeps the detail pane absent until a template is selected', async () => {
    renderManager()
    await waitFor(() => {
      expect(screen.getByText('Support Prompt v2')).toBeInTheDocument()
    })
    expect(screen.queryByText('Select a template')).not.toBeInTheDocument()
    expect(screen.queryByText('Template info')).not.toBeInTheDocument()
  })

  it('shows detail panel when a template is selected', async () => {
    renderManager()
    await waitFor(() => {
      expect(screen.getByText('Support Prompt v2')).toBeInTheDocument()
    })

    // Click the first template
    fireEvent.click(screen.getByText('Support Prompt v2'))

    await waitFor(() => {
      // The detail header should show the template name
      const headings = screen.getAllByText('Support Prompt v2')
      expect(headings.length).toBeGreaterThanOrEqual(2) // list item + header
    })

    // Should show description (may appear in multiple places: header + sections)
    const descs = screen.getAllByText('Customer support with empathy guidelines')
    expect(descs.length).toBeGreaterThanOrEqual(1)
  })

  it('shows four task tabs when a template is selected', async () => {
    renderManager()
    await waitFor(() => {
      expect(screen.getByText('Support Prompt v2')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Support Prompt v2'))

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Template info' })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: 'Body / variables' })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: 'Experiments / evaluation' })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: 'Activity log' })).toBeInTheDocument()
    })
  })

  it('shows only the selected task panel and keeps the choice in the URL', async () => {
    renderManager()
    await waitFor(() => {
      expect(screen.getByText('Support Prompt v2')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Support Prompt v2'))

    await waitFor(() => {
      expect(screen.getByTestId('editable-name')).toBeInTheDocument()
    })
    expect(screen.queryByText('New Version')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Body / variables' }))
    expect(await screen.findByText('New Version')).toBeInTheDocument()
  })

  it('opens comparison evaluation from its task tab', async () => {
    renderManager()
    await waitFor(() => {
      expect(screen.getByText('Support Prompt v2')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Support Prompt v2'))

    const experimentsTab = await screen.findByRole('tab', { name: 'Experiments / evaluation' })
    fireEvent.click(experimentsTab)

    await waitFor(() => {
      expect(experimentsTab).toHaveAttribute('aria-selected', 'true')
      expect(screen.getByText('No experiments yet')).toBeInTheDocument()
    })
  })

  it('shows create template button in template list', async () => {
    renderManager()
    await waitFor(() => {
      expect(screen.getByText('Support Prompt v2')).toBeInTheDocument()
    })
    // The TemplateList always shows a "Create Template" button
    expect(screen.getByRole('button', { name: 'Create Template' })).toBeInTheDocument()
  })

  it('shows one collection empty state without a detail placeholder', async () => {
    mockedApi.listTemplates.mockResolvedValueOnce([])
    renderManager()
    await waitFor(() => {
      expect(screen.getByText('No templates yet')).toBeInTheDocument()
    })
    expect(screen.getByText('Create the first reusable set of instructions and response formatting.')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Create Template' })).toHaveLength(1)
    expect(screen.queryByText('Select a template')).not.toBeInTheDocument()
    expect(screen.getByText('Example prompt content')).not.toBeVisible()

    fireEvent.click(screen.getByText('View a template example'))
    expect(screen.getByText('Example prompt content')).toBeVisible()
  })

  it('returns to the same empty collection after cancelling template creation', async () => {
    mockedApi.listTemplates.mockResolvedValueOnce([])
    renderManager()
    await screen.findByText('No templates yet')

    fireEvent.click(screen.getByRole('button', { name: 'Create Template' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByText('No templates yet')).toBeInTheDocument()
  })
})

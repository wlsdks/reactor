import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { ReactNode } from 'react'
import { ConfigToolbar } from '../ui/ConfigToolbar'
import { ApiError } from '../../../shared/api/errors'

// --- Mocks ---

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: vi.fn() },
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'chatInspector.config.persona': 'Persona',
        'chatInspector.config.model': 'Model',
        'chatInspector.config.template': 'Prompt Template',
        'chatInspector.config.none': 'None',
        'chatInspector.config.nonePersona': 'No persona',
        'chatInspector.config.noneModel': 'No model',
        'chatInspector.config.noneTemplate': 'No template',
        'chatInspector.config.default': '(default)',
        'chatInspector.config.retry': 'Retry',
        'chatInspector.config.permissionTitle': 'Admin access required',
        'chatInspector.config.permissionDescription': 'Check the admin account connection.',
        'chatInspector.config.unavailableTitle': 'Some settings are unavailable',
        'chatInspector.config.unavailableDescription': 'Check the connection and try again.',
        'chatInspector.config.unavailableValue': 'Unavailable',
      }
      return map[key] ?? key
    },
  }),
}))

vi.mock('../../personas', () => ({ listPersonas: vi.fn() }))
vi.mock('../../sessions', () => ({ listModels: vi.fn() }))
vi.mock('../../prompts', () => ({ listTemplates: vi.fn() }))

import { listPersonas } from '../../personas'
import { listModels } from '../../sessions'
import { listTemplates } from '../../prompts'

const listPersonasMock = vi.mocked(listPersonas)
const listModelsMock = vi.mocked(listModels)
const listTemplatesMock = vi.mocked(listTemplates)

// --- Helpers ---

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
}

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={createQueryClient()}>
      {children}
    </QueryClientProvider>
  )
}

const defaultProps = {
  personaId: '',
  modelId: '',
  templateId: '',
  onPersonaChange: vi.fn(),
  onModelChange: vi.fn(),
  onTemplateChange: vi.fn(),
}

// --- Mock Data ---

const mockPersonas = [
  { id: 'p1', name: 'Support Agent', systemPrompt: '', isDefault: false, description: null, responseGuideline: null, welcomeMessage: null, promptTemplateId: null, icon: null, isActive: true, createdAt: 0, updatedAt: 0 },
  { id: 'p2', name: 'Sales Bot', systemPrompt: '', isDefault: false, description: null, responseGuideline: null, welcomeMessage: null, promptTemplateId: null, icon: null, isActive: true, createdAt: 0, updatedAt: 0 },
  { id: 'p3', name: 'Inactive Persona', systemPrompt: '', isDefault: false, description: null, responseGuideline: null, welcomeMessage: null, promptTemplateId: null, icon: null, isActive: false, createdAt: 0, updatedAt: 0 },
]

const mockModels = {
  models: [
    { name: 'gpt-4o', isDefault: true },
    { name: 'gpt-3.5-turbo', isDefault: false },
  ],
  defaultModel: 'gpt-4o',
}

const mockTemplates = [
  { id: 't1', name: 'Greeting Template', description: '', createdAt: 0, updatedAt: 0 },
  { id: 't2', name: 'FAQ Template', description: '', createdAt: 0, updatedAt: 0 },
]

// --- Tests ---

describe('ConfigToolbar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listPersonasMock.mockResolvedValue(mockPersonas)
    listModelsMock.mockResolvedValue(mockModels)
    listTemplatesMock.mockResolvedValue(mockTemplates)
  })

  it('renders three dropdowns with labels', async () => {
    render(<ConfigToolbar {...defaultProps} />, { wrapper })

    await waitFor(() => {
      expect(screen.getByLabelText('Persona')).toBeInTheDocument()
      expect(screen.getByLabelText('Model')).toBeInTheDocument()
      expect(screen.getByLabelText('Prompt Template')).toBeInTheDocument()
    })
  })

  it('populates persona dropdown with fetched data (2 active + No persona = 3 options)', async () => {
    render(<ConfigToolbar {...defaultProps} />, { wrapper })

    await waitFor(() => {
      const select = screen.getByLabelText('Persona') as HTMLSelectElement
      const options = select.querySelectorAll('option')
      // Support Agent + Sales Bot + No persona = 3 (Inactive Persona filtered out)
      // "No persona" is last, not first.
      expect(options).toHaveLength(3)
      expect(options[0].textContent).toBe('Support Agent')
      expect(options[1].textContent).toBe('Sales Bot')
      expect(options[2].textContent).toBe('No persona')
    })
  })

  it('shows (default) suffix on default model and places No model last', async () => {
    render(<ConfigToolbar {...defaultProps} />, { wrapper })

    await waitFor(() => {
      const select = screen.getByLabelText('Model') as HTMLSelectElement
      const options = select.querySelectorAll('option')
      // Display names stay readable while the option values keep the backend IDs.
      expect(options).toHaveLength(3)
      expect(options[0].textContent).toBe('GPT-4o (default)')
      expect(options[0].value).toBe('gpt-4o')
      expect(options[1].textContent).toBe('GPT-3.5 Turbo')
      expect(options[1].value).toBe('gpt-3.5-turbo')
      expect(options[2].textContent).toBe('No model')
    })
  })

  it('auto-selects default persona when personaId is empty', async () => {
    const onPersonaChange = vi.fn()
    const personasWithDefault = [
      { ...mockPersonas[0], isDefault: false },
      { ...mockPersonas[1], isDefault: true }, // Sales Bot is default
      mockPersonas[2],
    ]
    listPersonasMock.mockResolvedValue(personasWithDefault)

    render(<ConfigToolbar {...defaultProps} onPersonaChange={onPersonaChange} />, { wrapper })

    await waitFor(() => {
      expect(onPersonaChange).toHaveBeenCalledWith('p2')
    })
  })

  it('falls back to first active persona when none marked default', async () => {
    const onPersonaChange = vi.fn()
    render(<ConfigToolbar {...defaultProps} onPersonaChange={onPersonaChange} />, { wrapper })

    await waitFor(() => {
      expect(onPersonaChange).toHaveBeenCalledWith('p1')
    })
  })

  it('auto-selects default model when modelId is empty', async () => {
    const onModelChange = vi.fn()
    render(<ConfigToolbar {...defaultProps} onModelChange={onModelChange} />, { wrapper })

    await waitFor(() => {
      expect(onModelChange).toHaveBeenCalledWith('gpt-4o')
    })
  })

  it('does not override existing persona/model selections', async () => {
    const onPersonaChange = vi.fn()
    const onModelChange = vi.fn()
    render(
      <ConfigToolbar
        {...defaultProps}
        personaId="p1"
        modelId="gpt-3.5-turbo"
        onPersonaChange={onPersonaChange}
        onModelChange={onModelChange}
      />,
      { wrapper },
    )

    // Let queries resolve
    await waitFor(() => {
      const options = screen.getByLabelText('Persona').querySelectorAll('option')
      expect(options.length).toBeGreaterThan(1)
    })

    // The auto-select effect should NOT fire when a value is already set.
    expect(onPersonaChange).not.toHaveBeenCalled()
    expect(onModelChange).not.toHaveBeenCalled()
  })

  it('keeps prompt template defaulting to No template (last option)', async () => {
    render(<ConfigToolbar {...defaultProps} />, { wrapper })

    await waitFor(() => {
      const select = screen.getByLabelText('Prompt Template') as HTMLSelectElement
      const options = select.querySelectorAll('option')
      // Greeting + FAQ + No template = 3
      expect(options).toHaveLength(3)
      expect(options[2].textContent).toBe('No template')
      expect(options[2].getAttribute('value')).toBe('')
    })
  })

  it('applies placeholder class when template selection is empty', async () => {
    render(<ConfigToolbar {...defaultProps} />, { wrapper })

    await waitFor(() => {
      const select = screen.getByLabelText('Prompt Template') as HTMLSelectElement
      expect(select.className).toContain('config-toolbar__select--placeholder')
    })
  })

  it('calls onPersonaChange when selection changes', async () => {
    const onPersonaChange = vi.fn()
    render(<ConfigToolbar {...defaultProps} onPersonaChange={onPersonaChange} />, { wrapper })

    await waitFor(() => {
      expect(screen.getByLabelText('Persona').querySelectorAll('option').length).toBeGreaterThan(1)
    })

    fireEvent.change(screen.getByLabelText('Persona'), { target: { value: 'p1' } })
    expect(onPersonaChange).toHaveBeenCalledWith('p1')
  })

  it('shows None option that clears selection', async () => {
    const onPersonaChange = vi.fn()
    render(<ConfigToolbar {...defaultProps} personaId="p1" onPersonaChange={onPersonaChange} />, { wrapper })

    await waitFor(() => {
      expect(screen.getByLabelText('Persona').querySelectorAll('option').length).toBeGreaterThan(1)
    })

    fireEvent.change(screen.getByLabelText('Persona'), { target: { value: '' } })
    expect(onPersonaChange).toHaveBeenCalledWith('')
  })

  it('filters out inactive personas', async () => {
    render(<ConfigToolbar {...defaultProps} />, { wrapper })

    await waitFor(() => {
      const select = screen.getByLabelText('Persona') as HTMLSelectElement
      const optionTexts = Array.from(select.querySelectorAll('option')).map(o => o.textContent)
      expect(optionTexts).not.toContain('Inactive Persona')
    })
  })

  it('groups failed selectors into one retryable connection notice', async () => {
    listPersonasMock.mockRejectedValue(new Error('Network error'))

    render(<ConfigToolbar {...defaultProps} />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Some settings are unavailable')).toBeInTheDocument()
      expect(screen.getByText('Unavailable')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    })
  })

  it('describes a 403 as an account permission issue instead of a server failure', async () => {
    listPersonasMock.mockRejectedValue(new Error('Network error'))
    listTemplatesMock.mockRejectedValue(new ApiError(403, 'FORBIDDEN', 'admin access required'))

    render(<ConfigToolbar {...defaultProps} />, { wrapper })

    expect(await screen.findByText('Admin access required')).toBeInTheDocument()
    expect(screen.getByText('Check the admin account connection.')).toBeInTheDocument()
    expect(screen.queryByText('Failed to load')).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Retry' })).toHaveLength(1)
  })
})

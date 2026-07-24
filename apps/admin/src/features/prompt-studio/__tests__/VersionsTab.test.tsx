import { render, screen, fireEvent } from '../../../test/utils'
import { describe, it, expect, vi } from 'vitest'
import { VersionsTab } from '../ui/VersionsTab'
import type { TemplateDetailResponse, VersionResponse } from '../types'
import { i18n } from '../../../test/utils'

i18n.addResourceBundle('en', 'translation', {
  'promptStudio.versionLabel': 'Version {{version}}',
  'promptStudio.versionStatus.active': 'Currently used',
  'promptStudio.versionStatus.draft': 'Draft for review',
  'promptStudio.versionStatus.archived': 'Previous record',
  'promptStudio.versionStatus.unknown': 'Needs review',
}, true, true)

function makeVersion(overrides: Partial<VersionResponse> = {}): VersionResponse {
  return {
    id: 'v1',
    templateId: 't1',
    version: 1,
    content: 'Hello world prompt content',
    status: 'DRAFT',
    changeLog: '',
    createdAt: 1700000000000,
    ...overrides,
  }
}

function makeTemplate(
  versions: VersionResponse[] = [],
  activeVersion: VersionResponse | null = null,
): TemplateDetailResponse {
  return {
    id: 't1',
    name: 'Test Template',
    description: 'A test template',
    activeVersion,
    versions,
    createdAt: 1700000000000,
    updatedAt: 1700000000000,
  }
}

const defaultProps = {
  onCreateVersion: vi.fn(),
  onActivate: vi.fn(),
  onArchive: vi.fn(),
  saving: false,
}

describe('VersionsTab', () => {
  it('renders version rows with readable states', () => {
    const draftVersion = makeVersion({ id: 'v1', version: 1, status: 'DRAFT' })
    const activeVersion = makeVersion({ id: 'v2', version: 2, status: 'ACTIVE' })
    const template = makeTemplate([draftVersion, activeVersion], activeVersion)

    render(<VersionsTab template={template} {...defaultProps} />)

    expect(screen.getByText('Version 1')).toBeInTheDocument()
    expect(screen.getByText('Version 2')).toBeInTheDocument()
    expect(screen.getByText('Draft for review')).toBeInTheDocument()
    expect(screen.getByText('Currently used')).toBeInTheDocument()
  })

  it('shows guide text', () => {
    const template = makeTemplate([])

    render(<VersionsTab template={template} {...defaultProps} />)

    expect(screen.getByText('promptStudio.versionsGuide')).toBeInTheDocument()
  })

  it('calls onActivate when clicking Activate on a DRAFT version', () => {
    const onActivate = vi.fn()
    const draftVersion = makeVersion({ id: 'v1', version: 1, status: 'DRAFT' })
    const template = makeTemplate([draftVersion])

    render(
      <VersionsTab template={template} {...defaultProps} onActivate={onActivate} />,
    )

    fireEvent.click(screen.getByText('prompts.activate'))
    expect(onActivate).toHaveBeenCalledWith(draftVersion)
  })

  it('calls onArchive when clicking Archive on an ACTIVE version', () => {
    const onArchive = vi.fn()
    const activeVersion = makeVersion({ id: 'v2', version: 2, status: 'ACTIVE' })
    const template = makeTemplate([activeVersion], activeVersion)

    render(
      <VersionsTab template={template} {...defaultProps} onArchive={onArchive} />,
    )

    fireEvent.click(screen.getByText('prompts.archive'))
    expect(onArchive).toHaveBeenCalledWith(activeVersion)
  })

  it('shows "New Version" button', () => {
    const template = makeTemplate([])

    render(<VersionsTab template={template} {...defaultProps} />)

    expect(screen.getByText('prompts.newVersion')).toBeInTheDocument()
  })

  it('shows empty state when no versions', () => {
    const template = makeTemplate([])

    render(<VersionsTab template={template} {...defaultProps} />)

    expect(screen.getByText('prompts.noVersions')).toBeInTheDocument()
  })

  it('shows changelog text when present', () => {
    const version = makeVersion({
      id: 'v1',
      version: 1,
      changeLog: 'Fixed typo in greeting',
    })
    const template = makeTemplate([version])

    render(<VersionsTab template={template} {...defaultProps} />)

    expect(screen.getByText('Fixed typo in greeting')).toBeInTheDocument()
  })

  it('truncates content preview to 300 characters', () => {
    const longContent = 'A'.repeat(350)
    const version = makeVersion({ id: 'v1', version: 1, content: longContent })
    const template = makeTemplate([version])

    render(<VersionsTab template={template} {...defaultProps} />)

    const contentPreview = screen.getByText((_, element) => {
      return element?.tagName === 'P' && element.textContent?.startsWith('AAAA') === true
    })
    expect(contentPreview.textContent).toHaveLength(301) // 300 chars + ellipsis
  })
})

import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { i18n, render, screen } from '../../../test/utils'
import {
  RELEASE_WORKFLOW_ANCHOR_PATH,
  RELEASE_WORKFLOW_PATHS_BY_ID,
} from '../../releaseWorkflow'
import { ReleaseWorkflowBacklink } from '../ReleaseWorkflowBacklink'

describe('ReleaseWorkflowBacklink', () => {
  it('links release operation pages back to the release workflow', () => {
    render(
      <MemoryRouter>
        <ReleaseWorkflowBacklink />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'common.releaseWorkflowBacklink' }))
      .toHaveAttribute('href', RELEASE_WORKFLOW_ANCHOR_PATH)
  })

  it('includes the optional release step number in the accessible link name', () => {
    i18n.addResourceBundle('en', 'translation', {
      'common.releaseWorkflowBacklinkStep': 'Release workflow step {{step}}',
      'common.releaseWorkflowBacklinkStepShort': 'Step {{step}} workflow',
    }, true, true)

    const { container } = render(
      <MemoryRouter>
        <ReleaseWorkflowBacklink stepNumber={5} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'Release workflow step 5' }))
      .toHaveAttribute('href', RELEASE_WORKFLOW_ANCHOR_PATH)
    expect(screen.getByText('Step 5 workflow')).toBeInTheDocument()
    const step = container.querySelector('.release-workflow-backlink__step')
    expect(step).toHaveTextContent('5')
    expect(step).toHaveAttribute('aria-hidden', 'true')
  })

  it('resolves release step ids through the shared workflow registry', () => {
    i18n.addResourceBundle('en', 'translation', {
      'common.releaseWorkflowBacklinkStep': 'Release workflow step {{step}}',
      'common.releaseWorkflowBacklinkStepShort': 'Step {{step}} workflow',
    }, true, true)

    render(
      <MemoryRouter>
        <ReleaseWorkflowBacklink stepId="provider" />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'Release workflow step 7' }))
      .toHaveAttribute('href', RELEASE_WORKFLOW_ANCHOR_PATH)
    expect(screen.getByText('Step 7 workflow')).toBeInTheDocument()
  })

  it('links a primary release page to its previous and next workflow steps', () => {
    i18n.addResourceBundle('en', 'translation', {
      'common.releaseWorkflowBacklinkStep': 'Release workflow step {{step}}',
      'common.releaseWorkflowBacklinkStepShort': 'Step {{step}} workflow',
      'common.releaseWorkflowStepNavigation': 'Release step navigation',
      'common.releaseWorkflowPreviousStep': 'Previous release step {{step}}: {{title}}',
      'common.releaseWorkflowPreviousStepShort': 'Previous step {{step}}',
      'common.releaseWorkflowNextStep': 'Next release step {{step}}: {{title}}',
      'common.releaseWorkflowNextStepShort': 'Next step {{step}}',
      'dashboard.releaseWorkflow.ingest': 'Ingest documents',
      'dashboard.releaseWorkflow.feedback': 'Promote feedback',
    }, true, true)

    render(
      <MemoryRouter>
        <ReleaseWorkflowBacklink stepId="rag" showAdjacentSteps />
      </MemoryRouter>,
    )

    expect(screen.getByRole('navigation', { name: 'Release step navigation' }))
      .toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Previous release step 2: Ingest documents' }))
      .toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.ingest)
    expect(screen.getByRole('link', { name: 'Release workflow step 3' }))
      .toHaveAttribute('href', RELEASE_WORKFLOW_ANCHOR_PATH)
    expect(screen.getByRole('link', { name: 'Next release step 4: Promote feedback' }))
      .toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.feedback)
  })

  it('omits a next-step link at the end of the release workflow', () => {
    i18n.addResourceBundle('en', 'translation', {
      'common.releaseWorkflowBacklinkStep': 'Release workflow step {{step}}',
      'common.releaseWorkflowBacklinkStepShort': 'Step {{step}} workflow',
      'common.releaseWorkflowStepNavigation': 'Release step navigation',
      'common.releaseWorkflowPreviousStep': 'Previous release step {{step}}: {{title}}',
      'common.releaseWorkflowPreviousStepShort': 'Previous step {{step}}',
      'common.releaseWorkflowNextStep': 'Next release step {{step}}: {{title}}',
      'common.releaseWorkflowNextStepShort': 'Next step {{step}}',
      'dashboard.releaseWorkflow.integrations': 'Run live smoke',
    }, true, true)

    render(
      <MemoryRouter>
        <ReleaseWorkflowBacklink stepId="provider" showAdjacentSteps />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'Previous release step 6: Run live smoke' }))
      .toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.integrations)
    expect(screen.queryByRole('link', { name: /^Next release step/ })).not.toBeInTheDocument()
  })
})

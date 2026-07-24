import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, i18n, render, screen, waitFor, within } from '../../../test/utils'
import { SchedulerManager } from '../ui/SchedulerManager'
import * as schedulerApi from '../api'
import type { ScheduledJobExecutionResponse, ScheduledJobResponse } from '../types'

vi.mock('../api', () => ({
  listJobs: vi.fn(),
  getJob: vi.fn(),
  createJob: vi.fn(),
  updateJob: vi.fn(),
  deleteJob: vi.fn(),
  triggerJob: vi.fn(),
  dryRunJob: vi.fn(),
  getExecutions: vi.fn(),
}))

const listJobsMock = vi.mocked(schedulerApi.listJobs)
const getJobMock = vi.mocked(schedulerApi.getJob)
const createJobMock = vi.mocked(schedulerApi.createJob)
const updateJobMock = vi.mocked(schedulerApi.updateJob)
const getExecutionsMock = vi.mocked(schedulerApi.getExecutions)

function buildJob(overrides: Partial<ScheduledJobResponse> = {}): ScheduledJobResponse {
  return {
    id: 'job-1',
    name: 'Daily summary',
    description: null,
    cronExpression: '0 9 * * 1-5',
    timezone: 'Asia/Seoul',
    jobType: 'AGENT',
    mcpServerName: null,
    toolName: null,
    toolArguments: {},
    agentPrompt: 'Summarize incidents',
    personaId: null,
    agentSystemPrompt: null,
    agentModel: 'gpt-5',
    agentMaxToolCalls: 5,
    tags: ['operations'],
    slackChannelId: 'C123',
    teamsWebhookUrl: null,
    retryOnFailure: true,
    maxRetryCount: 2,
    executionTimeoutMs: 120000,
    enabled: true,
    lastRunAt: 1710000000000,
    lastStatus: 'SUCCESS',
    lastResult: 'ok',
    lastResultPreview: 'ok',
    lastFailureReason: null,
    createdAt: 1710000000000,
    updatedAt: 1710000000000,
    ...overrides,
  }
}

function buildExecution(overrides: Partial<ScheduledJobExecutionResponse> = {}): ScheduledJobExecutionResponse {
  return {
    id: 'exec-1',
    jobId: 'job-1',
    jobName: 'Daily summary',
    status: 'SUCCESS',
    result: 'done',
    resultPreview: 'done',
    failureReason: null,
    durationMs: 1200,
    dryRun: false,
    startedAt: 1710000000000,
    completedAt: 1710000001000,
    ...overrides,
  }
}

function renderManager(initialEntry = '/') {
  const router = createMemoryRouter(
    [{ path: '/', element: <SchedulerManager /> }],
    { initialEntries: [initialEntry] },
  )
  return { ...render(<RouterProvider router={router} />), router }
}

describe('SchedulerManager', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'nav.scheduler': 'Scheduled Jobs',
      'nav.help.scheduler': 'Create and manage scheduled automation jobs.',
      'scheduler.tabsLabel': 'Scheduled jobs workspace',
      'scheduler.tabs.jobs': 'Jobs',
      'scheduler.tabs.executions': 'Execution history',
      'common.name': 'Name',
      'common.description': 'Description',
      'common.status': 'Status',
      'common.statuses.SUCCESS': 'Succeeded',
      'common.statuses.FAILED': 'Failed',
      'common.statuses.RUNNING': 'Running',
      'common.statuses.PASS': 'Passed',
      'common.statuses.WARN': 'Needs review',
      'common.statuses.FAIL': 'Blocked',
      'common.refresh': 'Refresh',
      'common.cancel': 'Cancel',
      'common.save': 'Save',
      'common.delete': 'Delete',
      'common.edit': 'Edit',
      'common.yes': 'yes',
      'common.no': 'no',
      'common.releaseWorkflowBacklink': 'Release workflow',
      'common.releaseWorkflowBacklinkStep': 'Release workflow step {{step}}',
      'scheduler.bannerTitle': 'Scheduled Jobs',
      'scheduler.lastSync': 'Last successful sync: {{time}}',
      'scheduler.lastSyncUnknown': 'No successful scheduler snapshot loaded yet',
      'scheduler.revalidationTitle': 'Latest job list needs another check',
      'scheduler.revalidationDescription': 'Showing the last verified jobs until the connection recovers.',
      'scheduler.unavailableTitle': 'Scheduled jobs are unavailable',
      'scheduler.unavailableDescription': 'The values on this page cannot be verified until a successful response returns.',
      'scheduler.executionWorkspaceUnavailableTitle': 'Execution history is unavailable',
      'scheduler.executionWorkspaceUnavailableDescription': 'The job list could not be verified, so execution history cannot be selected safely.',
      'scheduler.retry': 'Try again',
      'scheduler.retrying': 'Checking',
      'scheduler.openHealth': 'Open platform status',
      'scheduler.recoveryGuideTitle': 'Resolve the connection problem',
      'scheduler.recoveryGuide.checkAccount': 'Check the current account and organization.',
      'scheduler.recoveryGuide.checkStatus': 'Review server and access status.',
      'scheduler.recoveryGuide.retry': 'Return and try again.',
      'scheduler.technicalError': 'Technical detail',
      'scheduler.opsTitle': 'Scheduler Readiness',
      'scheduler.opsDescription': 'Confirm that the scheduler contract is reachable, enabled jobs are still runnable, failed jobs are not piling up, and execution history is trustworthy before replaying automation.',
      'scheduler.checksSummary': 'Decision evidence',
      'scheduler.checksCount': '{{count}} checks',
      'scheduler.attentionCount': '{{count}} need action',
      'scheduler.totalJobsCard': 'Tracked Jobs',
      'scheduler.enabledJobsCard': 'Enabled Jobs',
      'scheduler.attentionJobsCard': 'Attention Jobs',
      'scheduler.failedJobsCard': 'Failed Jobs',
      'scheduler.filterTitle': 'Quick Filters',
      'scheduler.jobsTitle': 'Scheduled jobs',
      'scheduler.filterDescription': 'Focus the job table on the backlog that needs a real operator decision right now.',
      'scheduler.showingRows': 'Showing {{shown}} of {{total}} jobs in the current filter.',
      'scheduler.filterEmpty': 'No jobs match the active quick filter',
      'scheduler.filterEmptyDescription': 'Switch back to All Jobs or clear the current operator filter before assuming the scheduler backlog is empty.',
      'scheduler.quickFilters.all': 'All Jobs',
      'scheduler.quickFilters.attention': 'Needs Attention',
      'scheduler.quickFilters.failed': 'Failed',
      'scheduler.quickFilters.neverRun': 'Never Run',
      'scheduler.quickFilters.stuckRunning': 'Stuck Running',
      'scheduler.quickFilters.noRetry': 'No Retry',
      'scheduler.signals.schedulerContract': 'Scheduler Contract',
      'scheduler.signals.enabledCoverage': 'Enabled Coverage',
      'scheduler.signals.failureBacklog': 'Failure Backlog',
      'scheduler.signals.historyCoverage': 'History Coverage',
      'scheduler.signalDetails.contractHealthy': 'The scheduler contract is responding and can be used for live operator actions.',
      'scheduler.signalDetails.contractMissing': 'The backend is not exposing `/api/scheduler/jobs` in this environment. Confirm feature wiring before relying on this console.',
      'scheduler.signalDetails.contractDenied': 'The scheduler endpoint is reachable, but this operator is not authorized. Review admin credentials and proxy auth settings.',
      'scheduler.signalDetails.contractTransport': 'The scheduler endpoint failed before a response returned. Inspect proxy or backend transport before replaying jobs.',
      'scheduler.signalDetails.contractError': 'The scheduler endpoint returned an unexpected HTTP error. Treat automation state as degraded until the contract recovers.',
      'scheduler.signalDetails.enabledCoverageReady': '{{count}} of {{total}} loaded job(s) are enabled for runtime execution.',
      'scheduler.signalDetails.enabledCoverageMissing': 'No enabled jobs are currently available. Confirm whether the scheduler is intentionally paused.',
      'scheduler.signalDetails.failureBacklogClear': 'No enabled jobs are currently reporting a failed last run.',
      'scheduler.signalDetails.failureBacklogPresent': '{{count}} enabled job(s) are reporting failed last runs. Review them before replaying automation.',
      'scheduler.signalDetails.historyCoverageReady': 'Execution history is available for all enabled jobs in the current snapshot.',
      'scheduler.signalDetails.historyCoverageMissing': 'Only {{count}} of {{total}} enabled job(s) have recent execution history. Verify stale or never-run jobs before assuming they are safe.',
      'scheduler.attentionTitle': 'Attention Queue',
      'scheduler.attentionDescription': 'Open job detail only after you understand whether the issue is a failed run, a never-executed job, or a stuck runtime.',
      'scheduler.attentionEmpty': 'No scheduler jobs currently need operator follow-up.',
      'scheduler.attentionHealthy': 'All tracked jobs are responding like a stable automation fleet.',
      'scheduler.attentionDetails.lastRunFailed': 'The latest execution failed. Confirm whether upstream systems recovered before triggering another run.',
      'scheduler.attentionDetails.lastRunFailedNoRetry': 'The latest execution failed and retry-on-failure is disabled. This job now needs manual recovery.',
      'scheduler.attentionDetails.neverExecuted': 'This enabled job has not produced an execution yet. Confirm cron, worker connectivity, and deployment timing.',
      'scheduler.attentionDetails.runningTooLong': 'This job still looks RUNNING long after its last start time. Treat it as a stuck execution until the worker state is verified.',
      'scheduler.openJobDetail': 'Open Job Detail',
      'scheduler.operatorNoteTitle': 'Operator Note',
      'scheduler.executionUnavailablePlain': 'Execution history is unavailable. Check the connection and try again.',
      'scheduler.executionSnapshotWarningPlain': 'The latest execution history could not be refreshed. Showing the last confirmed records.',
      'scheduler.executionConnectionDetail': 'Execution connection detail',
      'scheduler.create': 'New Job',
      'scheduler.jobType': 'Job Type',
      'scheduler.jobTypes.AGENT': 'Agent',
      'scheduler.jobTypes.MCP_TOOL': 'MCP tool',
      'scheduler.jobTypes.PROMPT_LAB_AUTO_OPTIMIZE': 'Prompt auto optimization',
      'scheduler.tags': 'Tags',
      'scheduler.tagsPlaceholder': 'Separate tags with commas',
      'scheduler.cron': 'Cron Expression',
      'scheduler.scheduleLabel': 'Schedule',
      'scheduler.scheduleHelp': 'A repeating schedule rule.',
      'scheduler.schedule.weekdaysAt': 'Weekdays at {{time}}',
      'scheduler.schedule.dailyAt': 'Every day at {{time}}',
      'scheduler.schedule.weeklyAt': 'Every {{weekday}} at {{time}}',
      'scheduler.schedule.everyHours': 'Every {{count}} hours',
      'scheduler.schedule.custom': 'Custom schedule',
      'scheduler.weekdays.1': 'Monday',
      'scheduler.jobState.enabled': 'Running automatically',
      'scheduler.jobState.paused': 'Paused',
      'scheduler.noExecutionYet': 'Not run yet',
      'scheduler.timezone': 'Timezone',
      'scheduler.timezoneHelp': 'Set the operating region for scheduled jobs.',
      'scheduler.agentPrompt': 'Agent Prompt',
      'scheduler.agentSystemPrompt': 'Agent System Prompt',
      'scheduler.personaId': 'Persona ID',
      'scheduler.mcpServer': 'MCP Server',
      'scheduler.toolName': 'Tool Name',
      'scheduler.toolArguments': 'Tool Arguments',
      'scheduler.slackChannel': 'Slack Channel ID',
      'scheduler.teamsWebhook': 'Teams Webhook URL',
      'scheduler.enabled': 'Enabled',
      'scheduler.retryOnFailure': 'Retry on failure',
      'scheduler.maxRetryCount': 'Max Retry Count',
      'scheduler.executionTimeoutMs': 'Execution Timeout (ms)',
      'scheduler.maximumExecutionTime': 'Maximum execution time',
      'scheduler.maximumExecutionTimeHelp': 'How long a job may run before it is stopped.',
      'scheduler.trigger': 'Run Now',
      'scheduler.dryRun': 'Dry Run',
      'scheduler.runType': 'Run type',
      'scheduler.liveRun': 'Live run',
      'scheduler.result': 'Result',
      'scheduler.executionResult': 'Execution result',
      'scheduler.lastRun': 'Last Run',
      'scheduler.executions': 'Execution History',
      'scheduler.noExecutions': 'No executions yet',
      'scheduler.duration': 'Duration',
      'scheduler.startedAt': 'Started At',
      'scheduler.completedAt': 'Completed At',
      'scheduler.toolInfo': 'Tool',
      'scheduler.latestRunSummary': 'Latest Run',
      'scheduler.executionDetail': 'Execution Detail',
      'scheduler.failureReason': 'Failure Reason',
      'scheduler.technicalJob': 'Job details',
      'scheduler.technicalExecution': 'Execution details',
      'scheduler.jobId': 'Job identifier',
      'scheduler.executionId': 'Execution identifier',
      'scheduler.executionOutcomes.success': 'Completed',
      'scheduler.executionOutcomes.failed': 'Needs failure review',
      'scheduler.executionOutcomes.running': 'In progress',
      'scheduler.executionOutcomes.skipped': 'Not run',
      'scheduler.executionOutcomes.review': 'Needs result review',
      'scheduler.agentConfigTitle': 'Agent Runtime Config',
      'scheduler.nameRequired': 'Job name is required',
      'scheduler.cronRequired': 'Cron expression is required',
      'scheduler.formReadinessTitle': 'Save Readiness',
      'scheduler.formReadinessDescription': 'Review the execution target, payload, retry policy, timeout, and delivery settings before changing a production job.',
      'scheduler.formBlocked': 'Review required fields',
      'scheduler.formReady': 'Ready to save',
      'scheduler.formWarnings': '{{count}} optional settings',
      'scheduler.advancedSettings': 'Additional runtime settings',
      'scheduler.advancedSettingsDescription': 'Set role, model, system instructions, and tool limits only when needed.',
      'scheduler.deliverySettings': 'Failure handling and notifications',
      'scheduler.deliverySettingsDescription': 'Configure retries, time limits, tags, and notification channels.',
      'scheduler.formSignals.jobTarget': 'Execution Target',
      'scheduler.formSignals.toolArguments': 'Payload Shape',
      'scheduler.formSignals.agentRuntime': 'Agent Runtime',
      'scheduler.formSignals.retryPolicy': 'Retry Policy',
      'scheduler.formSignals.executionTimeout': 'Execution Timeout',
      'scheduler.formSignals.delivery': 'Notifications',
      'scheduler.formSignalDetails.agentTargetReady': 'Agent mode has a prompt and can run with the current job definition.',
      'scheduler.formSignalDetails.agentPromptMissing': 'Agent jobs require a non-empty prompt before they can be saved safely.',
      'scheduler.formSignalDetails.toolTargetReady': 'The MCP server and tool target are both configured for this job.',
      'scheduler.formSignalDetails.toolServerMissing': 'MCP tool jobs need a server name before the job can be saved safely.',
      'scheduler.formSignalDetails.toolNameMissing': 'MCP tool jobs need a tool name before the job can be saved safely.',
      'scheduler.formSignalDetails.toolArgumentsReady': 'Tool arguments parse as a JSON object and are ready to send to the backend.',
      'scheduler.formSignalDetails.toolArgumentsInvalidJson': 'Tool arguments do not parse as valid JSON. Fix the payload before saving.',
      'scheduler.formSignalDetails.toolArgumentsObjectRequired': 'Tool arguments must be a JSON object, not an array or primitive value.',
      'scheduler.formSignalDetails.toolArgumentsOptional': 'Tool arguments are only evaluated for MCP tool jobs.',
      'scheduler.formSignalDetails.agentRuntimeReady': 'Agent runtime overrides are configured and within a sane range.',
      'scheduler.formSignalDetails.agentRuntimeDefault': 'Agent runtime overrides are blank, so the backend defaults will be used.',
      'scheduler.formSignalDetails.agentRuntimeInvalid': 'Agent max tool calls must be a positive integer when provided.',
      'scheduler.formSignalDetails.agentRuntimeOptional': 'Agent runtime overrides are only relevant for AGENT jobs.',
      'scheduler.formSignalDetails.retryPolicyReady': 'Retry-on-failure is enabled with a valid retry count.',
      'scheduler.formSignalDetails.retryPolicyDisabled': 'Retry-on-failure is disabled. Failed jobs will need manual operator follow-up.',
      'scheduler.formSignalDetails.retryPolicyInvalid': 'Retry count must be zero or greater, and at least 1 when retry-on-failure is enabled.',
      'scheduler.formSignalDetails.executionTimeoutReady': 'A per-job execution timeout is configured for this job.',
      'scheduler.formSignalDetails.executionTimeoutDefault': 'No per-job timeout is set. The scheduler will fall back to the backend default.',
      'scheduler.formSignalDetails.executionTimeoutInvalid': 'Execution timeout must be a positive integer in milliseconds.',
      'scheduler.formSignalDetails.deliveryConfigured': 'Slack or Teams delivery is configured for this job.',
      'scheduler.formSignalDetails.deliveryMissing': 'No delivery channel is configured. Results will only be visible in the admin console and logs.',
      'scheduler.validation.nameRequired': 'Job name is required',
      'scheduler.validation.nameTooLong': 'Job name must be 200 characters or fewer',
      'scheduler.validation.cronRequired': 'Cron expression is required',
      'scheduler.validation.agentPromptRequired': 'Agent jobs require a prompt',
      'scheduler.validation.mcpServerRequired': 'MCP tool jobs require an MCP server name',
      'scheduler.validation.toolNameRequired': 'MCP tool jobs require a tool name',
      'scheduler.validation.toolArgumentsInvalidJson': 'Tool arguments must be valid JSON',
      'scheduler.validation.toolArgumentsObjectRequired': 'Tool arguments must be a JSON object',
      'scheduler.validation.agentMaxToolCallsInvalid': 'Max tool calls must be a positive integer',
      'scheduler.validation.maxRetryCountInvalid': 'Retry count must be zero or greater, and at least 1 when retry-on-failure is enabled',
      'scheduler.validation.executionTimeoutInvalid': 'Execution timeout must be a positive integer',
      'scheduler.empty': 'No scheduled jobs',
      'scheduler.selectJob': 'Select a job to view details',
      'scheduler.deleteTitle': 'Delete Scheduled Job',
      'scheduler.deleteConfirm': 'Delete job "{{name}}"?',
    }, true, true)

    listJobsMock.mockResolvedValue([buildJob()])
    getJobMock.mockResolvedValue(buildJob())
    createJobMock.mockResolvedValue(buildJob())
    updateJobMock.mockResolvedValue(buildJob())
    getExecutionsMock.mockResolvedValue([buildExecution()])
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('keeps the execution workspace addressable in the URL', async () => {
    const { router } = renderManager()

    await waitFor(() => expect(screen.getByRole('tab', { name: 'Jobs' })).toBeVisible())
    fireEvent.click(screen.getByRole('tab', { name: 'Execution history' }))

    expect(router.state.location.search).toBe('?tab=executions')
    expect(screen.getByRole('tab', { name: 'Execution history' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('scheduler.selectJobForHistory')).toBeVisible()
  })

  it('does not render inactive filters when the backend has no jobs', async () => {
    listJobsMock.mockResolvedValue([])

    renderManager()

    expect(await screen.findByText('No scheduled jobs')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'All Jobs' })).not.toBeInTheDocument()
    expect(screen.queryByText('Showing 0 of 0 jobs in the current filter.')).not.toBeInTheDocument()
  })

  it('shows readable schedules and localized states instead of backend enums', async () => {
    renderManager()

    expect(await screen.findByText('Weekdays at 09:00')).toBeVisible()
    expect(screen.getByText('Running automatically')).toBeVisible()
    expect(screen.getByText('Succeeded')).toBeVisible()
    expect(screen.queryByText('0 9 * * 1-5')).not.toBeInTheDocument()
    expect(screen.queryByText('SUCCESS')).not.toBeInTheDocument()
    expect(screen.queryByText('ENABLED')).not.toBeInTheDocument()
  })

  it('renders readiness, attention signals, and operator notes for failing jobs', async () => {
    listJobsMock.mockResolvedValue([
      buildJob({
        id: 'job-failed',
        name: 'Nightly sync',
        lastStatus: 'FAILED',
        lastFailureReason: 'queue offline',
        retryOnFailure: false,
      }),
      buildJob({
        id: 'job-fresh',
        name: 'Fresh job',
        lastRunAt: null,
        lastStatus: null,
      }),
    ])
    getExecutionsMock.mockResolvedValue([
      buildExecution({
        jobId: 'job-failed',
        jobName: 'Nightly sync',
        status: 'FAILED',
        failureReason: 'queue offline',
      }),
    ])

    const view = renderManager()

    await waitFor(() => {
      expect(screen.getByText('Scheduler Readiness')).toBeInTheDocument()
      expect(screen.getAllByText('Nightly sync').length).toBeGreaterThan(0)
    })

    expect(screen.queryByRole('link', { name: 'Release workflow' })).not.toBeInTheDocument()

    const leftPane = within(view.container.querySelector('.split-left') as HTMLElement)

    expect(screen.getByText('Attention Queue')).toBeInTheDocument()
    await waitFor(() => {
      expect(leftPane.getByText('Showing 2 of 2 jobs in the current filter.')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: 'No Retry' }))

    await waitFor(() => {
      expect(leftPane.getByText('Showing 1 of 2 jobs in the current filter.')).toBeInTheDocument()
    })

    expect(leftPane.getByText('Nightly sync')).toBeInTheDocument()
    expect(leftPane.queryByText('Fresh job')).not.toBeInTheDocument()
    expect(screen.queryByText('queue offline')).not.toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: 'Open Job Detail' })[0])

    await waitFor(() => {
      expect(screen.getByText('Operator Note')).toBeInTheDocument()
    })

    expect(screen.getAllByText(/manual recovery/).length).toBeGreaterThan(0)
    expect(screen.getByText('Execution Detail')).toBeInTheDocument()
  })

  it('fails closed with one recovery surface when the scheduler contract fails on first load', async () => {
    listJobsMock.mockRejectedValueOnce(new Error('HTTP 404'))

    renderManager()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Scheduled jobs are unavailable')
    })

    expect(screen.queryByText('Scheduler Readiness')).not.toBeInTheDocument()
    expect(screen.queryByText('Attention Queue')).not.toBeInTheDocument()
    expect(screen.queryByText('Troubleshooting Guide')).not.toBeInTheDocument()
    expect(screen.queryByText('No scheduled jobs')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open platform status' })).toHaveAttribute('href', '/health')
    expect(screen.getByText('Resolve the connection problem').closest('details')).not.toHaveAttribute('open')
    expect(screen.getAllByRole('button', { name: 'Try again' })).toHaveLength(1)
  })

  it('keeps the last successful snapshot visible when refresh fails later', async () => {
    listJobsMock
      .mockResolvedValueOnce([buildJob({ name: 'Daily summary' })])
      .mockRejectedValueOnce(new Error('socket hang up'))

    renderManager()

    await waitFor(() => {
      expect(screen.getByText('Daily summary')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))

    await waitFor(() => {
      expect(screen.getByText('Latest job list needs another check')).toBeInTheDocument()
    })

    expect(screen.getByText('Daily summary')).toBeInTheDocument()
    expect(document.querySelector('.alert-warning')).not.toBeInTheDocument()
  })

  it('fails closed in execution history when the scheduler job list cannot load', async () => {
    listJobsMock.mockRejectedValue(new Error('HTTP 503'))

    renderManager('/?tab=executions')

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Execution history is unavailable')
    })

    expect(screen.queryByLabelText('Select a job to view history')).not.toBeInTheDocument()
    expect(screen.queryByText('Select a job to view execution history')).not.toBeInTheDocument()
    expect(screen.getByText('Resolve the connection problem').closest('details')).not.toHaveAttribute('open')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(listJobsMock).toHaveBeenCalledTimes(2))
  })

  it('moves a selected job detail into view on narrow screens', async () => {
    const matchMediaDescriptor = Object.getOwnPropertyDescriptor(window, 'matchMedia')
    const scrollIntoViewDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollIntoView')
    const scrollIntoView = vi.fn()

    renderManager()
    await waitFor(() => expect(screen.getByText('Daily summary')).toBeInTheDocument())

    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockReturnValue({ matches: true }),
    })
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    })

    try {
      fireEvent.click(screen.getByText('Daily summary'))
      await waitFor(() => {
        expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
      })
    } finally {
      if (matchMediaDescriptor) Object.defineProperty(window, 'matchMedia', matchMediaDescriptor)
      else delete (window as { matchMedia?: Window['matchMedia'] }).matchMedia

      if (scrollIntoViewDescriptor) Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', scrollIntoViewDescriptor)
      else delete (HTMLElement.prototype as { scrollIntoView?: () => void }).scrollIntoView
    }
  })

  it('hydrates hidden config fields and blocks invalid tool-argument payloads while editing', async () => {
    const toolJob = buildJob({
      id: 'job-mcp',
      name: 'Tool sync',
      jobType: 'MCP_TOOL',
      mcpServerName: 'atlassian',
      toolName: 'jira_search',
      toolArguments: { projectKey: 'OPS' },
      executionTimeoutMs: 60000,
      retryOnFailure: true,
      maxRetryCount: 4,
      agentPrompt: null,
      agentModel: null,
      agentMaxToolCalls: null,
    })

    listJobsMock.mockResolvedValue([toolJob])
    getJobMock.mockResolvedValue(toolJob)

    renderManager()

    await waitFor(() => {
      expect(screen.getByText('Tool sync')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Tool sync'))
    await waitFor(() => {
      expect(screen.getByText('Job details')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))

    await waitFor(() => {
      expect(screen.getByDisplayValue('atlassian')).toBeInTheDocument()
    })

    expect(screen.getByDisplayValue('jira_search')).toBeInTheDocument()
    expect(screen.getByDisplayValue('60000')).toBeInTheDocument()
    expect(screen.getByDisplayValue('4')).toBeInTheDocument()
    expect(screen.getByText('Save Readiness')).toBeInTheDocument()

    // The form is rendered inside a SideDrawer portal mounted on document.body.
    const toolArgumentsField = document.getElementById('scheduler-tool-args') as HTMLTextAreaElement
    expect(toolArgumentsField.value).toContain('"projectKey": "OPS"')

    fireEvent.change(toolArgumentsField, { target: { value: '[]' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(screen.getByText('Tool arguments must be a JSON object')).toBeInTheDocument()
    })

    expect(updateJobMock).not.toHaveBeenCalled()
  })

  it('keeps raw scheduler configuration and execution payloads in closed developer disclosures', async () => {
    renderManager()

    await waitFor(() => {
      expect(screen.getByText('Daily summary')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Daily summary'))

    await screen.findByText('Job details')
    const jobDetail = document.querySelector('.scheduler-job-detail')

    expect(jobDetail).not.toBeNull()
    const scopedJobDetail = jobDetail as HTMLElement
    const jobTechnical = within(scopedJobDetail).getByText('Job details').closest('details')
    const executionTechnical = scopedJobDetail.querySelector('.scheduler-execution-detail__technical')
    expect(jobTechnical).not.toHaveAttribute('open')
    expect(within(jobTechnical as HTMLElement).getByText('Summarize incidents')).toBeInTheDocument()
    expect(within(jobTechnical as HTMLElement).getByText('gpt-5')).toBeInTheDocument()
    expect(executionTechnical).not.toHaveAttribute('open')
    expect(within(executionTechnical as HTMLElement).getByText('done')).toBeInTheDocument()
  })
})

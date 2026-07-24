import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { fireEvent, i18n, render, screen, waitFor } from '../../../test/utils'
import { MetricIngestionManager } from '../ui/MetricIngestionManager'
import * as metricApi from '../api'
import { ApiError } from '../../../shared/api/errors'

vi.mock('../api', () => ({
  ingestMcpHealth: vi.fn(),
  ingestToolCall: vi.fn(),
  ingestEvalResult: vi.fn(),
  ingestEvalResults: vi.fn(),
  ingestMcpHealthBatch: vi.fn(),
}))

const ingestMcpHealthMock = vi.mocked(metricApi.ingestMcpHealth)

function renderManager() {
  const router = createMemoryRouter(
    [{ path: '/', element: <MetricIngestionManager /> }],
    { initialEntries: ['/'] },
  )
  return { ...render(<RouterProvider router={router} />), router }
}

describe('MetricIngestionManager', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'metricsIngestionPage.title': 'Send diagnostic data',
      'metricsIngestionPage.description': 'Send sample records to verify ingestion.',
      'metricsIngestionPage.warningTitle': 'Use sample data only',
      'metricsIngestionPage.warning': 'This writes directly to operational data.',
      'metricsIngestionPage.inputType': 'Record to verify',
      'metricsIngestionPage.scenarioTitle': 'Diagnostic data to send',
      'metricsIngestionPage.chooseDescription': 'Choose the diagnostic record type.',
      'metricsIngestionPage.payload': 'Source data to send (JSON)',
      'metricsIngestionPage.payloadReady': '{{count}} record ready to send.',
      'metricsIngestionPage.invalidJson': 'Enter valid JSON.',
      'metricsIngestionPage.jsonObjectRequired': 'Enter a JSON object.',
      'metricsIngestionPage.jsonArrayRequired': 'Enter a JSON array.',
      'metricsIngestionPage.confirmSample': 'I confirm this is sample data.',
      'metricsIngestionPage.resetSample': 'Restore sample',
      'metricsIngestionPage.submit': 'Send diagnostic data',
      'metricsIngestionPage.submitDescription': 'The record is written immediately.',
      'metricsIngestionPage.technicalDetails': 'Developer delivery information',
      'metricsIngestionPage.targetEndpoint': 'Delivery endpoint',
      'metricsIngestionPage.permission': 'Required permission',
      'metricsIngestionPage.permissionNotice': 'Operational write access is required.',
      'metricsIngestionPage.lastResponse': 'Delivery result',
      'metricsIngestionPage.failedResponse': 'Delivery failed',
      'metricsIngestionPage.submitUnavailable': 'Unable to send diagnostic data. Check the connection and try again.',
      'metricsIngestionPage.successDescription': 'The diagnostic record was written.',
      'metricsIngestionPage.rawResponse': 'View raw response',
      'metricsIngestionPage.technicalError': 'Technical detail',
      'metricsIngestionPage.resultFields.success': 'Result',
      'metricsIngestionPage.resultFields.ingested': 'Records written',
      'metricsIngestionPage.tabs.mcpHealth': 'External tool connection',
      'metricsIngestionPage.tabs.toolCall': 'Tool execution record',
      'metricsIngestionPage.tabs.evalResult': 'One quality result',
      'metricsIngestionPage.tabs.evalResults': 'Multiple quality results',
      'metricsIngestionPage.tabs.batch': 'Multiple connections',
      'metricsIngestionPage.typeDescriptions.mcpHealth': 'Record connection status.',
      'metricsIngestionPage.typeDescriptions.toolCall': 'Record a tool execution.',
      'metricsIngestionPage.typeDescriptions.evalResult': 'Record one quality result.',
      'metricsIngestionPage.typeDescriptions.evalResults': 'Record multiple quality results.',
      'metricsIngestionPage.typeDescriptions.batch': 'Record multiple connection states.',
      'metricsIngestionPage.help.inputTypeTitle': 'Diagnostic record type',
      'metricsIngestionPage.help.inputType': 'Choose which record to verify.',
      'metricsIngestionPage.help.jsonTitle': 'Source JSON',
      'metricsIngestionPage.help.json': 'Structured source data.',
      'common.retry': 'Retry',
    }, true, true)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders one input workflow without duplicate release navigation', () => {
    renderManager()
    expect(screen.getByRole('heading', { level: 1, name: 'Send diagnostic data' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Record to verify')).toHaveValue('mcpHealth')
    expect(screen.getByLabelText('Source data to send (JSON)')).toBeVisible()
    expect(screen.queryByText('Delivery result')).not.toBeInTheDocument()
  })

  it('shows warning alert and MCP Health section by default', () => {
    renderManager()
    expect(screen.getByText('This writes directly to operational data.')).toBeInTheDocument()
    expect(screen.getByText('/api/admin/metrics/ingest/mcp-health').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByRole('button', { name: 'Send diagnostic data' })).toBeDisabled()
  })

  it('requires a fresh sample-data confirmation after the payload changes', () => {
    renderManager()
    const submit = screen.getByRole('button', { name: 'Send diagnostic data' })
    const confirmation = screen.getByRole('checkbox', { name: 'I confirm this is sample data.' })

    fireEvent.click(confirmation)
    expect(submit).toBeEnabled()

    const payload = screen.getByLabelText('Source data to send (JSON)')
    fireEvent.change(payload, { target: { value: payload.getAttribute('value') ?? '{ "tenantId": "default" }' } })

    expect(confirmation).not.toBeChecked()
    expect(submit).toBeDisabled()
  })

  it('switches to tool call tab when clicked', () => {
    const { router } = renderManager()
    fireEvent.change(screen.getByLabelText('Record to verify'), { target: { value: 'toolCall' } })
    expect(screen.getByText('/api/admin/metrics/ingest/tool-call')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send diagnostic data' })).toBeDisabled()
    expect(router.state.location.search).toBe('?type=toolCall')
  })

  it('switches to batch tab when clicked', () => {
    renderManager()
    fireEvent.change(screen.getByLabelText('Record to verify'), { target: { value: 'batch' } })
    expect(screen.getByText('/api/admin/metrics/ingest/batch')).toBeInTheDocument()
  })

  it('shows response after successful MCP health ingestion', async () => {
    ingestMcpHealthMock.mockResolvedValueOnce({ success: true, ingested: 1 })
    renderManager()
    fireEvent.click(screen.getByRole('checkbox', { name: 'I confirm this is sample data.' }))
    fireEvent.click(screen.getByRole('button', { name: 'Send diagnostic data' }))
    await waitFor(() => {
      expect(screen.getByText(/"success": true/)).toBeInTheDocument()
    })
    expect(screen.getByText('The diagnostic record was written.')).toBeInTheDocument()
    expect(screen.getByText('Records written')).toBeInTheDocument()
    expect(screen.getByText(/"success": true/).closest('details')).not.toHaveAttribute('open')
    expect(ingestMcpHealthMock).toHaveBeenCalledTimes(1)
  })

  it('describes an authorization failure as a permission problem', async () => {
    ingestMcpHealthMock.mockRejectedValueOnce(new ApiError(403, 'FORBIDDEN', 'admin access required'))
    renderManager()
    fireEvent.click(screen.getByRole('checkbox', { name: 'I confirm this is sample data.' }))
    fireEvent.click(screen.getByRole('button', { name: 'Send diagnostic data' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('권한')
    expect(alert).not.toHaveTextContent('서버 오류')
  })

  it('shows error alert on ingestion failure', async () => {
    ingestMcpHealthMock.mockRejectedValueOnce(new Error('Service unavailable'))
    renderManager()
    fireEvent.click(screen.getByRole('checkbox', { name: 'I confirm this is sample data.' }))
    fireEvent.click(screen.getByRole('button', { name: 'Send diagnostic data' }))
    await waitFor(() => {
      expect(screen.getByText('Unable to send diagnostic data. Check the connection and try again.')).toBeInTheDocument()
    })
    expect(screen.getByText('Service unavailable')).not.toBeVisible()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeEnabled()
    fireEvent.click(screen.getByText('Technical detail'))
    expect(screen.getByText('Service unavailable')).toBeVisible()
  })

  it('fails locally when a batch payload is not an array', async () => {
    renderManager()
    fireEvent.change(screen.getByLabelText('Record to verify'), { target: { value: 'batch' } })
    fireEvent.change(screen.getByLabelText('Source data to send (JSON)'), { target: { value: '{}' } })

    expect(await screen.findByRole('alert')).toHaveTextContent('Enter a JSON array.')
    expect(screen.getByRole('button', { name: 'Send diagnostic data' })).toBeDisabled()
    expect(metricApi.ingestMcpHealthBatch).not.toHaveBeenCalled()
  })
})

import type { ComponentProps } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { TFunction } from 'i18next'
import { render, screen, within } from '../../../test/utils'
import { ControlPlaneProbesPanel, resolveProviderSmokeChecks } from '../ui/ControlPlaneProbesPanel'
import {
  RELEASE_A2A_PROTOCOL_PATH,
  RELEASE_SLACK_GATEWAY_PATH,
  RELEASE_WORKFLOW_PATHS_BY_ID,
} from '../../../shared/releaseWorkflow'
import type { ControlPlaneProbeSnapshot, ControlPlaneProbeSummary } from '../controlPlaneProbes'
import type { DashboardReleaseReadinessSummary } from '../../dashboard/types'

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    Link: ({ to, ...props }: ComponentProps<typeof actual.Link>) => (
      <a {...props} href={typeof to === 'string' ? to : String(to)} data-router-link="true" />
    ),
  }
})

const summary: ControlPlaneProbeSummary = {
  total: 4,
  passCount: 1,
  warnCount: 1,
  failCount: 1,
  declaredCount: 2,
}

function makeProbe(overrides: Partial<ControlPlaneProbeSnapshot> = {}): ControlPlaneProbeSnapshot {
  return {
    id: 'capabilities',
    path: '/api/admin/capabilities',
    status: 'PASS',
    reason: 'ready',
    manifestDeclared: true,
    httpStatus: 200,
    durationMs: 50,
    detail: 'OK',
    ...overrides,
  }
}

const readiness: DashboardReleaseReadinessSummary = {
  status: 'eligible_with_warnings',
  requiredReports: ['smoke_run', 'release_evidence', 'langsmith_eval_sync'],
  missingReports: [],
  slackGatewaySmoke: {
    status: 'verified',
    gateway: 'native_slack_gateway',
    workspaceId: 'T0REACTOR',
    workspaceName: 'Reactor Ops',
    channelId: 'C0123456789',
    botUserId: 'U0JARVIS',
    ingress: 'slash_command_or_socket_mode',
    currentThreadReplyRoute: 'native_gateway',
    signatureVerificationRequired: true,
    responseUrlRouteSupported: true,
    mcpWriteOverlapForbidden: true,
    authTestOk: true,
    feedbackActionRoute: 'slack_button_feedback_to_review_queue',
    evalPromotionRoute: 'feedback_review_to_langsmith_eval_sync',
    requiredChecks: ['required_env', 'signed_request', 'auth_test'],
  },
  a2aProtocol: {
    status: 'verified',
    agentCard: { name: 'Reactor', interfaceCount: 1, wellKnownPath: '/.well-known/agent-card.json' },
    diagnostics: { sdkAvailable: true, protocolVersion: '1.0', path: '/v1/a2a/diagnostics' },
    protocolNegotiation: {
      requestHeader: 'A2A-Version',
      requestedVersion: '1.0',
      responseVersion: '1.0',
      majorMinorOnly: true,
      agentCardVersionsChecked: true,
      serverGeneratedTaskIds: true,
      sdkFastApiSurface: true,
      telemetryInstrumentation: 'a2a-sdk[telemetry]',
    },
    taskApi: { status: 'passed', taskStatus: 'completed', path: '/v1/a2a/tasks' },
    operationalEvidence: {
      auditRecorded: true,
      idempotencyEnforced: true,
      telemetryEnabled: true,
      pushOutboxRouted: true,
    },
    secretFree: true,
    tlsRequired: true,
  },
  backendProviderIntegration: {
    status: 'verified',
    provider: 'ollama',
    model: 'gemma4:12b',
    requiredChecks: ['required_env', 'tracing_config', 'chat_model_invoke', 'usage_metadata'],
    usageMetadata: {
      source: 'LangChain AIMessage.usage_metadata',
      present: true,
      inputTokens: 20,
      outputTokens: 63,
      totalTokens: 83,
      totalMatchesBreakdown: true,
    },
  },
  feedbackReviewQueue: {
    status: 'passed',
    reviewStatus: 'done',
    candidateTag: 'rag-candidate:grounded_citation',
    caseIds: ['case-rag-weak-answer', 'case-slack-feedback-promoted'],
  },
  langsmithSync: {
    datasetName: 'reactor-release-regression',
    exampleCount: 2,
    caseCount: 2,
    exampleIds: ['example-1', 'example-2'],
    caseIds: ['case-rag-weak-answer'],
    metadataCaseIds: ['case-rag-weak-answer'],
    splitCounts: { regression: 2 },
    secretFree: true,
    sdkContract: 'Client.create_dataset/create_example',
  },
  gates: [
    { id: 'slack', status: 'passed' },
    { id: 'a2a', status: 'passed' },
    { id: 'provider', status: 'passed' },
  ],
  tagRecommendation: {
    releaseReadinessCommand: 'uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json',
  },
}

const blockedReadiness: DashboardReleaseReadinessSummary = {
  ...readiness,
  status: 'blocked',
  blockingReports: ['preflight', 'provider_smoke'],
  warningReports: ['slack_workspace_smoke'],
  missingEnvAnyOf: ['REACTOR_A2A_BASE_URL', 'REACTOR_A2A_API_KEY'],
  recommendedEnv: ['REACTOR_SLACK_BOT_TOKEN', 'REACTOR_SLACK_SIGNING_SECRET', 'OPENAI_API_KEY'],
  gates: [
    { id: 'slack', status: 'blocked' },
    { id: 'a2a', status: 'blocked' },
    { id: 'provider', status: 'warning' },
  ],
  items: [
    {
      name: 'slack_workspace_smoke',
      status: 'blocked',
      nextActions: [{
        id: 'fix-slack-workspace-smoke',
        label: 'Set Slack workspace credentials and rerun Slack smoke',
        releaseSmokeEnvFileCommand: 'uv run reactor-release-smoke-run --gate slack --env-file reports/release/release-smoke-preflight.local.env',
      }],
    },
    {
      name: 'a2a_peer_smoke',
      status: 'blocked',
      nextActions: [{
        id: 'fix-a2a-peer-smoke',
        label: 'Set A2A peer credentials and rerun A2A smoke',
        releaseSmokeEnvFileCommand: 'uv run reactor-release-smoke-run --gate a2a --env-file reports/release/release-smoke-preflight.local.env',
      }],
    },
    {
      name: 'provider_smoke',
      status: 'warning',
      nextActions: [{
        id: 'rerun-provider-smoke',
        label: 'Rerun provider smoke after local provider is available',
        command: 'uv run reactor-release-smoke-run --gate provider --readiness-output reports/release-readiness.json',
      }],
    },
  ],
}

function renderPanel(
  probes: ControlPlaneProbeSnapshot[],
  releaseReadiness: DashboardReleaseReadinessSummary | null = readiness,
  view: 'overview' | 'run' | 'evidence' = 'overview',
) {
  return render(
    <MemoryRouter>
      <ControlPlaneProbesPanel
        loading={false}
        error={null}
        probes={probes}
        summary={summary}
        releaseReadiness={releaseReadiness}
        view={view}
        onRefresh={async () => undefined}
        onRefreshReadiness={async () => undefined}
      />
    </MemoryRouter>,
  )
}

describe('ControlPlaneProbesPanel', () => {
  it('keeps the overview focused and the external test surface out of view', () => {
    const { container } = renderPanel([makeProbe()])

    expect(screen.getByText('integrationsPage.releaseSmoke.title')).toBeInTheDocument()
    expect(container.querySelector('.release-smoke-gates')).toBeNull()
    expect(container.querySelector('.external-smoke-operations')).toBeNull()
    expect(container.querySelector('.integrations-operations__evidence-list')).toBeNull()
  })

  it('renders evidence as three open operator rows rather than workflow or capability cards', () => {
    const { container } = renderPanel([
      makeProbe({ id: 'slackCommands' }),
      makeProbe({ id: 'slackEvents' }),
      makeProbe({ id: 'a2aDiagnostics' }),
      makeProbe({ id: 'providerModels' }),
    ], readiness, 'evidence')

    const gates = screen.getByLabelText('integrationsPage.releaseSmoke.gatesLabel')
    expect(within(gates).getAllByRole('article')).toHaveLength(3)
    expect(container.querySelector('.release-smoke-workflow')).toBeNull()
    expect(container.querySelector('.release-smoke-action-queue')).toBeNull()
    expect(container.querySelector('.product-capability-boundary-flow')).toBeNull()
    const gateLinks = within(gates).getAllByRole('link', {
      name: 'integrationsPage.releaseSmoke.openGate',
    })
    expect(gateLinks.map((link) => link.getAttribute('href'))).toEqual([
      RELEASE_SLACK_GATEWAY_PATH,
      RELEASE_A2A_PROTOCOL_PATH,
      RELEASE_WORKFLOW_PATHS_BY_ID.provider,
    ])
    expect(gates.querySelectorAll('.release-evidence-status')).toHaveLength(3)
    expect(container.querySelectorAll('.integration-evidence-detail')).toHaveLength(3)
    expect(container.querySelectorAll('.integration-evidence-detail .status-badge')).toHaveLength(0)
    expect(container.querySelectorAll('.integration-evidence-detail .release-evidence-status--pass')).toHaveLength(3)
    expect(container.querySelector('.release-smoke-evidence')).toBeNull()
  })

  it('keeps raw setup names and run commands inside closed technical disclosures', () => {
    const { container } = renderPanel([
      makeProbe({ id: 'slackCommands', status: 'FAIL' }),
      makeProbe({ id: 'slackEvents', status: 'FAIL' }),
      makeProbe({ id: 'a2aDiagnostics', status: 'FAIL' }),
      makeProbe({ id: 'providerModels', status: 'WARN' }),
    ], blockedReadiness, 'evidence')

    const gates = screen.getByLabelText('integrationsPage.releaseSmoke.gatesLabel')
    expect(within(gates).getAllByText('integrationsPage.releaseSmoke.nextAction')).toHaveLength(3)
    expect(within(gates).getByText('Set Slack workspace credentials and rerun Slack smoke')
      .closest('details')).not.toHaveAttribute('open')
    expect(container.querySelectorAll('.release-smoke-gate__technical:not([open])')).toHaveLength(3)
    expect(container.querySelector('.release-smoke-env__technical')).not.toHaveAttribute('open')
    expect(container.querySelector('.release-smoke-env__list code')).toBeNull()
  })

  it('does not request an OpenAI key when the live provider is local Ollama', () => {
    renderPanel([
      makeProbe({ id: 'providerModels', status: 'WARN' }),
    ], {
      ...blockedReadiness,
      backendProviderIntegration: readiness.backendProviderIntegration,
      recommendedEnv: ['OPENAI_API_KEY'],
      tagRecommendation: {
        ...blockedReadiness.tagRecommendation,
        missingEnv: ['OPENAI_API_KEY'],
      },
    }, 'evidence')

    const releaseSmoke = screen.getByRole('region', { name: 'integrationsPage.releaseSmoke.title' })
    expect(releaseSmoke).toHaveTextContent('integrationsPage.releaseSmoke.localProviderNoKey')
    expect(releaseSmoke).not.toHaveTextContent('OPENAI_API_KEY=')
  })

  it('maps provider smoke checks to translated labels without losing the failed check', () => {
    const t = ((key: string) => key) as TFunction
    const checks = resolveProviderSmokeChecks({
      status: 'verified',
      provider: 'ollama',
      model: 'gemma4:12b',
      requiredChecks: ['usage_metadata'],
      usageMetadata: {
        source: 'LangChain AIMessage.usage_metadata',
        present: true,
        inputTokens: 20,
        outputTokens: 63,
        totalTokens: 83,
        totalMatchesBreakdown: true,
      },
    }, t)

    expect(checks).toHaveLength(7)
    expect(checks.every((check) => check.ok)).toBe(true)
    expect(checks.map((check) => check.label)).toContain('integrationsPage.releaseSmoke.providerUsageTokens')
  })
})

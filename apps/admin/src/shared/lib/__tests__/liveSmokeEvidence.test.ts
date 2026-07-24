import { describe, expect, it } from 'vitest'
import {
  hasA2aSmokeEvidence,
  hasSlackSmokeEvidence,
  listA2aSmokeMissingCheckIds,
  listSlackSmokeMissingCheckIds,
  type A2aProtocolEvidence,
  type SlackGatewaySmokeEvidence,
} from '../liveSmokeEvidence'

const slackEvidence: SlackGatewaySmokeEvidence = {
  status: 'verified',
  gateway: 'native-slack-gateway',
  workspaceId: 'T0REACTOR',
  channelId: 'C0123456789',
  botUserId: 'U0JARVIS',
  ingress: 'socket-mode',
  currentThreadReplyRoute: 'chat.postMessage',
  signatureVerificationRequired: true,
  responseUrlRouteSupported: true,
  mcpWriteOverlapForbidden: true,
  authTestOk: true,
  feedbackActionRoute: 'slack_button_feedback_to_review_queue',
  evalPromotionRoute: 'feedback_review_to_langsmith_eval_sync',
}

const a2aEvidence: A2aProtocolEvidence = {
  status: 'verified',
  agentCard: {
    name: 'reactor-a2a-agent',
    interfaceCount: 1,
    wellKnownPath: '/.well-known/agent-card.json',
  },
  diagnostics: {
    sdkAvailable: true,
    path: '/v1/a2a/diagnostics',
  },
  protocolNegotiation: {
    requestHeader: 'A2A-Version',
    majorMinorOnly: true,
    sdkFastApiSurface: true,
    serverGeneratedTaskIds: true,
    telemetryInstrumentation: 'otel',
  },
  taskApi: {
    status: 'passed',
    taskStatus: 'completed',
    path: '/v1/a2a/tasks',
  },
  operationalEvidence: {
    auditRecorded: true,
    idempotencyEnforced: true,
    telemetryEnabled: true,
    pushOutboxRouted: true,
  },
  secretFree: true,
  tlsRequired: true,
}

describe('liveSmokeEvidence', () => {
  it('accepts complete Slack and A2A smoke evidence', () => {
    expect(hasSlackSmokeEvidence(slackEvidence)).toBe(true)
    expect(hasA2aSmokeEvidence(a2aEvidence)).toBe(true)
  })

  it('keeps verified Slack evidence blocked when action routes are missing', () => {
    const incomplete = {
      ...slackEvidence,
      feedbackActionRoute: '',
      evalPromotionRoute: '',
    }
    expect(hasSlackSmokeEvidence(incomplete)).toBe(false)
    expect(listSlackSmokeMissingCheckIds(incomplete)).toEqual(['feedback_action', 'eval_promotion'])
  })

  it('keeps verified A2A evidence blocked when operations are incomplete', () => {
    const incomplete = {
      ...a2aEvidence,
      operationalEvidence: {
        ...a2aEvidence.operationalEvidence!,
        pushOutboxRouted: false,
      },
      tlsRequired: false,
    }
    expect(hasA2aSmokeEvidence(incomplete)).toBe(false)
    expect(listA2aSmokeMissingCheckIds(incomplete)).toEqual(['operations', 'tls_required'])
  })
})

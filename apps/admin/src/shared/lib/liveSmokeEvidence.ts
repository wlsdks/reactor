export type SlackSmokeCheckId =
  | 'gateway'
  | 'workspace'
  | 'channel'
  | 'bot_user'
  | 'ingress'
  | 'reply_route'
  | 'signature'
  | 'response_url'
  | 'mcp_write_overlap'
  | 'auth_test'
  | 'feedback_action'
  | 'eval_promotion'

export type A2aSmokeCheckId =
  | 'agent'
  | 'agent_card_path'
  | 'interfaces'
  | 'sdk_available'
  | 'diagnostics_path'
  | 'negotiation'
  | 'sdk_fastapi_surface'
  | 'server_task_ids'
  | 'telemetry'
  | 'task_api'
  | 'task_path'
  | 'operations'
  | 'secret_free'
  | 'tls_required'

export interface SlackGatewaySmokeEvidence {
  status?: string | null
  gateway?: string | null
  workspaceId?: string | null
  workspaceName?: string | null
  channelId?: string | null
  botUserId?: string | null
  ingress?: string | null
  currentThreadReplyRoute?: string | null
  signatureVerificationRequired?: boolean | null
  responseUrlRouteSupported?: boolean | null
  mcpWriteOverlapForbidden?: boolean | null
  authTestOk?: boolean | null
  feedbackActionRoute?: string | null
  evalPromotionRoute?: string | null
}

export interface A2aProtocolEvidence {
  status?: string | null
  agentCard?: {
    name?: string | null
    interfaceCount?: number | null
    wellKnownPath?: string | null
  } | null
  diagnostics?: {
    sdkAvailable?: boolean | null
    path?: string | null
  } | null
  protocolNegotiation?: {
    requestHeader?: string | null
    majorMinorOnly?: boolean | null
    sdkFastApiSurface?: boolean | null
    serverGeneratedTaskIds?: boolean | null
    telemetryInstrumentation?: string | null
  } | null
  taskApi?: {
    status?: string | null
    taskStatus?: string | null
    path?: string | null
  } | null
  operationalEvidence?: {
    auditRecorded?: boolean | null
    idempotencyEnforced?: boolean | null
    telemetryEnabled?: boolean | null
    pushOutboxRouted?: boolean | null
  } | null
  secretFree?: boolean | null
  tlsRequired?: boolean | null
}

export function listSlackSmokeMissingCheckIds(
  evidence: SlackGatewaySmokeEvidence | null | undefined,
): SlackSmokeCheckId[] {
  const checks: Array<{ id: SlackSmokeCheckId; ok: boolean }> = [
    { id: 'gateway', ok: Boolean(evidence?.gateway) },
    { id: 'workspace', ok: Boolean(evidence?.workspaceId) || Boolean(evidence?.workspaceName) },
    { id: 'channel', ok: Boolean(evidence?.channelId) },
    { id: 'bot_user', ok: Boolean(evidence?.botUserId) },
    { id: 'ingress', ok: Boolean(evidence?.ingress) },
    { id: 'reply_route', ok: Boolean(evidence?.currentThreadReplyRoute) },
    { id: 'signature', ok: evidence?.signatureVerificationRequired === true },
    { id: 'response_url', ok: evidence?.responseUrlRouteSupported === true },
    { id: 'mcp_write_overlap', ok: evidence?.mcpWriteOverlapForbidden === true },
    { id: 'auth_test', ok: evidence?.authTestOk === true },
    { id: 'feedback_action', ok: Boolean(evidence?.feedbackActionRoute) },
    { id: 'eval_promotion', ok: Boolean(evidence?.evalPromotionRoute) },
  ]
  return checks.filter((check) => !check.ok).map((check) => check.id)
}

export function hasSlackSmokeEvidence(evidence: SlackGatewaySmokeEvidence | null | undefined): boolean {
  return evidence?.status === 'verified' && listSlackSmokeMissingCheckIds(evidence).length === 0
}

export function listA2aSmokeMissingCheckIds(
  evidence: A2aProtocolEvidence | null | undefined,
): A2aSmokeCheckId[] {
  const agentCard = evidence?.agentCard ?? null
  const diagnostics = evidence?.diagnostics ?? null
  const negotiation = evidence?.protocolNegotiation ?? null
  const taskApi = evidence?.taskApi ?? null
  const operations = evidence?.operationalEvidence ?? null
  const checks: Array<{ id: A2aSmokeCheckId; ok: boolean }> = [
    { id: 'agent', ok: Boolean(agentCard?.name) },
    { id: 'agent_card_path', ok: Boolean(agentCard?.wellKnownPath) },
    { id: 'interfaces', ok: (agentCard?.interfaceCount ?? 0) > 0 },
    { id: 'sdk_available', ok: diagnostics?.sdkAvailable === true },
    { id: 'diagnostics_path', ok: Boolean(diagnostics?.path) },
    { id: 'negotiation', ok: negotiation?.requestHeader === 'A2A-Version' && negotiation?.majorMinorOnly === true },
    { id: 'sdk_fastapi_surface', ok: negotiation?.sdkFastApiSurface === true },
    { id: 'server_task_ids', ok: negotiation?.serverGeneratedTaskIds === true },
    { id: 'telemetry', ok: Boolean(negotiation?.telemetryInstrumentation) },
    { id: 'task_api', ok: taskApi?.status === 'passed' && taskApi?.taskStatus === 'completed' },
    { id: 'task_path', ok: Boolean(taskApi?.path) },
    {
      id: 'operations',
      ok:
        operations?.auditRecorded === true
        && operations?.idempotencyEnforced === true
        && operations?.telemetryEnabled === true
        && operations?.pushOutboxRouted === true,
    },
    { id: 'secret_free', ok: evidence?.secretFree === true },
    { id: 'tls_required', ok: evidence?.tlsRequired === true },
  ]
  return checks.filter((check) => !check.ok).map((check) => check.id)
}

export function hasA2aSmokeEvidence(evidence: A2aProtocolEvidence | null | undefined): boolean {
  return evidence?.status === 'verified' && listA2aSmokeMissingCheckIds(evidence).length === 0
}

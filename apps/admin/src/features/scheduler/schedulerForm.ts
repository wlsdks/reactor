import type { CreateScheduledJobRequest, JobType, ScheduledJobResponse } from './types'

export interface SchedulerJobFormState {
  name: string
  description: string
  cronExpression: string
  timezone: string
  jobType: JobType
  mcpServerName: string
  toolName: string
  toolArgumentsRaw: string
  agentPrompt: string
  personaId: string
  agentSystemPrompt: string
  agentModel: string
  agentMaxToolCalls: string
  tagsRaw: string
  slackChannelId: string
  teamsWebhookUrl: string
  retryOnFailure: boolean
  maxRetryCount: string
  executionTimeoutMs: string
  enabled: boolean
}

export type SchedulerFormStatus = 'PASS' | 'WARN' | 'FAIL'

export interface SchedulerFormSignal {
  id: 'jobTarget' | 'toolArguments' | 'agentRuntime' | 'retryPolicy' | 'executionTimeout' | 'delivery'
  status: SchedulerFormStatus
  detailId:
    | 'agentTargetReady'
    | 'agentPromptMissing'
    | 'toolTargetReady'
    | 'toolServerMissing'
    | 'toolNameMissing'
    | 'promptTargetReady'
    | 'promptTemplateMissing'
    | 'toolArgumentsReady'
    | 'toolArgumentsInvalidJson'
    | 'toolArgumentsObjectRequired'
    | 'toolArgumentsOptional'
    | 'agentRuntimeReady'
    | 'agentRuntimeDefault'
    | 'agentRuntimeInvalid'
    | 'agentRuntimeOptional'
    | 'retryPolicyReady'
    | 'retryPolicyDisabled'
    | 'retryPolicyInvalid'
    | 'executionTimeoutReady'
    | 'executionTimeoutDefault'
    | 'executionTimeoutInvalid'
    | 'deliveryConfigured'
    | 'deliveryMissing'
}

export interface SchedulerFormReadinessSummary {
  status: SchedulerFormStatus
  passCount: number
  warnCount: number
  failCount: number
  signals: SchedulerFormSignal[]
}

export interface SchedulerJobFormValidationError {
  request?: never
  errorId:
    | 'nameRequired'
    | 'nameTooLong'
    | 'cronRequired'
    | 'agentPromptRequired'
    | 'mcpServerRequired'
    | 'toolNameRequired'
    | 'promptTemplateRequired'
    | 'toolArgumentsInvalidJson'
    | 'toolArgumentsObjectRequired'
    | 'agentMaxToolCallsInvalid'
    | 'maxRetryCountInvalid'
    | 'executionTimeoutInvalid'
}

export interface SchedulerJobFormValidationSuccess {
  errorId?: undefined
  request: CreateScheduledJobRequest
}

function normalizeText(value: string): string {
  return value.trim()
}

function optionalText(value: string): string | undefined {
  const trimmed = normalizeText(value)
  return trimmed ? trimmed : undefined
}

function parseInteger(value: string): number | null {
  const trimmed = normalizeText(value)
  if (!trimmed) return null
  if (!/^-?\d+$/.test(trimmed)) return null
  return Number(trimmed)
}

function parseToolArguments(raw: string): {
  ok: boolean
  value?: Record<string, unknown>
  errorId?: 'toolArgumentsInvalidJson' | 'toolArgumentsObjectRequired'
} {
  const trimmed = raw.trim()
  if (!trimmed) return { ok: true, value: {} }

  try {
    const parsed: unknown = JSON.parse(trimmed)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { ok: false, errorId: 'toolArgumentsObjectRequired' }
    }
    return { ok: true, value: parsed as Record<string, unknown> }
  } catch {
    return { ok: false, errorId: 'toolArgumentsInvalidJson' }
  }
}

function promptTemplateId(argumentsValue: Record<string, unknown> | undefined): string {
  const value = argumentsValue?.templateId
  return typeof value === 'string' ? value.trim() : ''
}

function summarizeStatus(signals: SchedulerFormSignal[]): Pick<SchedulerFormReadinessSummary, 'status' | 'passCount' | 'warnCount' | 'failCount'> {
  const passCount = signals.filter((signal) => signal.status === 'PASS').length
  const warnCount = signals.filter((signal) => signal.status === 'WARN').length
  const failCount = signals.filter((signal) => signal.status === 'FAIL').length

  return {
    status: failCount > 0 ? 'FAIL' : warnCount > 0 ? 'WARN' : 'PASS',
    passCount,
    warnCount,
    failCount,
  }
}

function summarizeJobTarget(form: SchedulerJobFormState): SchedulerFormSignal {
  if (form.jobType === 'AGENT') {
    return normalizeText(form.agentPrompt)
      ? { id: 'jobTarget', status: 'PASS', detailId: 'agentTargetReady' }
      : { id: 'jobTarget', status: 'FAIL', detailId: 'agentPromptMissing' }
  }

  if (form.jobType === 'PROMPT_LAB_AUTO_OPTIMIZE') {
    const parsed = parseToolArguments(form.toolArgumentsRaw)
    const templateId = parsed.ok ? promptTemplateId(parsed.value) : ''
    return templateId
      ? { id: 'jobTarget', status: 'PASS', detailId: 'promptTargetReady' }
      : { id: 'jobTarget', status: 'FAIL', detailId: 'promptTemplateMissing' }
  }

  if (!normalizeText(form.mcpServerName)) {
    return { id: 'jobTarget', status: 'FAIL', detailId: 'toolServerMissing' }
  }
  if (!normalizeText(form.toolName)) {
    return { id: 'jobTarget', status: 'FAIL', detailId: 'toolNameMissing' }
  }
  return { id: 'jobTarget', status: 'PASS', detailId: 'toolTargetReady' }
}

function summarizeToolArguments(form: SchedulerJobFormState): SchedulerFormSignal {
  if (form.jobType === 'AGENT') {
    return { id: 'toolArguments', status: 'WARN', detailId: 'toolArgumentsOptional' }
  }

  const parsed = parseToolArguments(form.toolArgumentsRaw)
  if (!parsed.ok) {
    return {
      id: 'toolArguments',
      status: 'FAIL',
      detailId: parsed.errorId === 'toolArgumentsInvalidJson' ? 'toolArgumentsInvalidJson' : 'toolArgumentsObjectRequired',
    }
  }

  return { id: 'toolArguments', status: 'PASS', detailId: 'toolArgumentsReady' }
}

function summarizeAgentRuntime(form: SchedulerJobFormState): SchedulerFormSignal {
  if (form.jobType !== 'AGENT') {
    return { id: 'agentRuntime', status: 'WARN', detailId: 'agentRuntimeOptional' }
  }

  if (normalizeText(form.agentMaxToolCalls) === '') {
    return { id: 'agentRuntime', status: 'WARN', detailId: 'agentRuntimeDefault' }
  }

  const parsed = parseInteger(form.agentMaxToolCalls)
  if (parsed == null || parsed < 1) {
    return { id: 'agentRuntime', status: 'FAIL', detailId: 'agentRuntimeInvalid' }
  }
  return { id: 'agentRuntime', status: 'PASS', detailId: 'agentRuntimeReady' }
}

function summarizeRetryPolicy(form: SchedulerJobFormState): SchedulerFormSignal {
  const parsed = parseInteger(form.maxRetryCount)
  if (parsed == null || parsed < 0 || (form.retryOnFailure && parsed < 1)) {
    return { id: 'retryPolicy', status: 'FAIL', detailId: 'retryPolicyInvalid' }
  }
  return form.retryOnFailure
    ? { id: 'retryPolicy', status: 'PASS', detailId: 'retryPolicyReady' }
    : { id: 'retryPolicy', status: 'WARN', detailId: 'retryPolicyDisabled' }
}

function summarizeExecutionTimeout(form: SchedulerJobFormState): SchedulerFormSignal {
  if (normalizeText(form.executionTimeoutMs) === '') {
    return { id: 'executionTimeout', status: 'WARN', detailId: 'executionTimeoutDefault' }
  }

  const parsed = parseInteger(form.executionTimeoutMs)
  if (parsed == null || parsed < 1) {
    return { id: 'executionTimeout', status: 'FAIL', detailId: 'executionTimeoutInvalid' }
  }
  return { id: 'executionTimeout', status: 'PASS', detailId: 'executionTimeoutReady' }
}

function summarizeDelivery(form: SchedulerJobFormState): SchedulerFormSignal {
  return normalizeText(form.slackChannelId) || normalizeText(form.teamsWebhookUrl)
    ? { id: 'delivery', status: 'PASS', detailId: 'deliveryConfigured' }
    : { id: 'delivery', status: 'WARN', detailId: 'deliveryMissing' }
}

export function createEmptySchedulerJobForm(): SchedulerJobFormState {
  return {
    name: '',
    description: '',
    cronExpression: '0 9 * * 1-5',
    timezone: 'Asia/Seoul',
    jobType: 'AGENT',
    mcpServerName: '',
    toolName: '',
    toolArgumentsRaw: '{}',
    agentPrompt: '',
    personaId: '',
    agentSystemPrompt: '',
    agentModel: '',
    agentMaxToolCalls: '',
    tagsRaw: '',
    slackChannelId: '',
    teamsWebhookUrl: '',
    retryOnFailure: false,
    maxRetryCount: '3',
    executionTimeoutMs: '',
    enabled: true,
  }
}

export function schedulerJobToForm(detail: ScheduledJobResponse): SchedulerJobFormState {
  return {
    name: detail.name,
    description: detail.description ?? '',
    cronExpression: detail.cronExpression,
    timezone: detail.timezone,
    jobType: detail.jobType,
    mcpServerName: detail.mcpServerName ?? '',
    toolName: detail.toolName ?? '',
    toolArgumentsRaw: JSON.stringify(detail.toolArguments ?? {}, null, 2),
    agentPrompt: detail.agentPrompt ?? '',
    personaId: detail.personaId ?? '',
    agentSystemPrompt: detail.agentSystemPrompt ?? '',
    agentModel: detail.agentModel ?? '',
    agentMaxToolCalls: detail.agentMaxToolCalls == null ? '' : String(detail.agentMaxToolCalls),
    tagsRaw: detail.tags.join(', '),
    slackChannelId: detail.slackChannelId ?? '',
    teamsWebhookUrl: detail.teamsWebhookUrl ?? '',
    retryOnFailure: detail.retryOnFailure,
    maxRetryCount: String(detail.maxRetryCount),
    executionTimeoutMs: detail.executionTimeoutMs == null ? '' : String(detail.executionTimeoutMs),
    enabled: detail.enabled,
  }
}

export function summarizeSchedulerFormReadiness(form: SchedulerJobFormState): SchedulerFormReadinessSummary {
  const signals: SchedulerFormSignal[] = [
    summarizeJobTarget(form),
    summarizeToolArguments(form),
    summarizeAgentRuntime(form),
    summarizeRetryPolicy(form),
    summarizeExecutionTimeout(form),
    summarizeDelivery(form),
  ]

  return {
    ...summarizeStatus(signals),
    signals,
  }
}

export function validateSchedulerJobForm(
  form: SchedulerJobFormState,
): SchedulerJobFormValidationSuccess | SchedulerJobFormValidationError {
  if (!normalizeText(form.name)) return { errorId: 'nameRequired' }
  if (normalizeText(form.name).length > 200) return { errorId: 'nameTooLong' }
  if (!normalizeText(form.cronExpression)) return { errorId: 'cronRequired' }

  const maxRetryCount = parseInteger(form.maxRetryCount)
  if (maxRetryCount == null || maxRetryCount < 0 || (form.retryOnFailure && maxRetryCount < 1)) {
    return { errorId: 'maxRetryCountInvalid' }
  }

  const executionTimeoutMs = parseInteger(form.executionTimeoutMs)
  if (normalizeText(form.executionTimeoutMs) && (executionTimeoutMs == null || executionTimeoutMs < 1)) {
    return { errorId: 'executionTimeoutInvalid' }
  }

  const agentMaxToolCalls = parseInteger(form.agentMaxToolCalls)
  if (normalizeText(form.agentMaxToolCalls) && (agentMaxToolCalls == null || agentMaxToolCalls < 1)) {
    return { errorId: 'agentMaxToolCallsInvalid' }
  }

  if (form.jobType === 'AGENT' && !normalizeText(form.agentPrompt)) {
    return { errorId: 'agentPromptRequired' }
  }
  if (form.jobType === 'MCP_TOOL' && !normalizeText(form.mcpServerName)) {
    return { errorId: 'mcpServerRequired' }
  }
  if (form.jobType === 'MCP_TOOL' && !normalizeText(form.toolName)) {
    return { errorId: 'toolNameRequired' }
  }

  const parsedToolArguments = parseToolArguments(form.toolArgumentsRaw)
  if (form.jobType !== 'AGENT' && !parsedToolArguments.ok) {
    return { errorId: parsedToolArguments.errorId ?? 'toolArgumentsInvalidJson' }
  }
  if (
    form.jobType === 'PROMPT_LAB_AUTO_OPTIMIZE'
    && !promptTemplateId(parsedToolArguments.value)
  ) {
    return { errorId: 'promptTemplateRequired' }
  }

  return {
    request: {
      name: normalizeText(form.name),
      description: optionalText(form.description),
      cronExpression: normalizeText(form.cronExpression),
      timezone: optionalText(form.timezone),
      jobType: form.jobType,
      mcpServerName: form.jobType === 'MCP_TOOL' ? optionalText(form.mcpServerName) : undefined,
      toolName: form.jobType === 'MCP_TOOL' ? optionalText(form.toolName) : undefined,
      toolArguments: form.jobType !== 'AGENT' ? parsedToolArguments.value ?? {} : undefined,
      agentPrompt: form.jobType === 'AGENT' ? optionalText(form.agentPrompt) : undefined,
      personaId: form.jobType === 'AGENT' ? optionalText(form.personaId) : undefined,
      agentSystemPrompt: form.jobType === 'AGENT' ? optionalText(form.agentSystemPrompt) : undefined,
      agentModel: form.jobType === 'AGENT' ? optionalText(form.agentModel) : undefined,
      agentMaxToolCalls: form.jobType === 'AGENT' ? agentMaxToolCalls ?? undefined : undefined,
      tags: form.tagsRaw.split(',').map(normalizeText).filter(Boolean),
      slackChannelId: optionalText(form.slackChannelId),
      teamsWebhookUrl: optionalText(form.teamsWebhookUrl),
      retryOnFailure: form.retryOnFailure,
      maxRetryCount,
      executionTimeoutMs: executionTimeoutMs ?? undefined,
      enabled: form.enabled,
    },
  }
}

import type { TFunction } from 'i18next'

export type SpanKind = 'request' | 'tool_call' | 'llm_call' | 'input_guard' | 'output_guard'

const SPAN_KIND_LABEL_KEYS: Record<SpanKind, string> = {
  request: 'tracesPage.spanKinds.request',
  tool_call: 'tracesPage.spanKinds.tool_call',
  llm_call: 'tracesPage.spanKinds.llm_call',
  input_guard: 'tracesPage.spanKinds.input_guard',
  output_guard: 'tracesPage.spanKinds.output_guard',
}

function normalizeCode(value: string | null | undefined): string {
  return value?.trim().toLowerCase().replace(/[\s_.-]+/g, '') ?? ''
}

export function deriveSpanKind(operationName: string): SpanKind {
  const normalized = normalizeCode(operationName)
  if (normalized.includes('toolcall') || normalized.startsWith('tool')) return 'tool_call'
  if (normalized.includes('llmcall') || normalized.startsWith('llm')) return 'llm_call'
  if (normalized.includes('inputguard') || normalized.includes('contentfilter')) return 'input_guard'
  if (normalized.includes('outputguard')) return 'output_guard'
  return 'request'
}

export function localizeSpanKind(t: TFunction, kind: SpanKind): string {
  return t(SPAN_KIND_LABEL_KEYS[kind])
}

function knownToolKey(value: string | null | undefined): string | null {
  const normalized = normalizeCode(value)
  if (normalized.includes('jirasearch')) return 'tracesPage.spanDetail.toolLabels.jira_search'
  if (normalized.includes('slack')) return 'tracesPage.spanDetail.toolLabels.slack'
  return null
}

function knownServerKey(value: string | null | undefined): string | null {
  const normalized = normalizeCode(value)
  if (normalized.includes('atlassian')) return 'tracesPage.spanDetail.serverLabels.atlassian'
  if (normalized.includes('slack')) return 'tracesPage.spanDetail.serverLabels.slack'
  return null
}

function knownModelKey(value: string | null | undefined): string | null {
  const normalized = normalizeCode(value)
  if (normalized.includes('claudesonnet')) return 'tracesPage.spanDetail.modelLabels.claude_sonnet'
  if (normalized.includes('claudehaiku')) return 'tracesPage.spanDetail.modelLabels.claude_haiku'
  if (normalized.includes('claudeopus')) return 'tracesPage.spanDetail.modelLabels.claude_opus'
  if (normalized.includes('gemma')) return 'tracesPage.spanDetail.modelLabels.gemma'
  if (normalized.includes('ollama')) return 'tracesPage.spanDetail.modelLabels.local'
  return null
}

export function localizeToolName(t: TFunction, value: string | null | undefined): string {
  return t(knownToolKey(value) ?? 'tracesPage.spanDetail.toolLabels.unknown')
}

export function localizeServerName(t: TFunction, value: string | null | undefined): string {
  return t(knownServerKey(value) ?? 'tracesPage.spanDetail.serverLabels.unknown')
}

export function localizeModelName(t: TFunction, value: string | null | undefined): string {
  return t(knownModelKey(value) ?? 'tracesPage.spanDetail.modelLabels.unknown')
}

export function localizeKnownSecondaryLabel(t: TFunction, kind: SpanKind, value: string | null): string | null {
  const key = kind === 'tool_call' ? knownToolKey(value) : kind === 'llm_call' ? knownModelKey(value) : null
  return key ? t(key) : null
}

export function localizeStopReason(t: TFunction, value: string | null | undefined): string {
  const normalized = normalizeCode(value)
  if (normalized === 'endturn' || normalized === 'stop') return t('tracesPage.spanDetail.stopReasonLabels.end_turn')
  if (normalized === 'length' || normalized === 'maxtokens') return t('tracesPage.spanDetail.stopReasonLabels.length')
  return t('tracesPage.spanDetail.stopReasonLabels.unknown')
}

export function localizeGuardAction(t: TFunction, value: string | null | undefined): string {
  const normalized = normalizeCode(value)
  if (normalized === 'allow' || normalized === 'pass') return t('tracesPage.spanDetail.guardActionLabels.allow')
  if (normalized === 'block' || normalized === 'deny') return t('tracesPage.spanDetail.guardActionLabels.block')
  return t('tracesPage.spanDetail.guardActionLabels.unknown')
}

export function localizeGuardRule(t: TFunction, value: string | null | undefined): string {
  const normalized = normalizeCode(value)
  if (normalized === 'piidetection') return t('tracesPage.spanDetail.guardRuleLabels.pii_detection')
  if (normalized === 'none') return t('tracesPage.spanDetail.guardRuleLabels.none')
  return t('tracesPage.spanDetail.guardRuleLabels.unknown')
}

export function localizeSpanError(t: TFunction, value: string | null | undefined): string {
  const normalized = normalizeCode(value)
  if (normalized.includes('connectiontimeout')) return t('tracesPage.spanDetail.errorLabels.connection_timeout')
  if (normalized.includes('llmtimeout') || normalized.includes('modeltimeout')) return t('tracesPage.spanDetail.errorLabels.model_timeout')
  if (normalized.includes('blockedbyguard')) return t('tracesPage.spanDetail.errorLabels.guard_blocked')
  return t('tracesPage.spanDetail.errorLabels.unknown')
}

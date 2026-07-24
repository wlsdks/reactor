import type { TFunction } from 'i18next'
import type { PatternType, RuleAction } from './api'

const RULE_ACTION_KEYS: Record<RuleAction, string> = {
  block: 'inputGuard.rules.actionLabels.block',
  warn: 'inputGuard.rules.actionLabels.warn',
  flag: 'inputGuard.rules.actionLabels.flag',
}

const PATTERN_TYPE_KEYS: Record<PatternType, string> = {
  regex: 'inputGuard.rules.patternTypeLabels.regex',
  keyword: 'inputGuard.rules.patternTypeLabels.keyword',
}

const AUDIT_ACTION_KEYS: Record<string, string> = {
  UPDATE_SETTINGS: 'inputGuard.audit.actionLabels.updateSettings',
  STAGE_CONFIG_UPDATE: 'inputGuard.audit.actionLabels.stageConfigUpdate',
  PIPELINE_REORDER: 'inputGuard.audit.actionLabels.pipelineReorder',
  SIMULATE: 'inputGuard.audit.actionLabels.simulate',
  RULE_CREATE: 'inputGuard.audit.actionLabels.ruleCreate',
  RULE_UPDATE: 'inputGuard.audit.actionLabels.ruleUpdate',
  RULE_DELETE: 'inputGuard.audit.actionLabels.ruleDelete',
  BLOCK: 'inputGuard.audit.actionLabels.block',
  WARN: 'inputGuard.audit.actionLabels.warn',
}

const AUDIT_TARGET_KEYS: Record<string, string> = {
  UPDATE_SETTINGS: 'inputGuard.audit.targetLabels.settings',
  STAGE_CONFIG_UPDATE: 'inputGuard.audit.targetLabels.stage',
  PIPELINE_REORDER: 'inputGuard.audit.targetLabels.pipeline',
  SIMULATE: 'inputGuard.audit.targetLabels.simulation',
  RULE_CREATE: 'inputGuard.audit.targetLabels.rule',
  RULE_UPDATE: 'inputGuard.audit.targetLabels.rule',
  RULE_DELETE: 'inputGuard.audit.targetLabels.rule',
  BLOCK: 'inputGuard.audit.targetLabels.request',
  WARN: 'inputGuard.audit.targetLabels.request',
}

const AUDIT_SUMMARY_KEYS: Record<string, string> = {
  UPDATE_SETTINGS: 'inputGuard.audit.summaryLabels.updateSettings',
  STAGE_CONFIG_UPDATE: 'inputGuard.audit.summaryLabels.stageConfigUpdate',
  PIPELINE_REORDER: 'inputGuard.audit.summaryLabels.pipelineReorder',
  SIMULATE: 'inputGuard.audit.summaryLabels.simulate',
  RULE_CREATE: 'inputGuard.audit.summaryLabels.ruleCreate',
  RULE_UPDATE: 'inputGuard.audit.summaryLabels.ruleUpdate',
  RULE_DELETE: 'inputGuard.audit.summaryLabels.ruleDelete',
  BLOCK: 'inputGuard.audit.summaryLabels.block',
  WARN: 'inputGuard.audit.summaryLabels.warn',
}

export const INPUT_GUARD_AUDIT_ACTIONS = Object.keys(AUDIT_ACTION_KEYS)

export function ruleActionLabel(t: TFunction, action: RuleAction): string {
  return t(RULE_ACTION_KEYS[action])
}

export function patternTypeLabel(t: TFunction, patternType: PatternType): string {
  return t(PATTERN_TYPE_KEYS[patternType])
}

export function auditActionLabel(t: TFunction, action: string): string {
  return t(AUDIT_ACTION_KEYS[action] ?? 'inputGuard.audit.unknownAction')
}

export function auditTargetLabel(t: TFunction, action: string): string {
  return t(AUDIT_TARGET_KEYS[action] ?? 'inputGuard.audit.unknownTarget')
}

export function auditSummaryLabel(t: TFunction, action: string): string {
  return t(AUDIT_SUMMARY_KEYS[action] ?? 'inputGuard.audit.unknownSummary')
}

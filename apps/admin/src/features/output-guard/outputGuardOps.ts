import { summarizeStatus, type OpsStatus } from '../../shared/lib/ops'
import { getErrorMessage } from '../../shared/lib/getErrorMessage'
import type {
  OutputGuardAuditLog,
  OutputGuardRule,
  SimulateOutputGuardResponse,
} from './types'

export interface OutputGuardSignal {
  id: 'activeRules' | 'regexValidity' | 'rejectCoverage' | 'auditChannel'
  status: OpsStatus
  detailId:
    | 'activeRulesReady'
    | 'activeRulesMissing'
    | 'regexValid'
    | 'regexInvalid'
    | 'rejectCoverageReady'
    | 'rejectCoverageMissing'
    | 'auditChannelReady'
    | 'auditChannelEmpty'
    | 'auditChannelUnavailable'
  meta?: {
    count?: number
    names?: string[]
  }
}

export interface OutputGuardOpsSummary {
  status: OpsStatus
  totalRules: number
  enabledRules: number
  disabledRules: number
  rejectRules: number
  maskRules: number
  invalidRules: number
  auditRows: number
  signals: OutputGuardSignal[]
}

export interface SimulationSummary {
  status: OpsStatus
  blocked: boolean
  modified: boolean
  matchedRuleCount: number
  invalidRuleCount: number
  blockedBy: string | null
  resultPreview: string
}

export function getRegexIssue(pattern: string): string | null {
  try {
    // Validate operator-provided regex patterns before relying on them in production.
    new RegExp(pattern)
    return null
  } catch (error) {
    return getErrorMessage(error)
  }
}

export function summarizeOutputGuardOps(
  rules: OutputGuardRule[],
  audits: OutputGuardAuditLog[],
  auditError: string | null,
): OutputGuardOpsSummary {
  const enabledRules = rules.filter((rule) => rule.enabled)
  const rejectRules = enabledRules.filter((rule) => rule.action === 'REJECT')
  const invalidRules = rules.filter((rule) => getRegexIssue(rule.pattern) != null)

  const signals: OutputGuardSignal[] = [
    enabledRules.length > 0
      ? {
          id: 'activeRules',
          status: 'PASS',
          detailId: 'activeRulesReady',
          meta: { count: enabledRules.length },
        }
      : {
          id: 'activeRules',
          status: 'FAIL',
          detailId: 'activeRulesMissing',
        },
    invalidRules.length === 0
      ? {
          id: 'regexValidity',
          status: 'PASS',
          detailId: 'regexValid',
        }
      : {
          id: 'regexValidity',
          status: 'FAIL',
          detailId: 'regexInvalid',
          meta: {
            count: invalidRules.length,
            names: invalidRules.map((rule) => rule.name),
          },
        },
    rejectRules.length > 0
      ? {
          id: 'rejectCoverage',
          status: 'PASS',
          detailId: 'rejectCoverageReady',
          meta: { count: rejectRules.length },
        }
      : {
          id: 'rejectCoverage',
          status: 'WARN',
          detailId: 'rejectCoverageMissing',
        },
    auditError
      ? {
          id: 'auditChannel',
          status: 'WARN',
          detailId: 'auditChannelUnavailable',
        }
      : audits.length > 0
        ? {
            id: 'auditChannel',
            status: 'PASS',
            detailId: 'auditChannelReady',
            meta: { count: audits.length },
          }
        : {
            id: 'auditChannel',
            status: 'WARN',
            detailId: 'auditChannelEmpty',
          },
  ]

  return {
    status: summarizeStatus(signals),
    totalRules: rules.length,
    enabledRules: enabledRules.length,
    disabledRules: rules.length - enabledRules.length,
    rejectRules: rejectRules.length,
    maskRules: enabledRules.filter((rule) => rule.action === 'MASK').length,
    invalidRules: invalidRules.length,
    auditRows: audits.length,
    signals,
  }
}

export function summarizeSimulation(
  simulationResult: SimulateOutputGuardResponse | null,
  simulationError: string | null,
): SimulationSummary | null {
  if (!simulationResult && !simulationError) return null

  if (simulationError) {
    return {
      status: 'FAIL',
      blocked: false,
      modified: false,
      matchedRuleCount: 0,
      invalidRuleCount: 0,
      blockedBy: null,
      resultPreview: simulationError,
    }
  }

  if (!simulationResult) return null

  return {
    status: simulationResult.blocked
      ? 'FAIL'
      : simulationResult.invalidRules.length > 0 || simulationResult.modified
        ? 'WARN'
        : 'PASS',
    blocked: simulationResult.blocked,
    modified: simulationResult.modified,
    matchedRuleCount: simulationResult.matchedRules.length,
    invalidRuleCount: simulationResult.invalidRules.length,
    blockedBy: simulationResult.blockedByRuleName ?? simulationResult.blockedByRuleId ?? null,
    resultPreview: simulationResult.resultContent,
  }
}

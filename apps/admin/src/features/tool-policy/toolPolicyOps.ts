import { summarizeStatus, classifyLoadIssue, type OpsStatus, type LoadIssue } from '../../shared/lib/ops'
import type { ToolPolicyState } from './types'

export interface ToolPolicySignal {
  id: 'policyContract' | 'runtimeEnforcement' | 'writeCoverage' | 'channelCoverage' | 'exceptionReview' | 'storedDrift'
  status: OpsStatus
  detailId:
    | 'contractHealthy'
    | 'contractMissing'
    | 'contractDenied'
    | 'contractTransport'
    | 'contractError'
    | 'runtimeEnforced'
    | 'runtimeDisabled'
    | 'runtimeConfigFallback'
    | 'writeCoverageReady'
    | 'writeCoverageMissing'
    | 'channelCoverageReady'
    | 'channelCoverageMissing'
    | 'exceptionReviewClean'
    | 'exceptionReviewNeeded'
    | 'storedDriftNone'
    | 'storedDriftDetected'
    | 'storedDriftNoStored'
  meta?: {
    count?: number
  }
}

export interface ToolPolicyDiffEntry {
  id:
    | 'enabled'
    | 'writeToolNames'
    | 'denyWriteChannels'
    | 'allowWriteToolNamesInDenyChannels'
    | 'allowWriteToolNamesByChannel'
    | 'denyWriteMessage'
  stored: string
  effective: string
  changed: boolean
}

export interface ToolPolicyOpsSummary {
  status: OpsStatus
  loadIssue: LoadIssue | null
  hasPolicy: boolean
  storedExists: boolean
  activeWriteTools: number
  denyChannels: number
  allowOverrides: number
  diffFields: ToolPolicyDiffEntry['id'][]
  signals: ToolPolicySignal[]
  diffs: ToolPolicyDiffEntry[]
}

function stableStringify(value: unknown): string {
  if (value == null) return '-'
  if (typeof value === 'string') return value
  if (typeof value === 'boolean' || typeof value === 'number') return String(value)

  if (Array.isArray(value)) {
    return JSON.stringify([...value].map((item) => String(item)).sort(), null, 2)
  }

  if (typeof value === 'object') {
    return JSON.stringify(sortObject(value as Record<string, unknown>), null, 2)
  }

  return String(value)
}

function sortObject(value: Record<string, unknown>): Record<string, unknown> {
  return Object.keys(value)
    .sort()
    .reduce<Record<string, unknown>>((acc, key) => {
      const current = value[key]
      if (Array.isArray(current)) {
        acc[key] = [...current].map((item) => String(item)).sort()
        return acc
      }
      if (current != null && typeof current === 'object') {
        acc[key] = sortObject(current as Record<string, unknown>)
        return acc
      }
      acc[key] = current
      return acc
    }, {})
}

function summarizeContractSignal(loadIssue: LoadIssue | null): ToolPolicySignal {
  if (loadIssue === 'notAdvertised') {
    return { id: 'policyContract', status: 'WARN', detailId: 'contractMissing' }
  }
  if (loadIssue === 'accessDenied') {
    return { id: 'policyContract', status: 'FAIL', detailId: 'contractDenied' }
  }
  if (loadIssue === 'transportFailure') {
    return { id: 'policyContract', status: 'FAIL', detailId: 'contractTransport' }
  }
  if (loadIssue === 'httpError') {
    return { id: 'policyContract', status: 'FAIL', detailId: 'contractError' }
  }
  return { id: 'policyContract', status: 'PASS', detailId: 'contractHealthy' }
}

function buildDiffs(state: ToolPolicyState): ToolPolicyDiffEntry[] {
  const stored = state.stored
  const effective = state.effective

  return [
    {
      id: 'enabled',
      stored: stableStringify(stored?.enabled ?? null),
      effective: stableStringify(effective.enabled),
      changed: (stored?.enabled ?? null) !== effective.enabled,
    },
    {
      id: 'writeToolNames',
      stored: stableStringify(stored?.writeToolNames ?? null),
      effective: stableStringify(effective.writeToolNames),
      changed: stableStringify(stored?.writeToolNames ?? null) !== stableStringify(effective.writeToolNames),
    },
    {
      id: 'denyWriteChannels',
      stored: stableStringify(stored?.denyWriteChannels ?? null),
      effective: stableStringify(effective.denyWriteChannels),
      changed: stableStringify(stored?.denyWriteChannels ?? null) !== stableStringify(effective.denyWriteChannels),
    },
    {
      id: 'allowWriteToolNamesInDenyChannels',
      stored: stableStringify(stored?.allowWriteToolNamesInDenyChannels ?? null),
      effective: stableStringify(effective.allowWriteToolNamesInDenyChannels),
      changed:
        stableStringify(stored?.allowWriteToolNamesInDenyChannels ?? null)
        !== stableStringify(effective.allowWriteToolNamesInDenyChannels),
    },
    {
      id: 'allowWriteToolNamesByChannel',
      stored: stableStringify(stored?.allowWriteToolNamesByChannel ?? null),
      effective: stableStringify(effective.allowWriteToolNamesByChannel),
      changed:
        stableStringify(stored?.allowWriteToolNamesByChannel ?? null)
        !== stableStringify(effective.allowWriteToolNamesByChannel),
    },
    {
      id: 'denyWriteMessage',
      stored: stableStringify(stored?.denyWriteMessage ?? null),
      effective: stableStringify(effective.denyWriteMessage),
      changed: stableStringify(stored?.denyWriteMessage ?? null) !== stableStringify(effective.denyWriteMessage),
    },
  ]
}

export function summarizeToolPolicyOps(
  state: ToolPolicyState | null,
  loadError: string | null,
): ToolPolicyOpsSummary {
  const loadIssue = classifyLoadIssue(loadError)
  const contractSignal = summarizeContractSignal(loadIssue)

  if (!state) {
    return {
      status: summarizeStatus([contractSignal]),
      loadIssue,
      hasPolicy: false,
      storedExists: false,
      activeWriteTools: 0,
      denyChannels: 0,
      allowOverrides: 0,
      diffFields: [],
      signals: [contractSignal],
      diffs: [],
    }
  }

  const effective = state.effective
  const diffs = buildDiffs(state)
  const allowOverrides = effective.allowWriteToolNamesInDenyChannels.length
    + Object.values(effective.allowWriteToolNamesByChannel).reduce((total, items) => total + items.length, 0)

  const signals: ToolPolicySignal[] = [
    contractSignal,
    effective.enabled
      ? {
          id: 'runtimeEnforcement',
          status: state.dynamicEnabled && state.stored
            ? 'PASS'
            : state.configEnabled
              ? 'WARN'
              : 'PASS',
          detailId: state.dynamicEnabled && state.stored
            ? 'runtimeEnforced'
            : state.configEnabled
              ? 'runtimeConfigFallback'
              : 'runtimeEnforced',
        }
      : {
          id: 'runtimeEnforcement',
          status: 'FAIL',
          detailId: 'runtimeDisabled',
        },
    effective.writeToolNames.length > 0
      ? {
          id: 'writeCoverage',
          status: 'PASS',
          detailId: 'writeCoverageReady',
          meta: { count: effective.writeToolNames.length },
        }
      : {
          id: 'writeCoverage',
          status: 'WARN',
          detailId: 'writeCoverageMissing',
        },
    effective.denyWriteChannels.length > 0
      ? {
          id: 'channelCoverage',
          status: 'PASS',
          detailId: 'channelCoverageReady',
          meta: { count: effective.denyWriteChannels.length },
        }
      : {
          id: 'channelCoverage',
          status: 'WARN',
          detailId: 'channelCoverageMissing',
        },
    allowOverrides === 0
      ? {
          id: 'exceptionReview',
          status: 'PASS',
          detailId: 'exceptionReviewClean',
        }
      : {
          id: 'exceptionReview',
          status: 'WARN',
          detailId: 'exceptionReviewNeeded',
          meta: { count: allowOverrides },
        },
    state.stored == null
      ? {
          id: 'storedDrift',
          status: state.configEnabled ? 'WARN' : 'PASS',
          detailId: 'storedDriftNoStored',
        }
      : diffs.some((diff) => diff.changed)
        ? {
            id: 'storedDrift',
            status: 'WARN',
            detailId: 'storedDriftDetected',
            meta: { count: diffs.filter((diff) => diff.changed).length },
          }
        : {
            id: 'storedDrift',
            status: 'PASS',
            detailId: 'storedDriftNone',
          },
  ]

  return {
    status: summarizeStatus(signals),
    loadIssue,
    hasPolicy: true,
    storedExists: state.stored != null,
    activeWriteTools: effective.writeToolNames.length,
    denyChannels: effective.denyWriteChannels.length,
    allowOverrides,
    diffFields: diffs.filter((diff) => diff.changed).map((diff) => diff.id),
    signals,
    diffs,
  }
}

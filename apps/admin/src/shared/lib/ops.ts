export type OpsStatus = 'PASS' | 'WARN' | 'FAIL'

export type LoadIssue =
  | 'notAdvertised'
  | 'accessDenied'
  | 'transportFailure'
  | 'httpError'

export function summarizeStatus(signals: ReadonlyArray<{ status: OpsStatus }>): OpsStatus {
  if (signals.some((signal) => signal.status === 'FAIL')) return 'FAIL'
  if (signals.some((signal) => signal.status === 'WARN')) return 'WARN'
  return 'PASS'
}

export function classifyLoadIssue(message: string | null): LoadIssue | null {
  const value = message?.trim().toLowerCase()
  if (!value) return null
  if (value.includes('http 404')) return 'notAdvertised'
  if (value.includes('http 401') || value.includes('http 403')) return 'accessDenied'
  if (
    value.includes('socket hang up')
    || value.includes('failed to fetch')
    || value.includes('networkerror')
    || value.includes('empty reply')
  ) {
    return 'transportFailure'
  }
  return 'httpError'
}

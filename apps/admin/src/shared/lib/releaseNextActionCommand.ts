export interface ReleaseNextActionCommandFields {
  command?: string | null
  preflightEnvFileCommand?: string | null
  releaseSmokeEnvFileCommand?: string | null
  remediationCommand?: string | null
}

export interface ReleaseActionRunbookFields extends ReleaseNextActionCommandFields {
  envFileCommand?: string | null
  releaseReadinessCommand?: string | null
}

export interface ReleaseActionRunbookLabels {
  command: string
  remediation: string
  env: string
  readiness: string
}

export interface ReleaseActionRunbookItem {
  key: 'command' | 'remediation' | 'env' | 'readiness'
  label: string
  value: string
}

function cleanCommand(value: string | null | undefined): string | null {
  const trimmed = value?.trim()
  return trimmed ? trimmed : null
}

function resolvePrimaryReleaseActionCommand(action: ReleaseNextActionCommandFields): string | null {
  return cleanCommand(action.command)
    || cleanCommand(action.preflightEnvFileCommand)
    || cleanCommand(action.releaseSmokeEnvFileCommand)
}

export function resolveReleaseNextActionCommand(action: ReleaseNextActionCommandFields): string | null {
  return resolvePrimaryReleaseActionCommand(action)
    || cleanCommand(action.remediationCommand)
}

export function resolveReleaseActionRunbookItems(
  action: ReleaseActionRunbookFields,
  labels: ReleaseActionRunbookLabels,
): ReleaseActionRunbookItem[] {
  return [
    { key: 'command', label: labels.command, value: resolvePrimaryReleaseActionCommand(action) },
    { key: 'remediation', label: labels.remediation, value: cleanCommand(action.remediationCommand) },
    { key: 'env', label: labels.env, value: cleanCommand(action.envFileCommand) },
    { key: 'readiness', label: labels.readiness, value: cleanCommand(action.releaseReadinessCommand) },
  ].filter((item): item is ReleaseActionRunbookItem => item.value !== null)
}

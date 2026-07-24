import type { useTranslation } from 'react-i18next'
import type { ControlPlaneProbeSnapshot } from '../controlPlaneProbes'
import type { McpProjectConnectionSnapshot } from '../projectConnections'

type TFn = ReturnType<typeof useTranslation>['t']

export function describeManifestStatus(t: TFn, snapshot: ControlPlaneProbeSnapshot): string {
  if (snapshot.manifestDeclared == null) return t('integrationsPage.probeManifestUnknown')
  return snapshot.manifestDeclared
    ? t('integrationsPage.probeManifestDeclared')
    : t('integrationsPage.probeManifestUndeclared')
}

export function describeProbeReason(t: TFn, snapshot: ControlPlaneProbeSnapshot): string {
  return t(`integrationsPage.probeReason.${snapshot.reason}`)
}

export function describeProbeHttp(t: TFn, snapshot: ControlPlaneProbeSnapshot): string {
  return snapshot.httpStatus == null
    ? t('integrationsPage.recoveryNoResponse')
    : `HTTP ${snapshot.httpStatus}`
}

export function describeProbeStatus(
  t: TFn,
  status: ControlPlaneProbeSnapshot['status'] | 'DISABLED',
): string {
  if (status === 'PASS' || status === 'WARN' || status === 'FAIL' || status === 'DISABLED') {
    return t(`integrationsPage.statusLabels.${status.toLowerCase()}`)
  }
  return status
}

export function describeProjectStatus(t: TFn, snapshot: McpProjectConnectionSnapshot): string {
  if (!snapshot.server) return t('integrationsPage.projectStatus.notRegistered')
  if (snapshot.server.status !== 'CONNECTED') return t('integrationsPage.projectStatus.registeredDisconnected')
  if (snapshot.error) return snapshot.error
  if (!snapshot.preflight) return t('integrationsPage.projectStatus.preflightUnavailable')
  if (snapshot.preflight.readyForProduction) return t('integrationsPage.projectStatus.ready')
  if (snapshot.preflight.ok) return t('integrationsPage.projectStatus.warnings')
  return t('integrationsPage.projectStatus.failed')
}

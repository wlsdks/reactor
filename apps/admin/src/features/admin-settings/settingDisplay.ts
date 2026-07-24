import type { AdminSetting } from './types'

export interface OperatorSettingLabels {
  cacheEnabled: string
  unknown: string
}

export function getOperatorSettingName(
  setting: AdminSetting,
  labels: OperatorSettingLabels,
): string {
  if (setting.key === 'cache.enabled') return labels.cacheEnabled

  const description = setting.description?.trim()
  if (description && /[가-힣]/.test(description)) return description

  return labels.unknown
}

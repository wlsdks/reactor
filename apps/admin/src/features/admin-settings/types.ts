export type SettingType = 'string' | 'boolean' | 'number' | 'json' | 'secret' | (string & {})

export interface AdminSetting {
  tenantId: string
  key: string
  value: string
  type: SettingType
  category: string
  description: string | null
  updatedBy: string | null
  updatedAt: string
  metadata: Record<string, unknown>
}

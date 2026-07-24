export interface GuardStageConfig {
  name: string
  order: number
  enabled: boolean
  className: string
  runtimeOverride: boolean | null
}

export interface InputGuardPipelineConfig {
  stages: GuardStageConfig[]
}

/** Response from PUT /api/admin/input-guard/settings */
export interface GuardSettingsUpdateResult {
  updated: number
  note: string
}

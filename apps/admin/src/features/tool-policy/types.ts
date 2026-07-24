export interface ToolPolicyRuleSet {
  enabled: boolean
  writeToolNames: string[]
  denyWriteChannels: string[]
  allowWriteToolNamesInDenyChannels: string[]
  allowWriteToolNamesByChannel: Record<string, string[]>
  denyWriteMessage: string
  createdAt: number
  updatedAt: number
}

export interface ToolPolicyState {
  configEnabled: boolean
  dynamicEnabled: boolean
  effective: ToolPolicyRuleSet
  stored: ToolPolicyRuleSet | null
}

export interface UpdateToolPolicyRequest {
  enabled: boolean
  writeToolNames?: string[]
  denyWriteChannels?: string[]
  allowWriteToolNamesInDenyChannels?: string[]
  allowWriteToolNamesByChannel?: Record<string, string[]>
  denyWriteMessage?: string
}

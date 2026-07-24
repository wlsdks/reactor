export type OutputBlockAction = 'REJECT' | 'MASK'

export interface OutputGuardRule {
  id: string
  name: string
  pattern: string
  action: OutputBlockAction
  priority: number
  enabled: boolean
  createdAt: number
  updatedAt: number
}

export interface CreateOutputGuardRuleRequest {
  name: string
  pattern: string
  action: OutputBlockAction
  priority?: number
  enabled?: boolean
}

export interface UpdateOutputGuardRuleRequest {
  name?: string
  pattern?: string
  action?: OutputBlockAction
  priority?: number
  enabled?: boolean
}

export interface SimulateOutputGuardRequest {
  content: string
  includeDisabled?: boolean
}

export interface OutputGuardSimulationMatch {
  ruleId: string
  ruleName: string
  action: OutputBlockAction
  priority: number
}

export interface OutputGuardSimulationInvalidRule {
  ruleId: string
  ruleName: string
  reason: string
}

export interface SimulateOutputGuardResponse {
  originalContent: string
  resultContent: string
  blocked: boolean
  modified: boolean
  blockedByRuleId: string | null
  blockedByRuleName: string | null
  matchedRules: OutputGuardSimulationMatch[]
  invalidRules: OutputGuardSimulationInvalidRule[]
}

export interface OutputGuardAuditLog {
  id: string
  ruleId: string | null
  action: string
  actor: string
  detail: string | null
  createdAt: number
}

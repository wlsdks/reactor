import type {
  OutputGuardRule,
  CreateOutputGuardRuleRequest,
  UpdateOutputGuardRuleRequest,
  SimulateOutputGuardRequest,
  SimulateOutputGuardResponse,
  OutputGuardAuditLog,
} from './types'
import { api } from '../../shared/api/client'

export const listRules = (): Promise<OutputGuardRule[]> =>
  api.get('output-guard/rules', { searchParams: { limit: 200 } }).json()

export const listRuleAudits = (limit = 100): Promise<OutputGuardAuditLog[]> =>
  api.get('output-guard/rules/audits', { searchParams: { limit: String(limit) } }).json()

export const createRule = (request: CreateOutputGuardRuleRequest): Promise<OutputGuardRule> =>
  api.post('output-guard/rules', { json: request }).json()

export const updateRule = (id: string, request: UpdateOutputGuardRuleRequest): Promise<OutputGuardRule> =>
  api.put(`output-guard/rules/${id}`, { json: request }).json()

export const deleteRule = (id: string): Promise<void> =>
  api.delete(`output-guard/rules/${id}`).json()

export const simulateGuard = (request: SimulateOutputGuardRequest): Promise<SimulateOutputGuardResponse> =>
  api.post('output-guard/rules/simulate', { json: request }).json()

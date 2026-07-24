import { api } from '../../shared/api/client'
import type {
  GuardStageConfig,
  InputGuardPipelineConfig,
  GuardSettingsUpdateResult,
} from './types'

export const getPipelineConfig = async (): Promise<InputGuardPipelineConfig> => {
  const raw = await api.get('admin/input-guard/pipeline').json<GuardStageConfig[] | InputGuardPipelineConfig>()
  // Backend returns bare array; normalize to { stages: [...] }
  if (Array.isArray(raw)) return { stages: raw }
  return raw
}

export const updateGuardSettings = (
  settings: Record<string, string>,
): Promise<GuardSettingsUpdateResult> =>
  api.put('admin/input-guard/settings', { json: { settings } }).json()

// ── Audit Log (R461) ──────────────────────────────────────────────
export interface InputGuardAudit {
  id: string
  timestamp: string
  category: string
  action: string
  actor: string
  resourceType?: string | null
  resourceId?: string | null
  detail?: string | null
}

export interface ListAuditsResponse {
  audits: InputGuardAudit[]
  total: number
}

/**
 * R461: Input Guard 감사 로그 조회.
 * @param limit 1~500 (기본 200)
 * @param action optional action 필터 (예: UPDATE_SETTINGS)
 */
export const listInputGuardAudits = (
  limit: number = 200,
  action?: string,
): Promise<ListAuditsResponse> => {
  const searchParams: Record<string, string | number> = { limit }
  if (action) searchParams.action = action
  return api.get('admin/input-guard/audits', { searchParams }).json()
}

// ── Simulate (dry-run) ───────────────────────────────────────────
export interface SimulateStageResult {
  stage: string
  order: number
  passed: boolean
  action: string
  durationMs: number
  reason: string | null
  category: string | null
}

export interface SimulateResponse {
  passed: boolean
  totalDurationMs: number
  finalAction: string
  blockingStage: string | null
  stageResults: SimulateStageResult[]
}

export interface SimulateRequest {
  input: string
  userId?: string
  sessionId?: string
  channel?: string
}

export const simulateInputGuard = (req: SimulateRequest): Promise<SimulateResponse> =>
  api.post('admin/input-guard/simulate', { json: req }).json()

// ── Stats ────────────────────────────────────────────────────────
export interface ReasonCount {
  reason: string
  count: number
}

export interface StageStats {
  stage: string
  triggered: number
  allowed: number
  rejected: number
  errors: number
  topReasons: ReasonCount[]
}

export interface GuardStatsResponse {
  periodHours: number
  totalRequests: number
  totalAllowed: number
  totalRejected: number
  totalErrors: number
  blockRate: number
  byStage: StageStats[]
}

export const getInputGuardStats = (
  hours: number = 24,
  tenantId?: string,
): Promise<GuardStatsResponse> => {
  const searchParams: Record<string, string | number> = { hours }
  if (tenantId) searchParams.tenantId = tenantId
  return api.get('admin/input-guard/stats', { searchParams }).json()
}

// ── Rules CRUD (R463) ─────────────────────────────────────────────
export type PatternType = 'regex' | 'keyword'
export type RuleAction = 'block' | 'warn' | 'flag'

export interface InputGuardRule {
  id: string
  name: string
  pattern: string
  patternType: PatternType
  action: RuleAction
  priority: number
  category: string
  description: string | null
  enabled: boolean
  createdAt: string
  updatedAt: string
}

export interface InputGuardRuleRequest {
  name: string
  pattern: string
  patternType: PatternType
  action: RuleAction
  priority: number
  category: string
  description?: string | null
  enabled: boolean
}

export interface ListRulesResponse {
  rules: InputGuardRule[]
  total: number
}

export const listInputGuardRules = (): Promise<ListRulesResponse> =>
  api.get('admin/input-guard/rules', { searchParams: { limit: 200 } }).json()

export const getInputGuardRule = (id: string): Promise<InputGuardRule> =>
  api.get(`admin/input-guard/rules/${encodeURIComponent(id)}`).json()

export const createInputGuardRule = (
  req: InputGuardRuleRequest,
): Promise<InputGuardRule> =>
  api.post('admin/input-guard/rules', { json: req }).json()

export const updateInputGuardRule = (
  id: string,
  req: InputGuardRuleRequest,
): Promise<InputGuardRule> =>
  api.put(`admin/input-guard/rules/${encodeURIComponent(id)}`, { json: req }).json()

export const deleteInputGuardRule = async (id: string): Promise<void> => {
  await api.delete(`admin/input-guard/rules/${encodeURIComponent(id)}`)
}

// ── Stage Config (R464) ───────────────────────────────────────────
export interface StageConfigField {
  value: string
  default: string
  overridden: boolean
  type: string
  description: string
  restartRequired: boolean
}

export interface StageConfigResponse {
  stageName: string
  className: string
  enabled: boolean
  order: number
  config: Record<string, StageConfigField>
  note?: string | null
}

export const getStageConfig = (stageName: string): Promise<StageConfigResponse> =>
  api.get(`admin/input-guard/stages/${encodeURIComponent(stageName)}/config`).json()

export interface StageConfigUpdateRequest {
  config: Record<string, string>
}

export interface StageConfigUpdateResponse {
  stageName: string
  updated: number
  restartRequired: string[]
  note: string
}

export const updateStageConfig = (
  stageName: string,
  req: StageConfigUpdateRequest,
): Promise<StageConfigUpdateResponse> =>
  api.put(`admin/input-guard/stages/${encodeURIComponent(stageName)}/config`, { json: req }).json()

// ── Pipeline Reorder (R464) ───────────────────────────────────────
export interface PipelineReorderRequest {
  order: string[]
}

export interface PipelineReorderResponse {
  order: string[]
  note: string
}

export const reorderPipeline = (
  req: PipelineReorderRequest,
): Promise<PipelineReorderResponse> =>
  api.put('admin/input-guard/pipeline/reorder', { json: req }).json()

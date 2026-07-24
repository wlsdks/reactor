/** Eval run from GET /api/admin/evals/runs */
export interface EvalRun {
  evalRunId: string
  totalCases: number
  passCount: number
  avgScore: number
  avgLatencyMs: number
  totalTokens: number
  totalCost: number
  startedAt: string
  endedAt: string
}

/** Daily pass rate point from GET /api/admin/evals/pass-rate */
export interface EvalPassRatePoint {
  day: string
  total: number
  passed: number
  avgScore: number
}

/** Enabled persisted case returned by GET /api/admin/agent-eval/cases. */
export interface PersistedEvalCase {
  id: string
  name: string
  enabled: boolean
  tags: string[]
  sourceRunId: string | null
  assertionCount: number
  updatedAt: string
}

/** Live LangSmith evidence returned by POST /api/admin/agent-eval/langsmith/sync. */
export interface LangSmithPersistedEvalSyncResult {
  ok: boolean
  status: string
  scope: string
  mode: string
  datasetName: string
  created: boolean
  examples: number
  exampleIds: string[]
  caseIds: string[]
  metadataCaseIds: string[]
  sourceRunIds: string[]
  caseSourceRunIds: Record<string, string>
  splitCounts: Record<string, number>
  secretFree: boolean
  exampleContract: Record<string, unknown>
  sdkContract: Record<string, unknown>
}

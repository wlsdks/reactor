import { api } from '../../shared/api/client'
import { snakeToCamel } from '../../shared/lib/caseTransform'
import type {
  EvalRun,
  EvalPassRatePoint,
  LangSmithPersistedEvalSyncResult,
  PersistedEvalCase,
} from './types'

export const getEvalRuns = async (days = 30): Promise<EvalRun[]> => {
  const raw = await api.get('admin/evals/runs', {
    searchParams: { days },
  }).json()
  return snakeToCamel(raw) as EvalRun[]
}

export const getEvalPassRate = async (days = 30): Promise<EvalPassRatePoint[]> => {
  const raw = await api.get('admin/evals/pass-rate', {
    searchParams: { days },
  }).json()
  return snakeToCamel(raw) as EvalPassRatePoint[]
}

export const getPersistedEvalCases = async (): Promise<PersistedEvalCase[]> => {
  const raw = await api.get('admin/agent-eval/cases', {
    searchParams: { enabledOnly: true, limit: 100 },
  }).json()
  return snakeToCamel(raw) as PersistedEvalCase[]
}

export const syncPersistedEvalCases = (
  datasetName: string,
): Promise<LangSmithPersistedEvalSyncResult> =>
  api.post('admin/agent-eval/langsmith/sync', {
    json: {
      datasetName,
      caseIds: [],
      description: 'Reactor admin persisted eval case dataset sync',
    },
  }).json()

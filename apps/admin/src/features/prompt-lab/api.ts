import type {
  PromptExperiment,
  PromptExperimentStatus,
  PromptExperimentStatusResponse,
  PromptTrial,
  PromptExperimentReport,
  CreatePromptExperimentRequest,
  AutoOptimizeRequest,
  AnalyzeFeedbackRequest,
  PromptFeedbackAnalysis,
} from './types'
import { api } from '../../shared/api/client'

export const listExperiments = (status?: PromptExperimentStatus): Promise<PromptExperiment[]> => {
  const searchParams: Record<string, string | number> = { limit: 200 }
  if (status) searchParams.status = status
  return api.get('prompt-lab/experiments', { searchParams }).json()
}

export const createExperiment = (request: CreatePromptExperimentRequest): Promise<PromptExperiment> =>
  api.post('prompt-lab/experiments', { json: request }).json()

export const getExperiment = (id: string): Promise<PromptExperiment> =>
  api.get(`prompt-lab/experiments/${id}`).json()

export const getExperimentStatus = (id: string): Promise<PromptExperimentStatusResponse> =>
  api.get(`prompt-lab/experiments/${id}/status`).json()

export const getExperimentTrials = (id: string): Promise<PromptTrial[]> =>
  api.get(`prompt-lab/experiments/${id}/trials`).json()

export const getExperimentReport = (id: string): Promise<PromptExperimentReport> =>
  api.get(`prompt-lab/experiments/${id}/report`).json()

export const runExperiment = (id: string): Promise<void> =>
  api.post(`prompt-lab/experiments/${id}/run`).json()

export const cancelExperiment = (id: string): Promise<void> =>
  api.post(`prompt-lab/experiments/${id}/cancel`).json()

export const activateExperimentRecommendation = (id: string): Promise<void> =>
  api.post(`prompt-lab/experiments/${id}/activate`).json()

export const deleteExperiment = (id: string): Promise<void> =>
  api.delete(`prompt-lab/experiments/${id}`).json()

export const autoOptimize = (request: AutoOptimizeRequest): Promise<{ status: string; templateId: string; jobId: string }> =>
  api.post('prompt-lab/auto-optimize', { json: request }).json()

export const analyzeFeedback = (request: AnalyzeFeedbackRequest): Promise<PromptFeedbackAnalysis> =>
  api.post('prompt-lab/analyze', { json: request }).json()

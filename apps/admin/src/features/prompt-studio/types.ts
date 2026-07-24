export type {
  TemplateResponse,
  TemplateDetailResponse,
  VersionResponse,
  VersionStatus,
  CreateTemplateRequest,
  UpdateTemplateRequest,
  CreateVersionRequest,
} from '../prompts/types'

export type {
  PromptExperiment,
  PromptExperimentStatus,
  PromptExperimentStatusResponse,
  PromptTrial,
  PromptVersionSummary,
  PromptRecommendation,
  PromptExperimentReport,
  CreatePromptExperimentRequest,
  PromptLabTestQueryRequest,
  PromptLabEvaluationConfigRequest,
} from '../prompt-lab/types'

export type StudioTab = 'versions' | 'experiments' | 'settings'

import type {
  TemplateResponse,
  TemplateDetailResponse,
  CreateTemplateRequest,
  UpdateTemplateRequest,
  VersionResponse,
  CreateVersionRequest,
} from './types'
import { api } from '../../shared/api/client'

export const listTemplates = (): Promise<TemplateResponse[]> =>
  api.get('prompt-templates', { searchParams: { limit: 200 } }).json()

export const getTemplate = (id: string): Promise<TemplateDetailResponse> =>
  api.get(`prompt-templates/${id}`).json()

export const createTemplate = (request: CreateTemplateRequest): Promise<TemplateResponse> =>
  api.post('prompt-templates', { json: request }).json()

export const updateTemplate = (id: string, request: UpdateTemplateRequest): Promise<TemplateResponse> =>
  api.put(`prompt-templates/${id}`, { json: request }).json()

export const deleteTemplate = (id: string): Promise<void> =>
  api.delete(`prompt-templates/${id}`).json()

export const createVersion = (templateId: string, request: CreateVersionRequest): Promise<VersionResponse> =>
  api.post(`prompt-templates/${templateId}/versions`, { json: request }).json()

export const activateVersion = (templateId: string, versionId: string): Promise<VersionResponse> =>
  api.put(`prompt-templates/${templateId}/versions/${versionId}/activate`).json()

export const archiveVersion = (templateId: string, versionId: string): Promise<VersionResponse> =>
  api.put(`prompt-templates/${templateId}/versions/${versionId}/archive`).json()

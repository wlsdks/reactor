export type VersionStatus = 'DRAFT' | 'ACTIVE' | 'ARCHIVED'

export interface TemplateResponse {
  id: string
  name: string
  description: string
  createdAt: number
  updatedAt: number
}

export interface TemplateDetailResponse {
  id: string
  name: string
  description: string
  activeVersion: VersionResponse | null
  versions: VersionResponse[]
  createdAt: number
  updatedAt: number
}

export interface VersionResponse {
  id: string
  templateId: string
  version: number
  content: string
  status: VersionStatus
  changeLog: string
  createdAt: number
}

export interface CreateTemplateRequest {
  name: string
  description?: string
}

export interface UpdateTemplateRequest {
  name?: string
  description?: string
}

export interface CreateVersionRequest {
  content: string
  changeLog?: string
}

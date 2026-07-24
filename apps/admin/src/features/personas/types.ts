export interface PersonaResponse {
  id: string
  name: string
  systemPrompt: string
  isDefault: boolean
  description: string | null
  responseGuideline: string | null
  welcomeMessage: string | null
  promptTemplateId: string | null
  icon: string | null
  isActive: boolean
  createdAt: number
  updatedAt: number
}

export interface CreatePersonaRequest {
  name: string
  systemPrompt: string
  isDefault?: boolean
  description?: string | null
  responseGuideline?: string | null
  welcomeMessage?: string | null
  promptTemplateId?: string | null
  icon?: string | null
  isActive?: boolean
}

export interface UpdatePersonaRequest {
  name?: string
  systemPrompt?: string
  isDefault?: boolean
  description?: string | null
  responseGuideline?: string | null
  welcomeMessage?: string | null
  promptTemplateId?: string | null
  icon?: string | null
  isActive?: boolean
}

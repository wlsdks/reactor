export interface AgentSpec {
  id: string
  name: string
  description: string
  toolNames: string[]
  keywords: string[]
  /** A short server-provided preview. The resolved prompt is fetched separately. */
  systemPromptPreview: string | null
  hasSystemPrompt: boolean
  mode: string
  independentExecution: boolean
  enabled: boolean
  createdAt: string
  updatedAt: string
}

export interface CreateAgentSpecRequest {
  name: string
  description?: string
  toolNames?: string[]
  keywords?: string[]
  systemPrompt?: string
  mode?: string
  independentExecution?: boolean
  enabled?: boolean
}

export interface UpdateAgentSpecRequest {
  name?: string
  description?: string
  toolNames?: string[]
  keywords?: string[]
  systemPrompt?: string
  mode?: string
  independentExecution?: boolean
  enabled?: boolean
}

/** Response shape of GET /api/admin/agent-specs/{id}/system-prompt.
 *  Each call writes an admin audit log entry on the server. */
export interface AgentSpecSystemPrompt {
  systemPrompt: string | null
}

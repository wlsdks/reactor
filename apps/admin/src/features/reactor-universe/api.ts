import type {
  AgentSpec,
  AgentSpecSystemPrompt,
  CreateAgentSpecRequest,
  UpdateAgentSpecRequest,
} from './types'
import { api } from '../../shared/api/client'
import { z } from 'zod/v4'

const agentSpecResponseSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  toolNames: z.array(z.string()),
  keywords: z.array(z.string()),
  systemPromptPreview: z.string().nullable(),
  hasSystemPrompt: z.boolean(),
  mode: z.string(),
  independentExecution: z.boolean(),
  enabled: z.boolean(),
  createdAt: z.string(),
  updatedAt: z.string(),
})

const agentSpecSystemPromptSchema = z.object({
  systemPrompt: z.string().nullable(),
})

function parseAgentSpec(payload: unknown): AgentSpec {
  const result = agentSpecResponseSchema.safeParse(payload)
  if (!result.success) {
    throw new Error('AI 역할 정보를 확인할 수 없어요. 잠시 후 다시 시도해 주세요.')
  }
  return result.data
}

export const listAgentSpecs = async (): Promise<AgentSpec[]> => {
  const payload = await api.get('admin/agent-specs').json<unknown>()
  const result = z.array(agentSpecResponseSchema).safeParse(payload)
  if (!result.success) {
    throw new Error('AI 역할 목록을 확인할 수 없어요. 잠시 후 다시 시도해 주세요.')
  }
  return result.data
}

export const getAgentSpec = async (id: string): Promise<AgentSpec> =>
  parseAgentSpec(await api.get(`admin/agent-specs/${encodeURIComponent(id)}`).json<unknown>())

export const createAgentSpec = async (request: CreateAgentSpecRequest): Promise<AgentSpec> =>
  parseAgentSpec(await api.post('admin/agent-specs', { json: request }).json<unknown>())

export const updateAgentSpec = async (id: string, request: UpdateAgentSpecRequest): Promise<AgentSpec> =>
  parseAgentSpec(await api.put(`admin/agent-specs/${encodeURIComponent(id)}`, { json: request }).json<unknown>())

export const deleteAgentSpec = (id: string): Promise<void> =>
  api.delete(`admin/agent-specs/${id}`).then(() => undefined)

/**
 * Fetches the resolved system prompt for an agent spec.
 *
 * NOTE: Each call writes an audit log entry on the backend. Callers should
 * cache the response (e.g. TanStack Query `staleTime: Infinity`) to avoid
 * re-triggering the audit log on remount.
 */
export const getAgentSpecSystemPrompt = async (id: string): Promise<AgentSpecSystemPrompt> => {
  const payload = await api.get(`admin/agent-specs/${encodeURIComponent(id)}/system-prompt`).json<unknown>()
  const result = agentSpecSystemPromptSchema.safeParse(payload)
  if (!result.success) {
    throw new Error('답변 원칙을 확인할 수 없어요. 잠시 후 다시 시도해 주세요.')
  }
  return result.data
}

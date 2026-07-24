export interface ChatRequest {
  message: string
  model?: string
  systemPrompt?: string
  personaId?: string
  promptTemplateId?: string
  runtime?: 'langgraph' | 'langchain_agent'
  graphProfile?: string
  metadata?: Record<string, unknown>
  responseFormat?: 'TEXT' | 'JSON'
}

export interface ChatVerifiedSource {
  title: string
  url: string
  toolName?: string | null
}

export interface ChatToolSignal {
  toolName: string
  grounded?: boolean
  answerMode?: string | null
  freshness?: Record<string, unknown> | null
  retrievedAt?: string | null
}

export interface ChatOutputGuard {
  action: string
  stage?: string | null
  reason?: string | null
}

export interface TokenUsage {
  promptTokens: number
  completionTokens: number
  totalTokens: number
  // R472: Provider-specific fields are present only when the active provider
  // reports the corresponding usage measurement.
  // thoughtsTokens — reasoning-token usage.
  // cachedContentTokens — cached-context usage.
  // toolUsePromptTokens — tool-result prompt usage.
  // trafficType — provider capacity mode.
  thoughtsTokens?: number | null
  cachedContentTokens?: number | null
  toolUsePromptTokens?: number | null
  trafficType?: string | null
}

export interface ChatResponseMetadata {
  tokenUsage?: TokenUsage | null
  grounded?: boolean
  answerMode?: string | null
  verifiedSourceCount?: number
  verifiedSources?: ChatVerifiedSource[]
  freshness?: Record<string, unknown> | null
  retrievedAt?: string | null
  blockReason?: string | null
  outputGuard?: ChatOutputGuard | null
  toolSignals?: ChatToolSignal[]
  [key: string]: unknown
}

export interface ChatResponse {
  content: string | null
  success: boolean
  model?: string | null
  toolsUsed: string[]
  durationMs?: number | null
  errorMessage?: string | null
  errorCode?: string | null
  grounded?: boolean | null
  verifiedSourceCount?: number | null
  blockReason?: string | null
  metadata?: ChatResponseMetadata | null
}

export type StreamEventType = 'message' | 'tool_start' | 'tool_end' | 'error' | 'done'

export interface StreamEvent {
  event: StreamEventType | (string & {})
  data: string
}

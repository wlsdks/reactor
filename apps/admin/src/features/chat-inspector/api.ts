import i18n from 'i18next'
import { api, fetchWithAuth } from '../../shared/api/client'
import type { ChatRequest, ChatResponse, StreamEvent } from './types'

// Reactor's agent runner may legitimately take up to 120 seconds before it
// returns a structured timeout result. Keep the inspector connected long enough
// to observe that backend state instead of turning it into a client timeout.
export const CHAT_REQUEST_TIMEOUT_MS = 130_000

function normalizeResponse(raw: Record<string, unknown>): ChatResponse {
  // R474: The backend returns `tokenUsage` at the top level while older
  // callers can still use input/output names. Normalize both shapes here.
  const topLevelTokenUsage = raw.tokenUsage as Record<string, unknown> | undefined
  const legacyInput = typeof raw.inputTokens === 'number' ? raw.inputTokens : 0
  const legacyOutput = typeof raw.outputTokens === 'number' ? raw.outputTokens : 0
  const tokenUsageForMetadata = topLevelTokenUsage
    ?? (legacyInput > 0 || legacyOutput > 0 ? {
      promptTokens: legacyInput,
      completionTokens: legacyOutput,
      totalTokens: legacyInput + legacyOutput,
    } : undefined)

  // Merge usage into the metadata object so consumers have one response shape.
  const rawMetadata = (raw.metadata as Record<string, unknown> | null | undefined) ?? null
  const mergedMetadata = tokenUsageForMetadata
    ? { ...(rawMetadata ?? {}), tokenUsage: tokenUsageForMetadata }
    : rawMetadata

  return {
    content: (raw.content ?? raw.response ?? null) as string | null,
    success: typeof raw.success === 'boolean' ? raw.success : raw.errorCode == null,
    model: (raw.model ?? null) as string | null,
    toolsUsed: Array.isArray(raw.toolsUsed)
      ? raw.toolsUsed as string[]
      : Array.isArray(raw.toolCalls)
        ? (raw.toolCalls as string[])
        : [],
    durationMs: typeof raw.durationMs === 'number' ? raw.durationMs : null,
    errorMessage: (raw.errorMessage ?? null) as string | null,
    errorCode: (raw.errorCode ?? null) as string | null,
    grounded: typeof raw.grounded === 'boolean' ? raw.grounded : null,
    verifiedSourceCount: typeof raw.verifiedSourceCount === 'number' ? raw.verifiedSourceCount : null,
    blockReason: (raw.blockReason ?? null) as string | null,
    metadata: mergedMetadata as ChatResponse['metadata'],
  }
}

export async function sendChat(request: ChatRequest): Promise<ChatResponse> {
  const raw: Record<string, unknown> = await api.post('chat', {
    json: request,
    timeout: CHAT_REQUEST_TIMEOUT_MS,
  }).json()
  return normalizeResponse(raw)
}

function parseSseEvent(rawEvent: string): StreamEvent {
  let event = 'message'
  const dataLines: string[] = []

  rawEvent.split('\n').forEach((line) => {
    const trimmed = line.trimEnd()
    if (!trimmed || trimmed.startsWith(':')) return
    if (trimmed.startsWith('event:')) {
      event = trimmed.slice('event:'.length).trim() || 'message'
      return
    }
    if (trimmed.startsWith('data:')) {
      dataLines.push(trimmed.slice('data:'.length).trimStart())
    }
  })

  return {
    event,
    data: dataLines.join('\n'),
  }
}

const SSE_IDLE_TIMEOUT_MS = 60_000

export async function streamChat(
  request: ChatRequest,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const idleController = new AbortController()
  let idleTimer: ReturnType<typeof setTimeout> | undefined = setTimeout(
    () => idleController.abort(),
    SSE_IDLE_TIMEOUT_MS,
  )

  // Combine caller signal with idle timeout signal
  const combinedSignal = signal
    ? AbortSignal.any([signal, idleController.signal])
    : idleController.signal

  const apiPrefix = (import.meta.env.VITE_API_URL as string | undefined) ?? ''
  const res = await fetchWithAuth(`${apiPrefix}/api/chat/stream`, {
    method: 'POST',
    body: JSON.stringify(request),
    signal: combinedSignal,
  })

  const reader = res.body?.getReader()
  if (!reader) throw new Error(i18n.t('chatInspector.errors.sseUnavailable'))

  const decoder = new TextDecoder()
  let buffer = ''

  function resetIdleTimer() {
    clearTimeout(idleTimer)
    idleTimer = setTimeout(() => idleController.abort(), SSE_IDLE_TIMEOUT_MS)
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      resetIdleTimer()
      buffer += decoder.decode(value, { stream: true })

      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const chunk = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)

        if (chunk.trim()) {
          onEvent(parseSseEvent(chunk))
        }

        boundary = buffer.indexOf('\n\n')
      }
    }

    if (buffer.trim()) {
      onEvent(parseSseEvent(buffer))
    }
  } finally {
    clearTimeout(idleTimer)
    reader.cancel().catch(() => {})
  }
}

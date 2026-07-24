import type { PersonaResponse, CreatePersonaRequest, UpdatePersonaRequest } from './types'
import { api, fetchWithAuth } from '../../shared/api/client'

export const listPersonas = (): Promise<PersonaResponse[]> =>
  api.get('personas', { searchParams: { limit: 200 } }).json()

export const getPersona = (id: string): Promise<PersonaResponse> =>
  api.get(`personas/${id}`).json()

export const createPersona = (request: CreatePersonaRequest): Promise<PersonaResponse> =>
  api.post('personas', { json: request }).json()

export const updatePersona = (id: string, request: UpdatePersonaRequest): Promise<PersonaResponse> =>
  api.put(`personas/${id}`, { json: request }).json()

export const deletePersona = (id: string): Promise<void> =>
  api.delete(`personas/${id}`).json()

// --- Playground SSE streaming ---

export interface StreamCallbacks {
  onToken: (text: string) => void
  onToolStart: (name: string) => void
  onToolEnd: (name: string) => void
  onDone: () => void
  onError: (error: Error) => void
}

const SSE_IDLE_TIMEOUT_MS = 60_000

export async function streamPersonaChat(
  personaId: string,
  message: string,
  sessionId: string,
  callbacks: StreamCallbacks,
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

  const body = {
    message,
    personaId,
    metadata: {
      sessionId,
      channel: 'playground',
    },
  }

  const apiPrefix = import.meta.env.VITE_API_URL || ''
  const res = await fetchWithAuth(`${apiPrefix}/api/chat/stream`, {
    method: 'POST',
    body: JSON.stringify(body),
    signal: combinedSignal,
  })

  const reader = res.body?.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  function resetIdleTimer() {
    clearTimeout(idleTimer)
    idleTimer = setTimeout(() => idleController.abort(), SSE_IDLE_TIMEOUT_MS)
  }

  try {
    while (reader) {
      const { done, value } = await reader.read()
      if (done) break

      resetIdleTimer()
      buffer += decoder.decode(value, { stream: true })

      const parts = buffer.split('\n\n')
      buffer = parts.pop() ?? ''

      for (const part of parts) {
        const lines = part.split('\n')
        let eventType = 'message'
        const dataLines: string[] = []

        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            dataLines.push(line.slice(5))
          }
        }

        const data = dataLines.join('\n')

        switch (eventType) {
          case 'message':
            if (data) callbacks.onToken(data)
            break
          case 'tool_start':
            callbacks.onToolStart(data)
            break
          case 'tool_end':
            callbacks.onToolEnd(data)
            break
          case 'error':
            callbacks.onError(new Error(data || 'Stream error'))
            break
          case 'done':
            callbacks.onDone()
            break
        }
      }
    }
  } finally {
    clearTimeout(idleTimer)
    reader?.cancel().catch(() => {})
  }
}

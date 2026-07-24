import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { PageHeader } from '../../../shared/ui'
import * as chatApi from '../api'
import { parseChatInspectorPrefill } from '../prefill'
import type { ChatRequest, ChatResponse, ChatResponseMetadata, StreamEvent } from '../types'
import { ConfigToolbar } from './ConfigToolbar'
import { ErrorDisplay } from './ErrorDisplay'
import { MessageInputPanel } from './MessageInputPanel'
import { ModePanel, type ChatMode } from './ModePanel'
import { PrefillBanner } from './PrefillBanner'
import { ResponseDetailPanel } from './ResponseDetailPanel'
import { SessionTotalPanel } from './SessionTotalPanel'
import { StreamOutputPanel } from './StreamOutputPanel'
import { getErrorMessage, isAbortError, resolveApiError } from '../../../shared/lib/getErrorMessage'
import { useModelPricing } from '../useModelPricing'
import {
  calculateCost,
  DEFAULT_BUDGET,
  isBudgetExceeded,
  shouldCollapsePayload,
  type BudgetThreshold,
  type SessionTotals,
} from '../cost'
import './ChatInspectorManager.css'

interface InspectorError {
  primaryMessage: string
  technicalCode?: string | null
  technicalMessage?: string | null
}

function redactEndpoint(value: string, replacement: string): string {
  return value.replace(/https?:\/\/[^\s)\]}]+/gi, replacement)
}

function getMetadata(result: ChatResponse | null): ChatResponseMetadata | null {
  return result?.metadata ?? null
}

/**
 * Parse a stream event `data` payload for a token usage object. Stream
 * servers typically embed `tokenUsage` inside `done` / meta events as a JSON
 * blob. We are defensive: any shape that exposes `totalTokens` (or the
 * input/output pair) is accepted.
 */
function extractTokensFromEventData(data: string): { input: number; output: number; total: number } | null {
  const trimmed = data?.trim?.()
  if (!trimmed || (!trimmed.startsWith('{') && !trimmed.startsWith('['))) return null
  try {
    const parsed = JSON.parse(trimmed) as Record<string, unknown>
    const usage = (parsed.tokenUsage ?? parsed.usage ?? parsed.tokens ?? parsed.metadata) as
      | Record<string, unknown>
      | undefined
    if (!usage || typeof usage !== 'object') return null
    const input = Number(usage.promptTokens ?? usage.input ?? usage.inputTokens ?? 0)
    const output = Number(usage.completionTokens ?? usage.output ?? usage.outputTokens ?? 0)
    const total = Number(usage.totalTokens ?? usage.total ?? input + output)
    if (!Number.isFinite(total) || total <= 0) return null
    return {
      input: Number.isFinite(input) ? input : 0,
      output: Number.isFinite(output) ? output : 0,
      total,
    }
  } catch {
    return null
  }
}

export function ChatInspectorManager() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const [mode, setMode] = useState<ChatMode>(() => searchParams.get('mode') === 'stream' ? 'stream' : 'chat')
  const [message, setMessage] = useState('')
  const [model, setModel] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [personaId, setPersonaId] = useState('')
  const [promptTemplateId, setPromptTemplateId] = useState('')
  const [runtime, setRuntime] = useState<'langgraph' | 'langchain_agent'>('langgraph')
  const [graphProfile, setGraphProfile] = useState('')
  const [responseFormat, setResponseFormat] = useState<'TEXT' | 'JSON'>('TEXT')

  const [running, setRunning] = useState(false)
  const [error, setError] = useState<InspectorError | null>(null)
  const [result, setResult] = useState<ChatResponse | null>(null)
  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([])
  const [streamMessage, setStreamMessage] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  // Budget selector — seeded from DEFAULT_BUDGET but user-configurable.
  const [budget, setBudget] = useState<BudgetThreshold>(DEFAULT_BUDGET)

  // Keep one session ID for the full inspector session so repeated questions
  // can use the backend's exact-cache contract when it is available.
  const [sessionId] = useState(
    () => `inspector-${(crypto as Crypto & { randomUUID?: () => string }).randomUUID?.() ?? Date.now()}`
  )

  // Abort any in-flight stream when the component unmounts
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  const prefillKey = searchParams.toString()
  const prefill = parseChatInspectorPrefill(new URLSearchParams(prefillKey))

  useEffect(() => {
    if (!prefill) return

    setMode('chat')
    setMessage(prefill.message)
    if (prefill.model) {
      setModel(prefill.model)
    }
    setResponseFormat('TEXT')
    setResult(null)
    setStreamEvents([])
    setStreamMessage('')
    setError(null)

  }, [prefillKey])

  function buildChatRequest(): ChatRequest {
    const metadata: Record<string, unknown> = { channel: 'admin', sessionId }
    if (prefill?.metadata) {
      Object.assign(metadata, prefill.metadata)
    }

    return {
      message,
      model: model.trim() || undefined,
      systemPrompt: systemPrompt.trim() || undefined,
      personaId: personaId.trim() || undefined,
      promptTemplateId: promptTemplateId.trim() || undefined,
      runtime,
      graphProfile: graphProfile.trim() || undefined,
      metadata,
      responseFormat,
    }
  }

  function resolveRequestError(caught: unknown): InspectorError {
    const technicalMessage = redactEndpoint(
      getErrorMessage(caught),
      t('chatInspector.errors.endpointRedacted'),
    )
    if (/timed out|timeout/i.test(technicalMessage)) {
      return {
        primaryMessage: t('chatInspector.errors.requestTimeout'),
        technicalMessage,
      }
    }

    const resolved = resolveApiError(caught)
    if (resolved.raw?.status != null || /failed to fetch|networkerror|econn/i.test(technicalMessage)) {
      return {
        primaryMessage: resolved.message,
        technicalCode: resolved.raw?.code,
        technicalMessage,
      }
    }
    return {
      primaryMessage: t('chatInspector.errors.requestFailed'),
      technicalMessage,
    }
  }

  async function handleSendChat() {
    if (!message.trim()) {
      setError({ primaryMessage: t('chatInspector.errors.messageRequired') })
      return
    }

    setRunning(true)
    setError(null)
    setResult(null)
    try {
      const response = await chatApi.sendChat(buildChatRequest())
      setResult(response)
    } catch (e) {
      setError(resolveRequestError(e))
    } finally {
      setRunning(false)
    }
  }

  async function handleStreamChat() {
    if (!message.trim()) {
      setError({ primaryMessage: t('chatInspector.errors.messageRequired') })
      return
    }

    // Abort any previous in-flight stream
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setRunning(true)
    setError(null)
    setResult(null)
    setStreamMessage('')
    setStreamEvents([])

    try {
      await chatApi.streamChat(buildChatRequest(), (event) => {
        setStreamEvents(prev => [...prev, event].slice(-400))
        if (event.event === 'message') {
          setStreamMessage(prev => `${prev}${event.data}`)
        }
      }, controller.signal)
    } catch (e) {
      if (!isAbortError(e)) {
        setError(resolveRequestError(e))
      }
    } finally {
      setRunning(false)
    }
  }

  function handleRun() {
    if (mode === 'stream') {
      void handleStreamChat()
    } else {
      void handleSendChat()
    }
  }

  function handleModeChange(next: ChatMode) {
    setMode(next)
    const params = new URLSearchParams(searchParams)
    if (next === 'chat') params.delete('mode')
    else params.set('mode', next)
    setSearchParams(params, { replace: true })
  }

  function handleRestart() {
    setResult(null)
    setStreamMessage('')
    setStreamEvents([])
    setError(null)
    setMessage('')
  }

  const inspectorMetadata = getMetadata(result)

  // --- Pricing, cost per event, session tally ---
  const pricing = useModelPricing()
  const activeModelName = result?.model ?? (model.trim() || null)
  const activeModelPrice = pricing.getPrice(activeModelName)

  const eventTotals: SessionTotals[] = []
  if (inspectorMetadata?.tokenUsage) {
    const usage = inspectorMetadata.tokenUsage
    eventTotals.push({
      totalTokens: usage.totalTokens,
      estimatedCostUsd: calculateCost(
        { inputTokens: usage.promptTokens, outputTokens: usage.completionTokens },
        activeModelPrice,
      ),
    })
  }
  for (const evt of streamEvents) {
    const tokens = extractTokensFromEventData(evt.data)
    if (!tokens) continue
    eventTotals.push({
      totalTokens: tokens.total,
      estimatedCostUsd: calculateCost(
        { inputTokens: tokens.input, outputTokens: tokens.output },
        activeModelPrice,
      ),
    })
  }
  const sessionTotals: SessionTotals = eventTotals.reduce(
    (acc, e) => ({
      totalTokens: acc.totalTokens + e.totalTokens,
      estimatedCostUsd: acc.estimatedCostUsd + e.estimatedCostUsd,
    }),
    { totalTokens: 0, estimatedCostUsd: 0 },
  )
  const budgetExceeded = isBudgetExceeded(sessionTotals, budget)

  const rawResponseJson = result ? JSON.stringify(result, null, 2) : ''
  const rawResponseCollapsedByDefault = shouldCollapsePayload(rawResponseJson)
  const requestJson = JSON.stringify(buildChatRequest(), null, 2)
  const requestCollapsedByDefault = shouldCollapsePayload(requestJson)

  const hasResult = result != null || streamEvents.length > 0 || streamMessage.length > 0

  return (
    <div className="page chat-inspector-workspace">
      <PageHeader
        title={t('nav.chatInspector')}
        description={t('chatInspector.pageGuide')}
      />

      {prefill && <PrefillBanner prefill={prefill} />}

      {error && (
        <ErrorDisplay
          primaryMessage={error.primaryMessage}
          errorCode={error.technicalCode}
          errorMessage={error.technicalMessage}
        />
      )}

      {/* The operator's task comes first in reading and keyboard order. */}
      <div className="chat-inspector-workspace__layout">
        <section className="chat-inspector-workspace__run" aria-label={t('chatInspector.runWorkspace')}>
          <div className="chat-inspector-workspace__section-heading">
            <h2>{t('chatInspector.questionTitle')}</h2>
            <p>{t('chatInspector.questionDescription')}</p>
          </div>

          <MessageInputPanel
            mode={mode}
            message={message}
            running={running}
            hasResult={hasResult}
            onMessageChange={setMessage}
            onRun={handleRun}
            onRestart={handleRestart}
          />

          {!hasResult ? (
            <div className="chat-inspector-workspace__empty-response">
              <h2>{t('chatInspector.response')}</h2>
              <p>{t('chatInspector.noResponseYet')}</p>
            </div>
          ) : (
            <>
              {(result != null || streamEvents.length > 0) && (
                <SessionTotalPanel
                  sessionTotals={sessionTotals}
                  hasPrice={activeModelPrice != null}
                  budgetExceeded={budgetExceeded}
                />
              )}

              {result != null && (
                <ResponseDetailPanel
                  result={result}
                  metadata={inspectorMetadata}
                  activeModelPrice={activeModelPrice}
                  requestJson={requestJson}
                  requestCollapsedByDefault={requestCollapsedByDefault}
                  rawResponseJson={rawResponseJson}
                  rawResponseCollapsedByDefault={rawResponseCollapsedByDefault}
                />
              )}

              {(streamMessage.length > 0 || streamEvents.length > 0) && (
                <StreamOutputPanel
                  streamMessage={streamMessage}
                  streamEvents={streamEvents}
                />
              )}
            </>
          )}
        </section>

        <aside className="chat-inspector-workspace__config" aria-labelledby="chat-inspector-config-title">
          <div className="chat-inspector-workspace__section-heading">
            <h2 id="chat-inspector-config-title">{t('chatInspector.configuration')}</h2>
            <p>{t('chatInspector.configurationDescription')}</p>
          </div>
          <ConfigToolbar
            personaId={personaId}
            modelId={model}
            templateId={promptTemplateId}
            onPersonaChange={setPersonaId}
            onModelChange={setModel}
            onTemplateChange={setPromptTemplateId}
          />

          <ModePanel
            mode={mode}
            systemPrompt={systemPrompt}
            responseFormat={responseFormat}
            runtime={runtime}
            graphProfile={graphProfile}
            budget={budget}
            onModeChange={handleModeChange}
            onSystemPromptChange={setSystemPrompt}
            onResponseFormatChange={setResponseFormat}
            onRuntimeChange={setRuntime}
            onGraphProfileChange={setGraphProfile}
            onBudgetChange={setBudget}
          />
        </aside>
      </div>
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { Bot, UserRound, Wrench } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useRoleVisibility } from '../../workspace/RoleVisibilityProvider'
import { getErrorMessage, isAbortError } from '../../../shared/lib/getErrorMessage'
import { streamPersonaChat } from '../api'
import { getTemplate } from '../../prompts'
import type { PersonaResponse } from '../types'

interface Props {
  persona: PersonaResponse
  sessionId: string
}

interface ChatMessage {
  role: 'user' | 'assistant' | 'welcome'
  content: string
}

function buildResolvedPrompt(persona: PersonaResponse, templatePrompt?: string | null): string {
  const base = templatePrompt?.trim() || persona.systemPrompt
  const guideline = persona.responseGuideline?.trim()
  return guideline ? `${base}\n\n${guideline}` : base
}

export function PersonaPlayground({ persona, sessionId }: Props) {
  const { t } = useTranslation()
  const { effectiveRole } = useRoleVisibility()
  const isDeveloperMode = effectiveRole !== 'ADMIN_MANAGER'
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [activeTools, setActiveTools] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [linkedTemplatePrompt, setLinkedTemplatePrompt] = useState<string | null>(null)
  const [linkedTemplateName, setLinkedTemplateName] = useState<string | null>(null)

  const abortRef = useRef<AbortController | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Reset state when persona changes (sessionId changes)
  useEffect(() => {
    const initial: ChatMessage[] = []
    if (persona.welcomeMessage) {
      initial.push({ role: 'welcome', content: persona.welcomeMessage })
    }
    setMessages(initial)
    setInput('')
    setStreaming(false)
    setActiveTools([])
    setError(null)
    abortRef.current?.abort()
    abortRef.current = null
  }, [sessionId, persona.welcomeMessage])

  // Cleanup: abort any running stream on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (!persona.promptTemplateId) {
      setLinkedTemplatePrompt(null)
      setLinkedTemplateName(null)
      return
    }

    let active = true
    getTemplate(persona.promptTemplateId)
      .then(template => {
        if (!active) return
        setLinkedTemplateName(template.name)
        setLinkedTemplatePrompt(template.activeVersion?.content ?? null)
      })
      .catch(() => {
        if (!active) return
        setLinkedTemplateName(null)
        setLinkedTemplatePrompt(null)
      })

    return () => {
      active = false
    }
  }, [persona.promptTemplateId])

  const scrollToBottom = () => {
    if (typeof messagesEndRef.current?.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, activeTools])

  async function handleSend() {
    const text = input.trim()
    if (!text || streaming) return

    setInput('')
    setError(null)

    const userMsg: ChatMessage = { role: 'user', content: text }
    const assistantMsg: ChatMessage = { role: 'assistant', content: '' }

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setStreaming(true)
    setActiveTools([])

    const controller = new AbortController()
    abortRef.current = controller

    try {
      await streamPersonaChat(
        persona.id,
        text,
        sessionId,
        {
          onToken: (token) => {
            setMessages(prev => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              if (last.role === 'assistant') {
                updated[updated.length - 1] = { ...last, content: last.content + token }
              }
              return updated
            })
          },
          onToolStart: (name) => {
            setActiveTools(prev => [...prev, name])
          },
          onToolEnd: (name) => {
            setActiveTools(prev => prev.filter(t => t !== name))
          },
          onDone: () => {
            setStreaming(false)
            setActiveTools([])
          },
          onError: (err) => {
            setError(err.message)
            // Remove empty assistant placeholder on error
            setMessages(prev => {
              const last = prev[prev.length - 1]
              if (last?.role === 'assistant' && !last.content) {
                return prev.slice(0, -1)
              }
              return prev
            })
            setStreaming(false)
            setActiveTools([])
          },
        },
        controller.signal,
      )
    } catch (err) {
      if (!isAbortError(err)) {
        setError(getErrorMessage(err))
        // Remove empty assistant placeholder on error
        setMessages(prev => {
          const last = prev[prev.length - 1]
          if (last?.role === 'assistant' && !last.content) {
            return prev.slice(0, -1)
          }
          return prev
        })
      }
    } finally {
      setStreaming(false)
      setActiveTools([])
    }
  }

  function handleStop() {
    abortRef.current?.abort()
    abortRef.current = null
    setStreaming(false)
    setActiveTools([])
  }

  function handleClear() {
    abortRef.current?.abort()
    abortRef.current = null
    const initial: ChatMessage[] = []
    if (persona.welcomeMessage) {
      initial.push({ role: 'welcome', content: persona.welcomeMessage })
    }
    setMessages(initial)
    setInput('')
    setStreaming(false)
    setActiveTools([])
    setError(null)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const resolvedPrompt = buildResolvedPrompt(persona, linkedTemplatePrompt)
  const languageLabel = t('personas.langKo')

  return (
    <div className="persona-playground">
      <p className="detail-note" style={{ marginTop: 0, marginBottom: 'var(--space-2)' }}>
        {t('personas.playgroundLanguageHint', { language: languageLabel })}
      </p>
      {isDeveloperMode && (
        <details className="playground-system-preview">
          <summary>{t('personas.resolvedPrompt')}</summary>
          {linkedTemplateName && (
            <p className="detail-note">
              {t('personas.resolvedPromptLinkedTemplateHelp', { name: linkedTemplateName })}
            </p>
          )}
          <pre className="form-code-block">{resolvedPrompt}</pre>
        </details>
      )}

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">{t('personas.playgroundEmpty')}</div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`chat-bubble chat-bubble--${msg.role}`}>
            {msg.role === 'welcome' && (
              <div className="chat-bubble-label" aria-hidden="true"><Bot className="persona-playground__message-icon" /></div>
            )}
            {msg.role === 'assistant' && (
              <div className="chat-bubble-label" aria-hidden="true"><Bot className="persona-playground__message-icon" /></div>
            )}
            {msg.role === 'user' && (
              <div className="chat-bubble-label" aria-hidden="true"><UserRound className="persona-playground__message-icon" /></div>
            )}
            <div className="chat-bubble-content">
              {msg.content}
              {msg.role === 'assistant' && streaming && i === messages.length - 1 && (
                <span className="streaming-cursor">▋</span>
              )}
            </div>
          </div>
        ))}

        {activeTools.length > 0 && (
          <div className="chat-tools-indicator">
            <Wrench className="persona-playground__tool-icon" aria-hidden="true" />
            <span>{t('personas.playgroundToolsRunning', { count: activeTools.length })}</span>
            <details className="persona-technical-details persona-playground__tool-details">
              <summary>{t('personas.technicalToolDetails')}</summary>
              <code>{activeTools.join(', ')}</code>
            </details>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {error ? (
        <div className="persona-playground__error" role="alert">
          <span>{t('personas.playgroundError')}</span>
          <details className="persona-technical-details">
            <summary>{t('personas.technicalError')}</summary>
            <code>{error}</code>
          </details>
        </div>
      ) : null}

      <div className="chat-input-area">
        <textarea
          ref={textareaRef}
          className="chat-input"
          rows={2}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t('personas.playgroundPlaceholder')}
          disabled={streaming}
        />
        <div className="chat-input-actions">
          {!streaming ? (
            <button
              className="btn btn-primary btn-sm"
              onClick={handleSend}
              disabled={!input.trim()}
            >
              {t('personas.send')}
            </button>
          ) : (
            <button className="btn btn-danger btn-sm" onClick={handleStop}>
              {t('personas.stop')}
            </button>
          )}
          <button
            className="btn btn-secondary btn-sm"
            onClick={handleClear}
            disabled={messages.length === 0}
          >
            {t('personas.clear')}
          </button>
        </div>
      </div>
    </div>
  )
}

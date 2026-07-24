import { useTranslation } from 'react-i18next'
import { CollapsibleSection, HelpHint } from '../../../shared/ui'
import type { BudgetThreshold } from '../cost'

export type ChatMode = 'chat' | 'stream'

interface ModePanelProps {
  mode: ChatMode
  systemPrompt: string
  responseFormat: 'TEXT' | 'JSON'
  runtime: 'langgraph' | 'langchain_agent'
  graphProfile: string
  budget: BudgetThreshold
  onModeChange: (mode: ChatMode) => void
  onSystemPromptChange: (value: string) => void
  onResponseFormatChange: (value: 'TEXT' | 'JSON') => void
  onRuntimeChange: (value: 'langgraph' | 'langchain_agent') => void
  onGraphProfileChange: (value: string) => void
  onBudgetChange: (updater: (prev: BudgetThreshold) => BudgetThreshold) => void
}

/**
 * Context rail panel that hosts the chat / stream mode tabs and a collapsible
 * advanced section for the system prompt, response format, and budget.
 *
 * Pure presentation — all state lives in the parent ChatInspectorManager.
 */
export function ModePanel({
  mode,
  systemPrompt,
  responseFormat,
  runtime,
  graphProfile,
  budget,
  onModeChange,
  onSystemPromptChange,
  onResponseFormatChange,
  onRuntimeChange,
  onGraphProfileChange,
  onBudgetChange,
}: ModePanelProps) {
  const { t } = useTranslation()
  const modeDescription = mode === 'chat'
    ? t('chatInspector.modeDescription.chat')
    : t('chatInspector.modeDescription.stream')

  return (
    <section className="chat-inspector-mode-panel">
      <div className="detail-tabs" role="tablist" aria-label={t('chatInspector.modeTablistLabel')}>
        <button
          id="chat-inspector-mode-tab-chat"
          className={`tab-btn ${mode === 'chat' ? 'active' : ''}`}
          role="tab"
          type="button"
          aria-selected={mode === 'chat'}
          aria-controls="chat-inspector-mode-panel"
          onClick={() => onModeChange('chat')}
        >
          {t('chatInspector.modeChat')}
        </button>
        <button
          id="chat-inspector-mode-tab-stream"
          className={`tab-btn ${mode === 'stream' ? 'active' : ''}`}
          role="tab"
          type="button"
          aria-selected={mode === 'stream'}
          aria-controls="chat-inspector-mode-panel"
          onClick={() => onModeChange('stream')}
        >
          {t('chatInspector.modeStream')}
        </button>
      </div>
      <p
        id="chat-inspector-mode-panel"
        role="tabpanel"
        aria-labelledby={mode === 'chat' ? 'chat-inspector-mode-tab-chat' : 'chat-inspector-mode-tab-stream'}
        className="detail-note chat-inspector-mode-panel__description"
      >
        {modeDescription}
      </p>

      <CollapsibleSection title={t('chatInspector.advanced')} defaultOpen={false}>
        <div className="form-group chat-inspector-mode-panel__first-field">
          <div className="chat-inspector-field-label-row">
            <label htmlFor="chat-inspector-system-prompt">{t('chatInspector.systemPromptOptional')}</label>
            <HelpHint title={t('chatInspector.help.systemPromptTitle')} label={t('chatInspector.help.systemPrompt')} />
          </div>
          <textarea
            id="chat-inspector-system-prompt"
            rows={3}
            value={systemPrompt}
            onChange={e => onSystemPromptChange(e.target.value)}
          />
        </div>
        <div className="form-group">
          <label htmlFor="chat-inspector-response-format">{t('chatInspector.responseFormat')}</label>
          <select
            id="chat-inspector-response-format"
            value={responseFormat}
            onChange={e => onResponseFormatChange(e.target.value as 'TEXT' | 'JSON')}
          >
            <option value="TEXT">{t('chatInspector.responseFormats.text')}</option>
            <option value="JSON">{t('chatInspector.responseFormats.json')}</option>
          </select>
        </div>
        <div className="form-group">
          <div className="chat-inspector-field-label-row">
            <label htmlFor="chat-inspector-runtime">{t('chatInspector.runtime')}</label>
            <HelpHint title={t('chatInspector.help.runtimeTitle')} label={t('chatInspector.help.runtime')} />
          </div>
          <select
            id="chat-inspector-runtime"
            value={runtime}
            onChange={e => onRuntimeChange(e.target.value as 'langgraph' | 'langchain_agent')}
          >
            <option value="langgraph">{t('chatInspector.runtimes.langgraph')}</option>
            <option value="langchain_agent">{t('chatInspector.runtimes.langchainAgent')}</option>
          </select>
        </div>
        <div className="form-group">
          <div className="chat-inspector-field-label-row">
            <label htmlFor="chat-inspector-graph-profile">{t('chatInspector.graphProfile')}</label>
            <HelpHint title={t('chatInspector.help.graphProfileTitle')} label={t('chatInspector.help.graphProfile')} />
          </div>
          <input
            id="chat-inspector-graph-profile"
            value={graphProfile}
            onChange={e => onGraphProfileChange(e.target.value)}
            placeholder={t('chatInspector.graphProfilePlaceholder')}
          />
        </div>
        <div className="form-group">
          <div className="chat-inspector-field-label-row">
            <label htmlFor="chat-inspector-budget-tokens">{t('chatInspectorPage.cost.budgetTokensLabel')}</label>
            <HelpHint title={t('chatInspector.help.tokenTitle')} label={t('chatInspector.help.token')} />
          </div>
          <input
            id="chat-inspector-budget-tokens"
            type="number"
            min={0}
            step={1000}
            value={budget.maxTokens}
            onChange={(e) =>
              onBudgetChange((prev) => ({ ...prev, maxTokens: Math.max(0, Number(e.target.value) || 0) }))
            }
          />
        </div>
        <div className="form-group">
          <label htmlFor="chat-inspector-budget-cost">
            {t('chatInspectorPage.cost.budgetCostLabel')}
          </label>
          <input
            id="chat-inspector-budget-cost"
            type="number"
            min={0}
            step={0.1}
            value={budget.maxCostUsd}
            onChange={(e) =>
              onBudgetChange((prev) => ({ ...prev, maxCostUsd: Math.max(0, Number(e.target.value) || 0) }))
            }
          />
        </div>
      </CollapsibleSection>
    </section>
  )
}

import { useTranslation } from 'react-i18next'
import { LoadingSpinner } from '../../../shared/ui'
import type { ChatMode } from './ModePanel'

interface MessageInputPanelProps {
  mode: ChatMode
  message: string
  running: boolean
  hasResult: boolean
  onMessageChange: (value: string) => void
  onRun: () => void
  onRestart: () => void
}

/**
 * Right-panel message composer + run controls. Shows the textarea, the
 * primary "Run" button (label switches between chat / stream), and a
 * "Restart" secondary action that becomes available once a result exists.
 */
export function MessageInputPanel({
  mode,
  message,
  running,
  hasResult,
  onMessageChange,
  onRun,
  onRestart,
}: MessageInputPanelProps) {
  const { t } = useTranslation()

  return (
    <section className="chat-inspector-message-panel">
      <div className="form-group">
        <label htmlFor="chat-inspector-message">{t('chatInspector.message')}</label>
        <textarea
          id="chat-inspector-message"
          rows={6}
          value={message}
          onChange={e => onMessageChange(e.target.value)}
          placeholder={t('chatInspector.messagePlaceholder')}
        />
      </div>

      <div className="detail-actions">
        {hasResult && (
          <button
            className="btn btn-secondary"
            type="button"
            onClick={onRestart}
            disabled={running}
          >
            {t('chatInspectorPage.steps.restart')}
          </button>
        )}
        <button className="btn btn-primary" onClick={onRun} disabled={running}>
          {running
            ? <LoadingSpinner size="sm" />
            : mode === 'stream'
              ? t('chatInspector.runStream')
              : t('chatInspector.runChat')
          }
        </button>
      </div>
    </section>
  )
}

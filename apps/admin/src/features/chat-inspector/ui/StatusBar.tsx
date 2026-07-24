import { useTranslation } from 'react-i18next'

interface StatusBarProps {
  success: boolean
  durationMs?: number | null
  totalTokens?: number | null
}

export function StatusBar({ success, durationMs, totalTokens }: StatusBarProps) {
  const { t } = useTranslation()

  return (
    <div className="chat-inspector-status" aria-live="polite">
      <span className={`chat-inspector-status__state ${success ? 'is-success' : 'is-error'}`}>
        {success ? t('chatInspector.response_meta.success') : t('chatInspector.response_meta.failed')}
      </span>
      {durationMs != null && (
        <span>
          {t('chatInspector.response_meta.duration', { ms: durationMs })}
        </span>
      )}
      {totalTokens != null && (
        <span>
          {t('chatInspector.response_meta.tokens', { count: new Intl.NumberFormat().format(totalTokens) as unknown as number })}
        </span>
      )}
    </div>
  )
}

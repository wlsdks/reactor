import { useTranslation } from 'react-i18next'

interface ErrorDisplayProps {
  primaryMessage?: string | null
  errorCode?: string | null
  errorMessage?: string | null
}

const ERROR_DESCRIPTION_KEY: Record<string, string> = {
  RATE_LIMITED: 'chatInspector.errors.rateLimited',
  TIMEOUT: 'chatInspector.errors.timeout',
  GUARD_BLOCKED: 'chatInspector.errors.guardBlocked',
  MODEL_ERROR: 'chatInspector.errors.modelError',
  TOOL_ERROR: 'chatInspector.errors.toolError',
}

export function ErrorDisplay({ primaryMessage, errorCode, errorMessage }: ErrorDisplayProps) {
  const { t } = useTranslation()
  if (!primaryMessage && !errorCode && !errorMessage) return null

  const description = primaryMessage
    ?? t(ERROR_DESCRIPTION_KEY[errorCode ?? ''] ?? 'chatInspector.errors.unknown')

  return (
    <div className="chat-inspector-response__failure">
      <div className="alert alert-error" role="alert">
        <strong>{t('chatInspector.errors.responseFailed')}</strong>
        <span>{description}</span>
      </div>
      {(errorCode || errorMessage) ? (
        <details className="chat-inspector-response__technical-error">
          <summary>{t('chatInspector.technicalDetails')}</summary>
          <dl>
            {errorCode ? <div><dt>{t('chatInspector.errors.technicalCode')}</dt><dd>{errorCode}</dd></div> : null}
            {errorMessage ? <div><dt>{t('chatInspector.errors.technicalDetail')}</dt><dd>{errorMessage}</dd></div> : null}
          </dl>
        </details>
      ) : null}
    </div>
  )
}

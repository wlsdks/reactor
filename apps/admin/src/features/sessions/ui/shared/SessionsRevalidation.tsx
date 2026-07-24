import { useTranslation } from 'react-i18next'

interface SessionsRevalidationProps {
  onRetry: () => void | Promise<unknown>
  isRetrying: boolean
}

export function SessionsRevalidation({ onRetry, isRetrying }: SessionsRevalidationProps) {
  const { t } = useTranslation()

  return (
    <div className="sessions-revalidation" role="status">
      <div>
        <strong>{t('conversations.revalidation.title')}</strong>
        <span>{t('conversations.revalidation.description')}</span>
      </div>
      <button className="btn btn-secondary btn-sm" type="button" onClick={() => void onRetry()} disabled={isRetrying}>
        {isRetrying ? t('common.loading') : t('common.retry')}
      </button>
    </div>
  )
}

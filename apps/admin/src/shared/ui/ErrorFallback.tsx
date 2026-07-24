import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'

interface ErrorFallbackProps {
  level: 'app' | 'route' | 'section'
  onReset?: () => void
}

/**
 * Brand-consistent error fallback rendered by `ErrorBoundary` /
 * `SectionErrorBoundary`.
 *
 * Design notes:
 * - Friendly Korean copy with `~해요` tone (BX audit P0-3 alignment)
 * - Inline panel chrome that integrates with surrounding layout — never a
 *   centered modal-style overlay
 * - Lucide `AlertTriangle` icon in muted/warn tones (no scary red)
 * - `role="alert"` + `aria-live="assertive"`; focus moves to retry button on
 *   mount so keyboard users hear the recovery action
 * - Recovery options: 재시도 (resets boundary) + 처음으로 (Link to root)
 */
export function ErrorFallback({ level, onReset }: ErrorFallbackProps) {
  const { t } = useTranslation()
  const retryRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    // Move focus to the primary recovery action on mount so screen readers
    // announce the alert and keyboard users can retry without searching.
    retryRef.current?.focus()
  }, [])

  const containerProps = {
    role: 'alert',
    'aria-live': 'assertive' as const,
  }

  if (level === 'section') {
    return (
      <div className="error-fallback-section" {...containerProps}>
        <AlertTriangle
          className="error-fallback-section-icon"
          size={20}
          aria-hidden="true"
        />
        <div className="error-fallback-section-body">
          <p className="error-fallback-section-title">
            {t('error.sectionCrashTitle')}
          </p>
          <p className="error-fallback-section-description">
            {t('error.sectionCrashDescription')}
          </p>
        </div>
        {onReset && (
          <button
            ref={retryRef}
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onReset}
          >
            {t('error.sectionRetry')}
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="error-fallback" {...containerProps}>
      <AlertTriangle
        className="error-fallback-icon"
        size={32}
        aria-hidden="true"
      />
      <h2 className="error-fallback-title">{t('error.crashTitle')}</h2>
      <p className="error-fallback-description">{t('error.crashDescription')}</p>
      <p className="error-fallback-hint">{t('error.reportHint')}</p>
      <div className="error-fallback-actions">
        {level === 'route' && onReset && (
          <button
            ref={retryRef}
            type="button"
            className="btn btn-primary btn-sm"
            onClick={onReset}
          >
            {t('error.tryAgain')}
          </button>
        )}
        {level === 'app' && (
          <button
            ref={retryRef}
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => window.location.reload()}
          >
            {t('error.reload')}
          </button>
        )}
        <Link to="/" className="btn btn-secondary btn-sm">
          {t('error.goHome')}
        </Link>
      </div>
    </div>
  )
}

import { useTranslation } from 'react-i18next'
import { HelpHint } from '../../../shared/ui'
import type { HttpCallResult } from '../types'

interface IntegrationTestResultProps {
  result: HttpCallResult
  title: string
}

function isSuccessful(result: HttpCallResult): boolean {
  return result.status >= 200 && result.status < 300
}

/**
 * A human-readable response boundary for manual integration tools. The primary
 * surface intentionally avoids raw HTTP/JSON vocabulary; operators see a plain
 * outcome first, while developers can expand the exact response when needed.
 */
export function IntegrationTestResult({ result, title }: IntegrationTestResultProps) {
  const { t } = useTranslation()
  const successful = isSuccessful(result)
  const summary = successful
    ? t('integrationsPage.toolResult.successDescription')
    : t('integrationsPage.toolResult.reviewDescription')

  return (
    <section
      className={`integration-tool-result integration-tool-result--${successful ? 'success' : 'attention'}`}
      aria-live="polite"
    >
      <div className="integration-tool-result__heading">
        <div>
          <p className="integration-tool-result__eyebrow">
            {successful ? t('integrationsPage.toolResult.successLabel') : t('integrationsPage.toolResult.reviewLabel')}
          </p>
          <h2>{title}</h2>
        </div>
        <HelpHint
          size="md"
          title={t('integrationsPage.toolResult.statusHelpTitle')}
          label={t('integrationsPage.toolResult.statusHelp')}
        />
      </div>
      <p>{summary}</p>
      <details className="integration-tool-result__technical">
        <summary>{t('integrationsPage.toolResult.technicalDetails')}</summary>
        <dl>
          <div>
            <dt>{t('integrationsPage.toolResult.responseStatus')}</dt>
            <dd>HTTP {result.status}</dd>
          </div>
        </dl>
        <pre className="code-block">{JSON.stringify(result.body, null, 2)}</pre>
      </details>
    </section>
  )
}

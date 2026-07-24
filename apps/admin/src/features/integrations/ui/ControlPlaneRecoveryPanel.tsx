import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { SkeletonCard } from '../../../shared/ui'
import type { ControlPlaneRecoverySummary } from '../controlPlaneRecovery'
import { describeManifestStatus, describeProbeHttp } from './probeDescribers'

interface ControlPlaneRecoveryPanelProps {
  loading: boolean
  recoverySummary: ControlPlaneRecoverySummary
}

const INITIAL_RECOVERY_ITEMS = 3

export function ControlPlaneRecoveryPanel({
  loading,
  recoverySummary,
}: ControlPlaneRecoveryPanelProps) {
  const { t } = useTranslation()
  const [showAll, setShowAll] = useState(false)
  const visibleItems = showAll
    ? recoverySummary.items
    : recoverySummary.items.slice(0, INITIAL_RECOVERY_ITEMS)
  const hasHiddenItems = recoverySummary.items.length > INITIAL_RECOVERY_ITEMS

  return (
    <section className="control-plane-recovery" aria-labelledby="control-plane-recovery-title">
      <div className="detail-section-header">
        <div>
          <h2 id="control-plane-recovery-title" className="section-title control-plane-recovery__title">{t('integrationsPage.recoveryTitle')}</h2>
        </div>
        {!loading && recoverySummary.attentionCount > 0 && (
          <span className="control-plane-recovery__state">
            <span aria-hidden="true" />
            {t('integrationsPage.recoveryAttentionCount', { count: recoverySummary.attentionCount })}
          </span>
        )}
      </div>
      <p className="detail-note">{t('integrationsPage.recoveryDescription')}</p>
      {loading ? (
        <SkeletonCard height={160} />
      ) : recoverySummary.attentionCount === 0 ? (
        <div className="control-plane-recovery__empty" role="status">
          <span className="control-plane-recovery__dot is-pass" aria-hidden="true" />
          <p>{t('integrationsPage.recoveryEmpty')}</p>
        </div>
      ) : (
        <>
          <div className="control-plane-recovery__list">
            {visibleItems.map((item) => (
              <article key={item.probe.id} className="control-plane-recovery__item">
                <div className="control-plane-recovery__item-main">
                  <span className={`control-plane-recovery__dot is-${item.status.toLowerCase()}`} aria-hidden="true" />
                  <div>
                    <strong>{t(`integrationsPage.probes.${item.probe.id}`)}</strong>
                    <p>{t(`integrationsPage.recoveryKinds.${item.kind}`)}</p>
                  </div>
                </div>
                <div className="control-plane-recovery__item-actions">
                  <Link className="btn btn-secondary btn-sm" to={item.route.path}>
                    {t('integrationsPage.openRecoveryConsole')}
                  </Link>
                </div>
                <details className="control-plane-recovery__technical">
                  <summary>{t('common.technicalDetails')}</summary>
                  <dl>
                    <div><dt>{t('integrationsPage.probeManifest')}</dt><dd>{describeManifestStatus(t, item.probe)}</dd></div>
                    <div><dt>{t('integrationsPage.status')}</dt><dd>{describeProbeHttp(t, item.probe)}</dd></div>
                    <div><dt>{t('integrationsPage.recoveryConsoleLabel')}</dt><dd>{t(item.route.labelKey)}</dd></div>
                    <div><dt>{t('integrationsPage.endpoint')}</dt><dd><code>{item.probe.path}</code></dd></div>
                  </dl>
                  {item.probe.detail ? <p>{item.probe.detail}</p> : null}
                  <ul>
                    {item.stepIds.map((stepId) => <li key={`${item.probe.id}-${stepId}`}>{t(`integrationsPage.recoverySteps.${stepId}`)}</li>)}
                  </ul>
                </details>
              </article>
            ))}
          </div>

          {hasHiddenItems && (
            <button
              className="btn btn-secondary btn-sm control-plane-recovery__toggle"
              type="button"
              onClick={() => setShowAll((current) => !current)}
            >
              {showAll
                ? t('integrationsPage.recoveryShowLess')
                : t('integrationsPage.recoveryShowAll')}
            </button>
          )}

          <details className="control-plane-recovery__runbook">
            <summary>{t('integrationsPage.recoveryRunbookTitle')}</summary>
            <p>{t('integrationsPage.recoveryRunbookDescription')}</p>
            <div>
              <section>
                <strong>{t('integrationsPage.recoveryRunbook.checkManifestTitle')}</strong>
                <p>{t('integrationsPage.recoveryRunbook.checkManifestBody')}</p>
              </section>
              <section>
                <strong>{t('integrationsPage.recoveryRunbook.probeDirectTitle')}</strong>
                <p>{t('integrationsPage.recoveryRunbook.probeDirectBody')}</p>
              </section>
              <section>
                <strong>{t('integrationsPage.recoveryRunbook.reopenConsoleTitle')}</strong>
                <p>{t('integrationsPage.recoveryRunbook.reopenConsoleBody')}</p>
              </section>
            </div>
          </details>
        </>
      )}
    </section>
  )
}

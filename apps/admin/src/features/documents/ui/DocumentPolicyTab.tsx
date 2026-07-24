import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DetailSkeleton, EmptyState, LoadingSpinner, ToggleSwitch } from '../../../shared/ui'
import { formatDateTime } from '../../../shared/lib/formatters'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import type { RagIngestionPolicyState } from '../types'

export interface RagPolicyFormState {
  enabled: boolean
  requireReview: boolean
  allowedChannelsRaw: string
  minQueryChars: string
  minResponseChars: string
  blockedPatternsRaw: string
}

const emptyPolicyForm: RagPolicyFormState = {
  enabled: false,
  requireReview: true,
  allowedChannelsRaw: '',
  minQueryChars: '10',
  minResponseChars: '20',
  blockedPatternsRaw: '',
}

function toPolicyForm(state: RagIngestionPolicyState): RagPolicyFormState {
  const policy = state.stored ?? state.effective
  return {
    enabled: policy.enabled,
    requireReview: policy.requireReview,
    allowedChannelsRaw: policy.allowedChannels.join(', '),
    minQueryChars: String(policy.minQueryChars),
    minResponseChars: String(policy.minResponseChars),
    blockedPatternsRaw: policy.blockedPatterns.join(', '),
  }
}

interface DocumentPolicyTabProps {
  policyState: RagIngestionPolicyState | null
  loadingPolicy: boolean
  policyError: unknown
  onReloadPolicy: () => void
  onSavePolicy: (form: RagPolicyFormState) => Promise<void>
  onResetPolicy: () => Promise<void>
  onDirtyChange: (dirty: boolean) => void
}

export function DocumentPolicyTab({
  policyState,
  loadingPolicy,
  policyError,
  onReloadPolicy,
  onSavePolicy,
  onResetPolicy,
  onDirtyChange,
}: DocumentPolicyTabProps) {
  const { t } = useTranslation()
  const [policyForm, setPolicyForm] = useState<RagPolicyFormState>(emptyPolicyForm)
  const [initialPolicyForm, setInitialPolicyForm] = useState<RagPolicyFormState>(emptyPolicyForm)
  const [policyUnavailable, setPolicyUnavailable] = useState(false)
  const [savingPolicy, setSavingPolicy] = useState(false)
  const [lastPolicyInitKey, setLastPolicyInitKey] = useState<string | null>(null)

  useEffect(() => {
    if (policyState === null) {
      if (!policyUnavailable) {
        const policyMessage = policyError ? getErrorMessage(policyError) : null
        if (!policyMessage) setPolicyUnavailable(true)
      }
      return
    }
    const stateKey = JSON.stringify((policyState.stored ?? policyState.effective).updatedAt)
    if (lastPolicyInitKey === stateKey) return
    const loaded = toPolicyForm(policyState)
    setLastPolicyInitKey(stateKey)
    setPolicyForm(loaded)
    setInitialPolicyForm(loaded)
    setPolicyUnavailable(false)
  }, [lastPolicyInitKey, policyError, policyState, policyUnavailable])

  const policyDirty = !policyUnavailable
    && !loadingPolicy
    && JSON.stringify(policyForm) !== JSON.stringify(initialPolicyForm)

  useEffect(() => {
    onDirtyChange(policyDirty)
  }, [onDirtyChange, policyDirty])

  async function handleSavePolicy() {
    setSavingPolicy(true)
    try {
      await onSavePolicy(policyForm)
      setInitialPolicyForm(policyForm)
    } finally {
      setSavingPolicy(false)
    }
  }

  async function handleResetPolicy() {
    setSavingPolicy(true)
    try {
      await onResetPolicy()
      setLastPolicyInitKey(null)
    } finally {
      setSavingPolicy(false)
    }
  }

  const appliedPolicy = policyState?.stored ?? policyState?.effective

  return (
    <div className="document-policy-workspace">
      <header className="document-policy-header">
        <div>
          <h2>{t('documentsPage.policy.title')}</h2>
          <p>{t('documentsPage.policy.description')}</p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={onReloadPolicy} disabled={loadingPolicy}>
          {loadingPolicy ? <LoadingSpinner size="sm" /> : t('documentsPage.policy.reloadAction')}
        </button>
      </header>

      {policyUnavailable ? (
        <EmptyState
          message={t('documentsPage.policy.unavailableTitle')}
          description={t('documentsPage.policy.unavailableDescription')}
          actionLabel={t('documentsPage.policy.reloadAction')}
          onAction={onReloadPolicy}
        />
      ) : loadingPolicy ? (
        <div className="document-policy-loading"><DetailSkeleton /></div>
      ) : (
        <section className="document-policy-surface" aria-labelledby="document-policy-form-title">
          <div className="document-policy-surface__heading">
            <div>
              <h3 id="document-policy-form-title">{t('documentsPage.policy.formTitle')}</h3>
              <p>{t('documentsPage.policy.formDescription')}</p>
            </div>
            {appliedPolicy && (
              <span>{t('documentsPage.policy.updated', { value: formatDateTime(appliedPolicy.updatedAt) })}</span>
            )}
          </div>

          <div className="document-policy-toggle-list">
            <div className="document-policy-toggle-row">
              <div>
                <strong>{t('documentsPage.policy.collectEnabled')}</strong>
                <p>{t('documentsPage.policy.collectEnabledDescription')}</p>
              </div>
              <ToggleSwitch
                checked={policyForm.enabled}
                onChange={(checked) => setPolicyForm((current) => ({ ...current, enabled: checked }))}
                label={t('documentsPage.policy.collectEnabled')}
              />
            </div>
            <div className="document-policy-toggle-row">
              <div>
                <strong>{t('documentsPage.policy.reviewRequired')}</strong>
                <p>{t('documentsPage.policy.reviewRequiredDescription')}</p>
              </div>
              <ToggleSwitch
                checked={policyForm.requireReview}
                onChange={(checked) => setPolicyForm((current) => ({ ...current, requireReview: checked }))}
                label={t('documentsPage.policy.reviewRequired')}
              />
            </div>
          </div>

          <div className="document-policy-fields">
            <label htmlFor="policy-allowed-channels">
              <span>{t('documentsPage.policy.allowedSources')}</span>
              <small>{t('documentsPage.policy.allowedSourcesDescription')}</small>
              <input
                id="policy-allowed-channels"
                value={policyForm.allowedChannelsRaw}
                onChange={(event) => setPolicyForm((current) => ({ ...current, allowedChannelsRaw: event.target.value }))}
                placeholder={t('documentsPage.allowedChannelsPlaceholder')}
              />
            </label>

            <div className="document-policy-fields__pair">
              <label htmlFor="policy-min-query">
                <span>{t('documentsPage.policy.minimumQuestion')}</span>
                <small>{t('documentsPage.policy.minimumQuestionDescription')}</small>
                <input
                  id="policy-min-query"
                  type="number"
                  min={1}
                  value={policyForm.minQueryChars}
                  onChange={(event) => setPolicyForm((current) => ({ ...current, minQueryChars: event.target.value }))}
                />
              </label>
              <label htmlFor="policy-min-response">
                <span>{t('documentsPage.policy.minimumAnswer')}</span>
                <small>{t('documentsPage.policy.minimumAnswerDescription')}</small>
                <input
                  id="policy-min-response"
                  type="number"
                  min={1}
                  value={policyForm.minResponseChars}
                  onChange={(event) => setPolicyForm((current) => ({ ...current, minResponseChars: event.target.value }))}
                />
              </label>
            </div>

            <label htmlFor="policy-blocked-patterns">
              <span>{t('documentsPage.policy.excludedPhrases')}</span>
              <small>{t('documentsPage.policy.excludedPhrasesDescription')}</small>
              <input
                id="policy-blocked-patterns"
                value={policyForm.blockedPatternsRaw}
                onChange={(event) => setPolicyForm((current) => ({ ...current, blockedPatternsRaw: event.target.value }))}
              />
            </label>
          </div>

          <div className="document-policy-actions">
            {policyDirty && <span role="status">{t('documentsPage.policy.unsaved')}</span>}
            <button type="button" className="btn btn-primary" onClick={() => void handleSavePolicy()} disabled={savingPolicy || !policyDirty}>
              {savingPolicy ? <LoadingSpinner size="sm" /> : t('documentsPage.policy.saveAction')}
            </button>
          </div>

          <details className="document-policy-maintenance">
            <summary>{t('documentsPage.policy.maintenanceTitle')}</summary>
            <p>{t('documentsPage.policy.maintenanceDescription')}</p>
            <button type="button" className="btn btn-secondary" onClick={() => void handleResetPolicy()} disabled={savingPolicy}>
              {t('documentsPage.policy.resetAction')}
            </button>
          </details>

          {policyState && (
            <details className="document-policy-technical">
              <summary>{t('common.technicalDetails')}</summary>
              <dl>
                <div><dt>{t('documentsPage.configEnabled')}</dt><dd>{policyState.configEnabled ? t('common.yes') : t('common.no')}</dd></div>
                <div><dt>{t('documentsPage.dynamicEnabled')}</dt><dd>{policyState.dynamicEnabled ? t('common.yes') : t('common.no')}</dd></div>
                <div><dt>{t('documentsPage.usingStoredPolicy')}</dt><dd>{policyState.stored ? t('common.yes') : t('common.no')}</dd></div>
              </dl>
            </details>
          )}
        </section>
      )}
    </div>
  )
}

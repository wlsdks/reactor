import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ConfirmDialog, EmptyState, HelpHint, LoadingSpinner, PageHeader, RefreshButton, SkeletonCard, WorkspaceUnavailable } from '../../../shared/ui'
import { useUnsavedChanges, getErrorMessage, isForbiddenError, formatDateTimeCompact } from '../../../shared/lib'
import { useToastStore } from '../../../shared/store/toast.store'
import { queryKeys } from '../../../shared/lib/queryKeys'
import * as toolPolicyApi from '../api'
import { classifyLoadIssue } from '../../../shared/lib/ops'
import { summarizeToolPolicyOps } from '../toolPolicyOps'
import type { ToolPolicyRuleSet } from '../types'

interface PolicyForm {
  enabled: boolean
  writeToolNames: string
  denyWriteChannels: string
  allowWriteToolNamesInDenyChannels: string
  allowWriteToolNamesByChannel: string
  denyWriteMessage: string
}

function listToText(items: string[]): string {
  return items.join(', ')
}

function textToList(text: string): string[] {
  return text
    .split(/[\n,]/g)
    .map((item) => item.trim())
    .filter(Boolean)
}

function ruleSetToForm(ruleSet: ToolPolicyRuleSet): PolicyForm {
  return {
    enabled: ruleSet.enabled,
    writeToolNames: listToText(ruleSet.writeToolNames),
    denyWriteChannels: listToText(ruleSet.denyWriteChannels),
    allowWriteToolNamesInDenyChannels: listToText(ruleSet.allowWriteToolNamesInDenyChannels),
    allowWriteToolNamesByChannel: JSON.stringify(ruleSet.allowWriteToolNamesByChannel, null, 2),
    denyWriteMessage: ruleSet.denyWriteMessage,
  }
}

function policyStatusLabel(status: string, t: (key: string) => string): string {
  const normalized = status.toUpperCase()
  if (normalized === 'PASS' || normalized === 'OK') return t('safetyRules.statusReady')
  if (normalized === 'WARN' || normalized === 'WARNING') return t('safetyRules.statusAttention')
  if (normalized === 'FAIL' || normalized === 'ERROR' || normalized === 'BLOCKED') return t('safetyRules.statusBlocked')
  return t('safetyRules.statusUnknown')
}

function policyStatusTone(status: string): 'ready' | 'attention' | 'danger' | 'muted' {
  const normalized = status.toUpperCase()
  if (normalized === 'PASS' || normalized === 'OK') return 'ready'
  if (normalized === 'WARN' || normalized === 'WARNING') return 'attention'
  if (normalized === 'FAIL' || normalized === 'ERROR' || normalized === 'BLOCKED') return 'danger'
  return 'muted'
}

export function ToolPolicyManager({ embedded = false }: { embedded?: boolean } = {}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<PolicyForm | null>(null)
  const [initialForm, setInitialForm] = useState<PolicyForm | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [technicalActionError, setTechnicalActionError] = useState<string | null>(null)
  const [showResetConfirm, setShowResetConfirm] = useState(false)

  const { data: state = null, isLoading, error, dataUpdatedAt } = useQuery({
    queryKey: queryKeys.toolPolicy.list(),
    queryFn: toolPolicyApi.getPolicy,
  })

  const lastLoadedAt = dataUpdatedAt > 0 ? dataUpdatedAt : null
  const loadFailure = error ? getErrorMessage(error) : null

  // Sync form when server state first arrives or is refreshed
  useEffect(() => {
    if (state && !form) {
      const loaded = ruleSetToForm(state.stored ?? state.effective)
      setForm(loaded)
      setInitialForm(loaded)
    }
  }, [state, form])

  const saveMutation = useMutation({
    mutationFn: toolPolicyApi.updatePolicy,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.toolPolicy.all() })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
      setActionError(null)
      setTechnicalActionError(null)
      // Reset dirty tracking after successful save
      if (form) setInitialForm(form)
    },
    onError: (err: Error) => {
      setActionError(t('toolPolicyPage.saveFailed'))
      setTechnicalActionError(getErrorMessage(err))
    },
  })

  const resetMutation = useMutation({
    mutationFn: toolPolicyApi.deletePolicy,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.toolPolicy.all() })
      setForm(null)
      setInitialForm(null)
      setActionError(null)
      setTechnicalActionError(null)
    },
    onError: (err: Error) => {
      setActionError(t('toolPolicyPage.resetFailed'))
      setTechnicalActionError(getErrorMessage(err))
    },
  })

  const saving = saveMutation.isPending || resetMutation.isPending
  const isDirty = form != null && initialForm != null && JSON.stringify(form) !== JSON.stringify(initialForm)
  const blocker = useUnsavedChanges(isDirty)

  function handleSave() {
    if (!form) return

    setActionError(null)
    setTechnicalActionError(null)

    let allowByChannel: Record<string, string[]>
    try {
      const parsed = JSON.parse(form.allowWriteToolNamesByChannel) as unknown
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error(t('toolPolicyPage.validation.allowByChannelObject'))
      }

      allowByChannel = Object.entries(parsed as Record<string, unknown>).reduce<Record<string, string[]>>((acc, [key, value]) => {
        if (!key.trim()) return acc
        if (Array.isArray(value)) {
          acc[key.trim()] = value.map((item) => String(item).trim()).filter(Boolean)
          return acc
        }
        if (typeof value === 'string') {
          acc[key.trim()] = textToList(value)
          return acc
        }
        throw new Error(t('toolPolicyPage.validation.invalidChannelValue'))
      }, {})
    } catch (e) {
      setActionError(getErrorMessage(e))
      setTechnicalActionError(null)
      return
    }

    saveMutation.mutate({
      enabled: form.enabled,
      writeToolNames: textToList(form.writeToolNames),
      denyWriteChannels: textToList(form.denyWriteChannels),
      allowWriteToolNamesInDenyChannels: textToList(form.allowWriteToolNamesInDenyChannels),
      allowWriteToolNamesByChannel: allowByChannel,
      denyWriteMessage: form.denyWriteMessage,
    })
  }

  const opsSummary = summarizeToolPolicyOps(state, loadFailure)
  const loadIssue = classifyLoadIssue(loadFailure)
  const canEdit = form != null && state != null
  const hasStaleSnapshot = loadFailure != null && state != null

  function refreshToolPolicy() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.toolPolicy.all() })
  }

  const policyActions = (
    <>
      <RefreshButton
        onRefresh={refreshToolPolicy}
        isFetching={isLoading || saving}
      />
      {canEdit && (
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? <LoadingSpinner size="sm" /> : t('common.save')}
        </button>
      )}
    </>
  )

  if (isLoading && !state && !form) {
    return (
      <div className={embedded ? 'safety-workspace__section' : 'page'}>
        {!embedded && <PageHeader title={t('nav.toolPolicy')} updateDocumentTitle />}
        <div className="safety-policy-loading">
          <SkeletonCard height={172} />
          <SkeletonCard height={320} />
        </div>
      </div>
    )
  }

  if (loadFailure && !state && !form) {
    const forbidden = isForbiddenError(error)
    return (
      <div className={embedded ? 'safety-workspace__section' : 'page'}>
        {!embedded && <PageHeader title={t('nav.toolPolicy')} updateDocumentTitle />}
        <WorkspaceUnavailable
          title={t(forbidden ? 'toolPolicyPage.accessDeniedTitle' : 'toolPolicyPage.unavailableTitle')}
          description={t(forbidden ? 'toolPolicyPage.accessDeniedDescription' : 'toolPolicyPage.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={refreshToolPolicy}
          isRetrying={isLoading}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{
            title: t('toolPolicyPage.recoveryTitle'),
            steps: [t('toolPolicyPage.recoveryAccount'), t('toolPolicyPage.recoveryConnection')],
            technicalLabel: t('common.technicalDetails'),
            technicalDetail: loadFailure,
          }}
        />
      </div>
    )
  }

  return (
    <div className={embedded ? 'safety-workspace__section' : 'page'}>
      {embedded ? (
        <div className="safety-workspace__toolbar">
          <span className="safety-workspace__sync-note">
            {lastLoadedAt
              ? t('toolPolicyPage.lastSync', { time: formatDateTimeCompact(lastLoadedAt) })
              : t('toolPolicyPage.lastSyncUnknown')}
          </span>
          <div className="safety-workspace__toolbar-actions">{policyActions}</div>
        </div>
      ) : (
        <PageHeader
          title={t('nav.toolPolicy')}
          updateDocumentTitle
          description={
            <>
              <p className="page-subtitle">{t('nav.help.toolPolicy')}</p>
              <p className="detail-note">
                {lastLoadedAt
                  ? t('toolPolicyPage.lastSync', { time: formatDateTimeCompact(lastLoadedAt) })
                  : t('toolPolicyPage.lastSyncUnknown')}
              </p>
            </>
          }
          actions={policyActions}
        />
      )}

      {hasStaleSnapshot && (
        <div className="safety-workspace__sync-note safety-tool-policy__sync-note" role="status">
          <span>{t('toolPolicyPage.refreshFailed')}</span>
          <button className="btn btn-sm btn-secondary" onClick={refreshToolPolicy}>
            {t('common.retry')}
          </button>
          <details>
            <summary>{t('common.technicalDetails')}</summary>
            <code>{loadFailure}</code>
          </details>
        </div>
      )}
      {actionError && (
        <div id="tool-policy-action-error" className="safety-tool-policy__action-error" role="alert">
          <span>{actionError}</span>
          {technicalActionError ? (
            <details>
              <summary>{t('common.technicalDetails')}</summary>
              <code>{technicalActionError}</code>
            </details>
          ) : null}
        </div>
      )}

      <section className="safety-policy-overview" aria-labelledby="tool-policy-overview-title">
        <div className="safety-policy-overview__head">
          <div>
            <h2 id="tool-policy-overview-title">{t('toolPolicyPage.opsTitle')}</h2>
            <p>{t('toolPolicyPage.opsDescription')}</p>
          </div>
          <span className={`safety-policy-state is-${policyStatusTone(opsSummary.status)}`}>
            <span aria-hidden="true" />
            {policyStatusLabel(opsSummary.status, t)}
          </span>
        </div>
        {opsSummary.hasPolicy ? (
          <dl>
            <div><dt>{t('toolPolicyPage.activeWriteToolsCard')}</dt><dd>{opsSummary.activeWriteTools}</dd></div>
            <div><dt>{t('toolPolicyPage.denyChannelsCard')}</dt><dd>{opsSummary.denyChannels}</dd></div>
            <div><dt>{t('toolPolicyPage.allowOverridesCard')}</dt><dd>{opsSummary.allowOverrides}</dd></div>
            <div><dt>{t('toolPolicyPage.diffFieldsCard')}</dt><dd>{opsSummary.diffFields.length}</dd></div>
          </dl>
        ) : (
          <div className="safety-policy-overview__empty">
            <EmptyState
              message={t(`toolPolicyPage.empty.${loadIssue ?? 'unknown'}`)}
              description={t('toolPolicyPage.emptyDescription')}
              actionLabel={t('common.refresh')}
              onAction={refreshToolPolicy}
            />
          </div>
        )}
      </section>

      {canEdit && state && form && (
        <section className="safety-tool-policy" aria-labelledby="tool-policy-editor-title">
          <div className="safety-tool-policy__editor-head">
            <div>
              <h2 id="tool-policy-editor-title">{t('toolPolicyPage.editorTitle')}</h2>
              <p>{t('toolPolicyPage.editorDescription')}</p>
            </div>
          </div>

          <div className="safety-tool-policy__fields">
            <div className="form-group form-check">
                <input
                  id="policy-enabled"
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(e) => setForm((prev) => prev ? { ...prev, enabled: e.target.checked } : prev)}
                />
                <label htmlFor="policy-enabled">{t('toolPolicyPage.enabled')}</label>
            </div>

            <div className="form-group">
              <div className="form-label-row">
                <label className="form-label" htmlFor="policy-write-tools">{t('toolPolicyPage.writeToolNames')}</label>
                <HelpHint title={t('toolPolicyPage.writeToolNames')} label={t('toolPolicyPage.help.writeToolNames')} />
              </div>
                <textarea
                  id="policy-write-tools"
                  rows={3}
                  value={form.writeToolNames}
                  aria-invalid={false}
                  onChange={(e) => setForm((prev) => prev ? { ...prev, writeToolNames: e.target.value } : prev)}
                />
            </div>

            <div className="form-group">
              <div className="form-label-row">
                <label className="form-label" htmlFor="policy-deny-channels">{t('toolPolicyPage.denyWriteChannels')}</label>
                <HelpHint title={t('toolPolicyPage.denyWriteChannels')} label={t('toolPolicyPage.help.denyWriteChannels')} />
              </div>
                <textarea
                  id="policy-deny-channels"
                  rows={2}
                  value={form.denyWriteChannels}
                  aria-invalid={false}
                  onChange={(e) => setForm((prev) => prev ? { ...prev, denyWriteChannels: e.target.value } : prev)}
                />
            </div>

            <div className="form-group">
              <div className="form-label-row">
                <label className="form-label" htmlFor="policy-allow-deny-channels">{t('toolPolicyPage.allowWriteToolsInDenyChannels')}</label>
                <HelpHint title={t('toolPolicyPage.allowWriteToolsInDenyChannels')} label={t('toolPolicyPage.help.allowWriteToolsInDenyChannels')} />
              </div>
                <textarea
                  id="policy-allow-deny-channels"
                  rows={2}
                  value={form.allowWriteToolNamesInDenyChannels}
                  aria-invalid={false}
                  onChange={(e) => setForm((prev) => prev ? { ...prev, allowWriteToolNamesInDenyChannels: e.target.value } : prev)}
                />
            </div>

            <div className="form-group">
              <div className="form-label-row">
                <label className="form-label" htmlFor="policy-deny-message">{t('toolPolicyPage.denyMessage')}</label>
                <HelpHint title={t('toolPolicyPage.denyMessage')} label={t('toolPolicyPage.help.denyMessage')} />
              </div>
              <input
                id="policy-deny-message"
                value={form.denyWriteMessage}
                aria-invalid={false}
                onChange={(e) => setForm((prev) => prev ? { ...prev, denyWriteMessage: e.target.value } : prev)}
              />
            </div>
          </div>

          <details className="safety-tool-policy__advanced">
            <summary>{t('toolPolicyPage.advancedRules')}</summary>
            <p>{t('toolPolicyPage.advancedRulesDescription')}</p>
            <div className="form-group">
              <div className="form-label-row">
                <label className="form-label" htmlFor="policy-allow-by-channel">
                  {t('toolPolicyPage.allowWriteToolsByChannel')}
                  <span className="form-label-required" aria-hidden="true">*</span>
                </label>
                <HelpHint title={t('toolPolicyPage.allowWriteToolsByChannel')} label={t('toolPolicyPage.help.allowWriteToolsByChannel')} />
              </div>
              <textarea
                id="policy-allow-by-channel"
                rows={6}
                value={form.allowWriteToolNamesByChannel}
                aria-required="true"
                aria-invalid={!!actionError}
                aria-describedby={actionError ? 'tool-policy-action-error' : undefined}
                onChange={(e) => setForm((prev) => prev ? { ...prev, allowWriteToolNamesByChannel: e.target.value } : prev)}
              />
            </div>
          </details>

          <details className="safety-tool-policy__technical">
            <summary>{t('toolPolicyPage.technicalDetails')}</summary>
            <div className="safety-tool-policy__technical-content">
              <p>{t('toolPolicyPage.technicalDescription')}</p>
              <dl>
                <div><dt>{t('toolPolicyPage.configEnabled')}</dt><dd>{state.configEnabled ? t('common.yes') : t('common.no')}</dd></div>
                <div><dt>{t('toolPolicyPage.dynamicEnabled')}</dt><dd>{state.dynamicEnabled ? t('common.yes') : t('common.no')}</dd></div>
                <div><dt>{t('toolPolicyPage.storedPolicy')}</dt><dd>{state.stored ? t('common.yes') : t('common.no')}</dd></div>
              </dl>

              <section className="safety-tool-policy__diff" aria-labelledby="tool-policy-diff-title">
                <h3 id="tool-policy-diff-title">{t('toolPolicyPage.configDiff')}</h3>
                <p>{t('toolPolicyPage.diffDescription')}</p>
                {opsSummary.diffFields.length === 0 ? (
                  <p>{t('toolPolicyPage.signalDetails.driftNone')}</p>
                ) : (
                  opsSummary.diffs
                    .filter((diff) => diff.changed)
                    .map((diff) => (
                      <div key={diff.id}>
                        <h4>{t(`toolPolicyPage.diffFields.${diff.id}`)}</h4>
                        <dl>
                          <div><dt>{t('toolPolicyPage.storedPolicyTitle')}</dt><dd><pre className="code-block">{diff.stored}</pre></dd></div>
                          <div><dt>{t('toolPolicyPage.effectivePolicyTitle')}</dt><dd><pre className="code-block">{diff.effective}</pre></dd></div>
                        </dl>
                      </div>
                    ))
                )}
              </section>

              <section className="safety-tool-policy__raw-values" aria-label={t('toolPolicyPage.technicalDetails')}>
                <h3>{t('toolPolicyPage.effectiveRaw')}</h3>
                <pre className="code-block">{JSON.stringify(state.effective, null, 2)}</pre>
                <h3>{t('toolPolicyPage.storedRaw')}</h3>
                <pre className="code-block">{JSON.stringify(state.stored, null, 2)}</pre>
              </section>
            </div>
          </details>

          <details className="safety-tool-policy__maintenance">
            <summary>{t('toolPolicyPage.maintenance')}</summary>
            <p>{t('toolPolicyPage.maintenanceDescription')}</p>
            <button className="btn btn-danger" onClick={() => setShowResetConfirm(true)} disabled={saving}>
              {t('toolPolicyPage.resetStoredPolicy')}
            </button>
          </details>
        </section>
      )}

      {showResetConfirm && (
        <ConfirmDialog
          title={t('toolPolicyPage.resetStoredPolicy')}
          message={t('toolPolicyPage.resetConfirmMessage')}
          onConfirm={() => {
            setShowResetConfirm(false)
            resetMutation.mutate()
          }}
          onCancel={() => setShowResetConfirm(false)}
          danger
        />
      )}

      {blocker.state === 'blocked' && (
        <ConfirmDialog
          title={t('common.unsavedChanges')}
          message={t('common.unsavedChangesMessage')}
          onConfirm={() => blocker.proceed()}
          onCancel={() => blocker.reset()}
          danger
        />
      )}
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { CollapsibleSection, ConfirmDialog, DataTable, EmptyState, LoadingSpinner, PageHeader, RefreshButton, TableSkeleton, WorkspaceUnavailable, useAnnouncer } from '../../../shared/ui'
import { useEscapeKey, getErrorMessage } from '../../../shared/lib'
import { scheduleUndoableDelete } from '../../../shared/lib/scheduleUndoableDelete'
import { showApiErrorToast } from '../../../shared/lib/showApiErrorToast'
import { formatDateTime } from '../../../shared/lib/formatters'
import { queryKeys } from '../../../shared/lib/queryKeys'
import * as outputGuardApi from '../api'
import type { OutputGuardRule, SimulateOutputGuardResponse } from '../types'
import {
  getRegexIssue,
  summarizeOutputGuardOps,
  summarizeSimulation,
} from '../outputGuardOps'
import { OutputGuardRuleModal } from './OutputGuardRuleModal'

/**
 * Maps the raw response-filter action enum (REJECT / MASK / BLOCK / REDACT /
 * ALLOW) to a Korean operator label. Unknown backend values stay visible as a
 * localized unknown state rather than leaking protocol text into the workspace.
 */
function localizeAction(action: string, t: (key: string) => string): string {
  switch (action.toUpperCase()) {
    case 'REJECT':
    case 'BLOCK':
      return t('outputGuardPage.actionLabels.block')
    case 'MASK':
      return t('outputGuardPage.actionLabels.mask')
    case 'REDACT':
      return t('outputGuardPage.actionLabels.redact')
    case 'ALLOW':
      return t('outputGuardPage.actionLabels.allow')
    default:
      return t('outputGuardPage.actionLabels.unknown')
  }
}

/**
 * Maps the rule status (derived from `enabled` boolean plus future PAUSED
 * state) to a Korean label under `outputGuardPage.statusLabels.*`. The table
 * combines that label with one semantic dot so normal rule state never falls
 * back to a raw uppercase code or a status capsule.
 */
function localizeStatus(status: string, t: (key: string) => string): string {
  switch (status.toUpperCase()) {
    case 'ENABLED':
      return t('outputGuardPage.statusLabels.enabled')
    case 'DISABLED':
      return t('outputGuardPage.statusLabels.disabled')
    case 'PAUSED':
      return t('outputGuardPage.statusLabels.paused')
    default:
      return t('outputGuardPage.statusLabels.unknown')
  }
}

function OutputRuleState({ enabled, t }: { enabled: boolean; t: (key: string) => string }) {
  const status = enabled ? 'ENABLED' : 'DISABLED'
  return (
    <span className={`safety-policy-state is-${enabled ? 'ready' : 'muted'}`}>
      <span aria-hidden="true" />
      {localizeStatus(status, t)}
    </span>
  )
}

function SimulationState({ status, t }: { status: 'PASS' | 'WARN' | 'FAIL'; t: (key: string) => string }) {
  const state = status === 'FAIL' ? 'danger' : status === 'WARN' ? 'attention' : 'ready'
  const label = status === 'FAIL'
    ? t('outputGuardPage.simulationStatus.blocked')
    : status === 'WARN'
      ? t('outputGuardPage.simulationStatus.needsReview')
      : t('outputGuardPage.simulationStatus.passed')
  return (
    <span className={`safety-policy-state is-${state}`}>
      <span aria-hidden="true" />
      {label}
    </span>
  )
}

export function OutputGuardManager({ embedded = false }: { embedded?: boolean } = {}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { announce } = useAnnouncer()

  const [selected, setSelected] = useState<OutputGuardRule | null>(null)
  const detailRef = useRef<HTMLDivElement>(null)
  const [ruleModalOpen, setRuleModalOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<OutputGuardRule | null>(null)
  const [modalKey, setModalKey] = useState(0)
  const [deleteTarget, setDeleteTarget] = useState<OutputGuardRule | null>(null)

  const PII_SAMPLE = '제 이메일은 user@example.com이고 전화번호는 010-0000-0000입니다. 주민번호는 000000-0000000입니다.'
  const [simulateContent, setSimulateContent] = useState(PII_SAMPLE)
  const [simulateIncludeDisabled, setSimulateIncludeDisabled] = useState(false)
  const [simulating, setSimulating] = useState(false)
  const [simulationResult, setSimulationResult] = useState<SimulateOutputGuardResponse | null>(null)
  const [simulationError, setSimulationError] = useState<string | null>(null)
  const [simulationTechnicalError, setSimulationTechnicalError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const { data: rulesData, isLoading, isFetching, error } = useQuery({
    queryKey: queryKeys.outputGuard.list(),
    queryFn: outputGuardApi.listRules,
  })

  const { data: audits = [], error: auditErrorRaw } = useQuery({
    queryKey: queryKeys.outputGuard.audits(),
    queryFn: () => outputGuardApi.listRuleAudits(50),
  })

  useEffect(() => {
    if (selected && detailRef.current && typeof detailRef.current.scrollIntoView === 'function') {
      const isNarrow = window.innerWidth <= 1280
      if (isNarrow) {
        detailRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }
    }
  }, [selected])

  const errorMsg = error ? getErrorMessage(error) : null
  const rules = rulesData ?? []
  const auditError = auditErrorRaw ? getErrorMessage(auditErrorRaw) : null

  const opsSummary = summarizeOutputGuardOps(rules, audits, auditError)
  const simulationSummary = summarizeSimulation(simulationResult, simulationError)
  const selectedRegexIssue = selected ? getRegexIssue(selected.pattern) : null

  const deleteMutation = useMutation({
    mutationFn: (id: string) => outputGuardApi.deleteRule(id),
    onSuccess: () => {
      // Authoritative refetch after the grace period commits the delete.
      void queryClient.invalidateQueries({ queryKey: queryKeys.outputGuard.all() })
      // Defer to the next tick so the announcement runs after React commits the
      // optimistic list shrink and the AT settles on the new row count.
      setTimeout(() => announce(t('common.a11y.deleted')), 0)
    },
    onError: (err) => {
      // Optimistic UI removed the rule from the cached list; re-sync so the
      // user can retry from the restored row.
      void queryClient.invalidateQueries({ queryKey: queryKeys.outputGuard.all() })
      const resolved = showApiErrorToast(err)
      announce(resolved.message, { priority: 'assertive' })
    },
  })

  useEscapeKey(!!selected && !ruleModalOpen && !deleteTarget, () => setSelected(null))

  function openCreate() {
    setEditingRule(null)
    setModalKey((k) => k + 1)
    setRuleModalOpen(true)
  }

  function openEdit(rule: OutputGuardRule) {
    setEditingRule(rule)
    setModalKey((k) => k + 1)
    setRuleModalOpen(true)
  }

  function handleRuleModalClose() {
    setRuleModalOpen(false)
    setEditingRule(null)
  }

  function handleRuleSaved() {
    // Modal handles query invalidation internally; nothing extra needed here
  }

  function refreshGuardData() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.outputGuard.all() })
  }

  function handleDelete() {
    if (!deleteTarget) return
    const target = deleteTarget
    const listKey = queryKeys.outputGuard.list()

    setDeleteTarget(null)
    const snapshot = queryClient.getQueryData<OutputGuardRule[]>(listKey)

    scheduleUndoableDelete({
      message: t('outputGuardPage.deletedNamed', { name: target.name }),
      undoLabel: t('common.undo'),
      undoneMessage: t('common.toast.undone'),
      optimistic: () => {
        if (snapshot) {
          queryClient.setQueryData<OutputGuardRule[]>(
            listKey,
            snapshot.filter((r) => r.id !== target.id),
          )
        }
        if (selected?.id === target.id) setSelected(null)
      },
      restore: () => {
        if (snapshot) {
          queryClient.setQueryData<OutputGuardRule[]>(listKey, snapshot)
        } else {
          void queryClient.invalidateQueries({ queryKey: queryKeys.outputGuard.all() })
        }
      },
      commit: () => deleteMutation.mutateAsync(target.id),
    })
  }

  async function handleSimulate() {
    if (!simulateContent.trim()) {
      setFormError(t('outputGuardPage.validation.simulationRequired'))
      return
    }

    setSimulating(true)
    setFormError(null)
    setSimulationError(null)
    setSimulationTechnicalError(null)
    try {
      const result = await outputGuardApi.simulateGuard({
        content: simulateContent,
        includeDisabled: simulateIncludeDisabled,
      })
      setSimulationResult(result)
      setSimulationError(null)
      setSimulationTechnicalError(null)
      refreshGuardData()
    } catch (e) {
      const message = getErrorMessage(e)
      const operatorMessage = t('outputGuardPage.simulationFailure')
      setFormError(operatorMessage)
      setSimulationResult(null)
      setSimulationError(operatorMessage)
      setSimulationTechnicalError(message)
    } finally {
      setSimulating(false)
    }
  }

  function applySimulationPreset(preset: 'safe' | 'pii' | 'secret') {
    if (preset === 'safe') {
      setSimulateContent('오늘 날씨가 좋습니다. 회의는 3시에 시작됩니다.')
      return
    }
    if (preset === 'pii') {
      setSimulateContent('제 이메일은 user@example.com이고 전화번호는 010-0000-0000입니다. 주민번호는 000000-0000000입니다.')
      return
    }
    setSimulateContent('API 키는 sk-abc123def456ghi789jkl012mno345pqr678 입니다. 서버 비밀번호는 P@ssw0rd123! 입니다.')
  }

  const ruleColumns = [
    {
      key: 'name',
      header: t('common.name'),
      width: '44%',
      render: (row: OutputGuardRule) => row.name,
    },
    {
      key: 'action',
      header: t('outputGuardPage.ruleAction'),
      width: '18%',
      render: (row: OutputGuardRule) => <span className="safety-policy-value">{localizeAction(row.action, t)}</span>,
    },
    {
      key: 'priority',
      header: t('outputGuardPage.rulePriority'),
      width: '12%',
      render: (row: OutputGuardRule) => row.priority,
    },
    {
      key: 'enabled',
      header: t('common.status'),
      width: '26%',
      render: (row: OutputGuardRule) => <OutputRuleState enabled={row.enabled} t={t} />,
    },
  ]

  if (isLoading && rulesData == null) {
    return (
      <div className={embedded ? 'safety-workspace__section' : 'page'}>
        {!embedded && (
          <PageHeader
            title={t('nav.outputGuard')}
            description={t('nav.help.outputGuard')}
            updateDocumentTitle
          />
        )}
        <TableSkeleton />
      </div>
    )
  }

  if (errorMsg && rulesData == null) {
    return (
      <div className={embedded ? 'safety-workspace__section' : 'page'}>
        {!embedded && (
          <PageHeader
            title={t('nav.outputGuard')}
            description={t('nav.help.outputGuard')}
            updateDocumentTitle
          />
        )}
        <WorkspaceUnavailable
          title={t('outputGuardPage.unavailableTitle')}
          description={t('outputGuardPage.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={refreshGuardData}
          isRetrying={isFetching}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{
            title: t('outputGuardPage.recoveryTitle'),
            steps: [t('outputGuardPage.recoveryAccount'), t('outputGuardPage.recoveryConnection')],
            technicalLabel: t('common.technicalDetails'),
            technicalDetail: errorMsg,
          }}
        />
      </div>
    )
  }

  return (
    <div className={embedded ? 'safety-workspace__section' : 'page'}>
      {embedded ? (
        <div className="safety-workspace__toolbar">
          {errorMsg && rulesData != null ? <span className="safety-workspace__sync-note" role="status">{t('outputGuardPage.refreshFailed')}</span> : null}
          <div className="safety-workspace__toolbar-actions">
            <RefreshButton onRefresh={refreshGuardData} />
            {rules.length > 0 ? <button className="btn btn-primary" onClick={openCreate}>{t('outputGuardPage.newRule')}</button> : null}
          </div>
        </div>
      ) : (
        <PageHeader
          title={t('nav.outputGuard')}
          description={`${t('nav.help.outputGuard')} · ${t('outputGuardPage.ruleCount')}: ${rules.length} · ${t('outputGuardPage.auditCount')}: ${audits.length}`}
          updateDocumentTitle
          actions={
            <>
              <RefreshButton onRefresh={refreshGuardData} />
              {rules.length > 0 ? <button className="btn btn-primary" onClick={openCreate}>{t('outputGuardPage.newRule')}</button> : null}
            </>
          }
        />
      )}

      {errorMsg && rulesData != null && (
        <div className="safety-workspace__sync-note" role="status">
          <span>{t('outputGuardPage.refreshFailed')}</span>
          <button className="btn btn-sm btn-secondary" onClick={refreshGuardData}>
            {t('common.retry')}
          </button>
        </div>
      )}

      <section className="safety-policy-overview" aria-labelledby="answer-protection-overview-title">
        <h3 id="answer-protection-overview-title">{t('outputGuardPage.opsTitle')}</h3>
        <dl>
          <div><dt>{t('outputGuardPage.totalRulesCard')}</dt><dd>{opsSummary.totalRules}</dd></div>
          <div><dt>{t('outputGuardPage.activeRulesCard')}</dt><dd>{opsSummary.enabledRules}</dd></div>
          <div><dt>{t('outputGuardPage.rejectRulesCard')}</dt><dd>{opsSummary.rejectRules}</dd></div>
          <div><dt>{t('outputGuardPage.auditChannelCard')}</dt><dd>{auditError ? t('outputGuardPage.auditUnavailableShort') : opsSummary.auditRows}</dd></div>
        </dl>
      </section>

      {(() => {
        const leftContent = (
          <div className="safety-workspace__panel">
            {isLoading ? (
              <TableSkeleton />
            ) : rules.length === 0 ? (
              <EmptyState
                message={t('outputGuardPage.empty')}
                description={t('nav.help.outputGuard')}
                actionLabel={t('outputGuardPage.newRule')}
                onAction={openCreate}
                example={<p>{t('outputGuardPage.emptyExample')}</p>}
              />
            ) : (
              <DataTable
                columns={ruleColumns}
                data={rules}
                keyFn={row => row.id}
                onRowClick={setSelected}
                selectedKey={selected?.id ?? null}
              />
            )}

            <CollapsibleSection title={t('outputGuardPage.simulationTitle')} defaultOpen={false}>
              <p className="detail-note">{t('outputGuardPage.simulationGuide')}</p>
              <div className="detail-actions" style={{ marginBottom: 'var(--space-3)' }}>
                <button className="btn btn-secondary btn-sm" onClick={() => applySimulationPreset('safe')}>
                  {t('outputGuardPage.presets.safe')}
                </button>
                <button className="btn btn-secondary btn-sm" onClick={() => applySimulationPreset('pii')}>
                  {t('outputGuardPage.presets.pii')}
                </button>
                <button className="btn btn-secondary btn-sm" onClick={() => applySimulationPreset('secret')}>
                  {t('outputGuardPage.presets.secret')}
                </button>
              </div>
              <div className="form-group">
                <label htmlFor="simulation-content">{t('outputGuardPage.simulationContent')}</label>
                <textarea
                  id="simulation-content"
                  rows={5}
                  value={simulateContent}
                  onChange={e => setSimulateContent(e.target.value)}
                />
              </div>
              <div className="form-group form-check">
                <input
                  id="include-disabled"
                  type="checkbox"
                  checked={simulateIncludeDisabled}
                  onChange={e => setSimulateIncludeDisabled(e.target.checked)}
                />
                <label htmlFor="include-disabled">{t('outputGuardPage.includeDisabled')}</label>
              </div>
              {formError && <div className="alert alert-error" style={{ marginBottom: 'var(--space-3)' }}>{formError}</div>}
              <button className="btn btn-primary" onClick={() => { void handleSimulate() }} disabled={simulating}>
                {simulating ? <LoadingSpinner size="sm" /> : t('outputGuardPage.runSimulation')}
              </button>

              {simulationSummary && (
                <section className="output-guard-simulation-result" aria-labelledby="output-guard-simulation-result-title">
                  <div className="output-guard-simulation-result__head">
                    <h3 id="output-guard-simulation-result-title">{t('outputGuardPage.simulationOutcome')}</h3>
                    <SimulationState status={simulationSummary.status} t={t} />
                  </div>
                  <dl className="output-guard-simulation-result__summary">
                    <div><dt>{t('outputGuardPage.blocked')}</dt><dd>{simulationSummary.blocked ? t('common.yes') : t('common.no')}</dd></div>
                    <div><dt>{t('outputGuardPage.modified')}</dt><dd>{simulationSummary.modified ? t('common.yes') : t('common.no')}</dd></div>
                    <div><dt>{t('outputGuardPage.matchedRules')}</dt><dd>{simulationSummary.matchedRuleCount}</dd></div>
                    <div><dt>{t('outputGuardPage.invalidRules')}</dt><dd>{simulationSummary.invalidRuleCount}</dd></div>
                    <div><dt>{t('outputGuardPage.blockedBy')}</dt><dd>{simulationSummary.blockedBy ?? '-'}</dd></div>
                  </dl>
                  {simulationError && (
                    <div className="alert alert-error" style={{ marginTop: 'var(--space-3)' }}>
                      {t('outputGuardPage.simulationFailure')}
                    </div>
                  )}
                  {simulationTechnicalError ? (
                    <details className="output-guard-technical">
                      <summary>{t('common.technicalDetails')}</summary>
                      <code>{simulationTechnicalError}</code>
                    </details>
                  ) : null}
                  {simulationResult && simulationResult.matchedRules.length > 0 && (
                    <div className="output-guard-simulation-result__list">
                      <h3>{t('outputGuardPage.matchedRuleList')}</h3>
                      <ul>
                        {simulationResult.matchedRules.map((rule) => (
                          <li key={`${rule.ruleId}-${rule.priority}`}>
                            <strong>{rule.ruleName}</strong>
                            <span>{localizeAction(rule.action, t)}</span>
                            <span>{t('outputGuardPage.priorityValue', { priority: rule.priority })}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {simulationResult && simulationResult.invalidRules.length > 0 && (
                    <div className="output-guard-simulation-result__list">
                      <h3>{t('outputGuardPage.invalidRuleList')}</h3>
                      <ul>
                        {simulationResult.invalidRules.map((rule) => (
                          <li key={`${rule.ruleId}-${rule.ruleName}`}>
                            <strong>{rule.ruleName}</strong>
                            <span>{t('outputGuardPage.invalidRuleNeedsFix')}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <pre className="code-block" style={{ marginTop: 'var(--space-3)' }}>{simulationSummary.resultPreview}</pre>
                </section>
              )}
            </CollapsibleSection>
          </div>
        )

        if (!selected) {
          return leftContent
        }

        return (
          <div className="split-layout">
            <div className="split-left">
              {leftContent}
            </div>
            <div className="split-right panel-stack" ref={detailRef}>
              <div className="detail-panel detail-panel--compact">
                <div className="detail-panel-header">
                  <div className="detail-header">
                    <h2>{selected.name}</h2>
                    <OutputRuleState enabled={selected.enabled} t={t} />
                  </div>
                  <button
                    className="detail-close-btn"
                    onClick={() => setSelected(null)}
                    aria-label={t('common.close')}
                  >
                    ×
                  </button>
                </div>
                <p className="detail-note" style={{ marginTop: 'var(--space-1)', marginBottom: 'var(--space-3)' }}>
                  {selected.action === 'REJECT'
                    ? t('outputGuardPage.ruleDescriptionReject')
                    : t('outputGuardPage.ruleDescriptionMask')}
                </p>
                <div className="meta-grid">
                  <span>{t('outputGuardPage.ruleAction')}: <span className="safety-policy-value">{localizeAction(selected.action, t)}</span></span>
                  <span>{t('outputGuardPage.rulePriority')}: {selected.priority}</span>
                  <span>{t('outputGuardPage.ruleStatus')}: <OutputRuleState enabled={selected.enabled} t={t} /></span>
                  <span>{t('outputGuardPage.ruleCreated')}: {formatDateTime(selected.createdAt)}</span>
                  <span>{t('outputGuardPage.ruleUpdated')}: {formatDateTime(selected.updatedAt)}</span>
                </div>
                {selectedRegexIssue && (
                  <div className="alert alert-error" style={{ marginTop: 'var(--space-3)' }}>
                    {t('outputGuardPage.patternNeedsFix')}
                  </div>
                )}
                <div className="detail-actions">
                  <button className="btn btn-secondary btn-sm" onClick={() => openEdit(selected)}>{t('common.edit')}</button>
                  <button className="btn btn-danger btn-sm" onClick={() => setDeleteTarget(selected)}>{t('common.delete')}</button>
                </div>
                <details className="output-guard-technical">
                  <summary>{t('common.technicalDetails')}</summary>
                  <dl className="output-guard-technical__list">
                    <div><dt>{t('outputGuardPage.ruleId')}</dt><dd><code>{selected.id}</code></dd></div>
                    <div><dt>{t('outputGuardPage.filterPattern')}</dt><dd><pre className="code-block">{selected.pattern}</pre></dd></div>
                    {selectedRegexIssue ? <div><dt>{t('outputGuardPage.patternError')}</dt><dd><code>{selectedRegexIssue}</code></dd></div> : null}
                  </dl>
                </details>
              </div>
            </div>
          </div>
        )
      })()}

      <OutputGuardRuleModal
        key={modalKey}
        open={ruleModalOpen}
        onClose={handleRuleModalClose}
        onSaved={handleRuleSaved}
        rule={editingRule}
      />

      {deleteTarget && (
        <ConfirmDialog
          title={t('outputGuardPage.deleteTitle')}
          message={t('outputGuardPage.deleteConfirm', { name: deleteTarget.name })}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
          danger
        />
      )}
    </div>
  )
}

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { DetailModal, LoadingSpinner, SkeletonCard, SkeletonText, ConfirmDialog, SectionErrorBoundary } from '../../../shared/ui'
import { useToastStore } from '../../../shared/store/toast.store'
import { queryKeys } from '../../../shared/lib/queryKeys'
import {
  getMcpSecurityPolicy,
  updateMcpSecurityPolicy,
  deleteMcpSecurityPolicy,
} from '../../mcp-security'

interface GlobalSettingsModalProps {
  open: boolean
  onClose: () => void
  serverNames: string[]
}

type ConfirmActionType = 'allowAll' | 'blockAll' | 'resetDefaults' | null

export function GlobalSettingsModal({ open, onClose, serverNames }: GlobalSettingsModalProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  // Draft state: null means "use server baseline", non-null means user has modified
  const [draftAllowed, setDraftAllowed] = useState<string[] | null>(null)
  const [draftOutput, setDraftOutput] = useState<number | null>(null)
  const [confirmAction, setConfirmAction] = useState<ConfirmActionType>(null)

  // Fetch current policy
  const { data: policyState, isLoading } = useQuery({
    queryKey: queryKeys.mcpSecurity.list(),
    queryFn: getMcpSecurityPolicy,
    enabled: open,
  })

  // Derive baseline from server state
  const baselineSource = policyState ? (policyState.stored ?? policyState.effective) : null
  const baselineAllowed = baselineSource?.allowedServerNames ?? []
  const baselineOutput = baselineSource?.maxToolOutputLength ?? 50000

  // Current form values: draft overrides baseline
  const allowedServerNames = draftAllowed ?? baselineAllowed
  const maxToolOutputLength = draftOutput ?? baselineOutput

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: () =>
      updateMcpSecurityPolicy({
        allowedServerNames: [...allowedServerNames].sort(),
        maxToolOutputLength,
      }),
    onSuccess: () => {
      setDraftAllowed(null)
      setDraftOutput(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.mcpSecurity.list() })
      useToastStore.getState().addToast({ type: 'success', message: t('mcpServers.toast.settingsSaved') })
      onClose()
    },
  })

  // Reset mutation
  const resetMutation = useMutation({
    mutationFn: deleteMcpSecurityPolicy,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.mcpSecurity.list() })
      if (policyState?.configDefault) {
        setDraftAllowed(policyState.configDefault.allowedServerNames)
        setDraftOutput(policyState.configDefault.maxToolOutputLength)
      }
      useToastStore.getState().addToast({ type: 'success', message: t('mcpServers.toast.policyReset') })
      setConfirmAction(null)
    },
    onError: () => {
      setConfirmAction(null)
    },
  })

  const isSaving = saveMutation.isPending || resetMutation.isPending

  function handleAllowAll() {
    // Merge all known serverNames into the allowlist
    const merged = Array.from(new Set([...allowedServerNames, ...serverNames])).sort()
    setDraftAllowed(merged)
    useToastStore.getState().addToast({ type: 'info', message: t('mcpServers.toast.allowAll') })
    setConfirmAction(null)
  }

  function handleBlockAll() {
    setDraftAllowed([])
    useToastStore.getState().addToast({ type: 'info', message: t('mcpServers.toast.blockAll') })
    setConfirmAction(null)
  }

  function handleConfirm() {
    if (confirmAction === 'allowAll') {
      handleAllowAll()
    } else if (confirmAction === 'blockAll') {
      handleBlockAll()
    } else if (confirmAction === 'resetDefaults') {
      resetMutation.mutate()
    }
  }

  function handleSave() {
    if (maxToolOutputLength < 1024 || maxToolOutputLength > 500000) {
      useToastStore.getState().addToast({ type: 'error', message: t('mcpSecurityPage.validation.outputLengthRange') })
      return
    }
    saveMutation.mutate()
  }

  const showLoading = isLoading && !policyState

  return (
    <>
      <DetailModal
        open={open}
        title={t('mcpServers.globalSettings.title')}
        onClose={onClose}
      >
        <SectionErrorBoundary name="global-settings-modal">
        {showLoading ? (
          // Modal placeholder mirrors the two stacked sections (Security Policy
          // + Performance) that resolve once settings load.
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
            <div>
              <SkeletonText width="40%" />
              <div style={{ marginTop: 'var(--space-3)' }}>
                <SkeletonCard height={64} />
              </div>
            </div>
            <div>
              <SkeletonText width="40%" />
              <div style={{ marginTop: 'var(--space-3)' }}>
                <SkeletonCard height={64} />
              </div>
            </div>
          </div>
        ) : (
          <>
            {/* Security Policy Section */}
            <section style={{ marginBottom: 'var(--space-6)' }}>
              <h3
                style={{
                  fontSize: 'var(--text-xxs)',
                  fontWeight: 'var(--font-weight-strong)',
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  color: 'var(--text-muted)',
                  marginBottom: 'var(--space-4)',
                }}
              >
                {t('mcpServers.globalSettings.securityPolicy')}
              </h3>

              {/* Max Tool Output Length */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: 'var(--space-3) var(--space-4)',
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                }}
              >
                <div>
                  <div
                    style={{
                      fontSize: 'var(--text-sm)',
                      fontWeight: 'var(--font-weight-emphasis)',
                      color: 'var(--text-primary)',
                    }}
                  >
                    {t('mcpServers.globalSettings.outputLimitLabel')}
                  </div>
                  <div
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--text-dim)',
                      marginTop: 2,
                    }}
                  >
                    {t('mcpServers.globalSettings.outputLimitHint')}
                  </div>
                </div>
                <input
                  type="number"
                  aria-label={t('mcpServers.globalSettings.outputLimitLabel')}
                  min={1024}
                  max={500000}
                  value={maxToolOutputLength}
                  onChange={(e) => setDraftOutput(Number(e.target.value))}
                  disabled={isSaving}
                  style={{ width: 120, textAlign: 'right' }}
                />
              </div>
            </section>

            {/* Bulk Security Actions */}
            <section style={{ marginBottom: 'var(--space-6)' }}>
              <h3
                style={{
                  fontSize: 'var(--text-xxs)',
                  fontWeight: 'var(--font-weight-strong)',
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  color: 'var(--text-muted)',
                  marginBottom: 'var(--space-4)',
                }}
              >
                {t('mcpServers.globalSettings.bulkActions')}
              </h3>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: 'var(--space-3)',
                }}
              >
                {/* Allow All */}
                <div
                  style={{
                    padding: 'var(--space-3) var(--space-4)',
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius)',
                  }}
                >
                  <div
                    style={{
                      fontSize: '0.82rem',
                      color: 'var(--text-secondary)',
                      marginBottom: 'var(--space-2)',
                    }}
                  >
                    {t('mcpServers.globalSettings.allowAllDesc')}
                  </div>
                  <button
                    className="btn btn-secondary"
                    style={{ width: '100%' }}
                    onClick={() => setConfirmAction('allowAll')}
                    disabled={isSaving}
                  >
                    {t('mcpServers.globalSettings.allowAll')}
                  </button>
                </div>

                {/* Block All */}
                <div
                  style={{
                    padding: 'var(--space-3) var(--space-4)',
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius)',
                  }}
                >
                  <div
                    style={{
                      fontSize: '0.82rem',
                      color: 'var(--text-secondary)',
                      marginBottom: 'var(--space-2)',
                    }}
                  >
                    {t('mcpServers.globalSettings.blockAllDesc')}
                  </div>
                  <button
                    className="btn btn-danger"
                    style={{ width: '100%' }}
                    onClick={() => setConfirmAction('blockAll')}
                    disabled={isSaving}
                  >
                    {t('mcpServers.globalSettings.blockAll')}
                  </button>
                </div>
              </div>
            </section>

            {/* Reset to Defaults */}
            <section style={{ marginBottom: 'var(--space-2)' }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: 'var(--space-3) var(--space-4)',
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                }}
              >
                <div>
                  <div
                    style={{
                      fontSize: 'var(--text-sm)',
                      fontWeight: 'var(--font-weight-emphasis)',
                      color: 'var(--text-primary)',
                    }}
                  >
                    {t('mcpServers.globalSettings.resetDefaults')}
                  </div>
                  <div
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--text-dim)',
                      marginTop: 2,
                    }}
                  >
                    {t('mcpServers.globalSettings.resetDefaultsDesc')}
                  </div>
                </div>
                <button
                  className="btn btn-secondary"
                  onClick={() => setConfirmAction('resetDefaults')}
                  disabled={isSaving || !policyState}
                >
                  {resetMutation.isPending ? (
                    <LoadingSpinner size="sm" />
                  ) : (
                    t('mcpServers.globalSettings.reset')
                  )}
                </button>
              </div>
            </section>

            {/* Footer */}
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={onClose} disabled={isSaving}>
                {t('mcpServers.globalSettings.cancel')}
              </button>
              <button
                className="btn btn-primary"
                onClick={handleSave}
                disabled={isSaving}
              >
                {saveMutation.isPending ? (
                  <LoadingSpinner size="sm" />
                ) : (
                  t('mcpServers.globalSettings.saveChanges')
                )}
              </button>
            </div>
          </>
        )}
        </SectionErrorBoundary>
      </DetailModal>

      {/* Confirm dialogs */}
      {confirmAction === 'allowAll' && (
        <ConfirmDialog
          title={t('mcpServers.globalSettings.allowAll')}
          message={t('mcpServers.confirm.allowAll')}
          onConfirm={handleConfirm}
          onCancel={() => setConfirmAction(null)}
        />
      )}
      {confirmAction === 'blockAll' && (
        <ConfirmDialog
          title={t('mcpServers.globalSettings.blockAll')}
          message={t('mcpServers.confirm.blockAll')}
          onConfirm={handleConfirm}
          onCancel={() => setConfirmAction(null)}
          danger
        />
      )}
      {confirmAction === 'resetDefaults' && (
        <ConfirmDialog
          title={t('mcpServers.globalSettings.resetDefaults')}
          message={t('mcpServers.confirm.resetDefaults')}
          onConfirm={handleConfirm}
          onCancel={() => setConfirmAction(null)}
          danger
        />
      )}
    </>
  )
}

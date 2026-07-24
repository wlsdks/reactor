/**
 * OperationButton — standardised button for mutation/submit operations.
 *
 * Behaviour:
 *  - Renders `<button class="btn btn-{variant} {operating? 'btn--operating' : ''}">`
 *  - When `isOperating`, prepends a small <LoadingSpinner /> and shows
 *    `loadingLabel ?? children` so screen readers announce the loading state.
 *  - `aria-busy` reflects `isOperating`; `disabled` is the OR of `isOperating`
 *    and the explicit `disabled` prop, so callers no longer need to combine
 *    `isPending || isSubmitting` themselves.
 *  - Forwards refs (focus management, parent measurement).
 *
 * Migration backlog (PRs to come — keep each PR scoped):
 *  After this initial migration (~10 sites), the following high-traffic
 *  surfaces still use the bespoke `disabled={mutation.isPending}` +
 *  `isPending ? <LoadingSpinner /> : label` pattern. Migrate progressively:
 *
 *    src/features/admin-settings/ui/SettingEditModal.tsx              — Save
 *    src/features/admin-settings/ui/AdminSettingsTab.tsx              — Refresh
 *    src/features/audit/ui/AuditRollbackModal.tsx                     — Confirm rollback
 *    src/features/cache-runtime → src/features/rag-cache/ui/CacheRuntimeControls.tsx
 *                                                                     — invalidate key/pattern, toggles
 *    src/features/conversation-analytics/ui/...                       — export buttons
 *    src/features/debug-replay/ui/...                                 — replay/run buttons
 *    src/features/doctor/ui/...                                       — repair/run actions
 *    src/features/documents/ui/...                                    — add/batch buttons
 *    src/features/evals/ui/...                                        — run eval buttons
 *    src/features/feedback/ui/FeedbackManager.tsx                     — bulk mark done/inbox
 *    src/features/followup-suggestions/ui/...                         — accept/reject
 *    src/features/input-guard/ui/StageConfigPanel.tsx                 — save diff
 *    src/features/input-guard/ui/InputGuardRulesTab.tsx               — toggle
 *    src/features/input-guard/ui/InputGuardSimulateTab.tsx            — simulate
 *    src/features/integrations/ui/...                                 — connect/disconnect
 *    src/features/mcp-security/ui/...                                 — apply policy
 *    src/features/mcp-servers/ui/McpServerDetailView.tsx              — connect/disconnect
 *    src/features/mcp-servers/ui/McpServersListView.tsx               — bulk emergency
 *    src/features/mcp-servers/ui/GlobalSettingsModal.tsx              — save
 *    src/features/model-registry/ui/...                               — register/sync
 *    src/features/output-guard/ui/...                                 — save/toggle
 *    src/features/proactive-channels/ui/...                           — connect
 *    src/features/prompt-lab/ui/...                                   — run experiment
 *    src/features/prompt-studio/ui/ExperimentsTab.tsx                 — run/delete/cancel
 *    src/features/prompts/ui/...                                      — save template
 *    src/features/rag-analytics/ui/...                                — export/refresh
 *    src/features/rag-cache/ui/RagCacheManager.tsx                    — invalidate
 *    src/features/rag-cache/ui/RagPolicyEditor.tsx                    — save/reset
 *    src/features/rbac/ui/...                                         — assign role
 *    src/features/scheduler/ui/...                                    — enable/disable
 *    src/features/sessions/ui/...                                     — terminate
 *    src/features/slack-bots/ui/...                                   — install/remove
 *    src/features/tenant-admin/ui/...                                 — quota update
 *    src/features/tool-policy/ui/ToolPolicyManager.tsx                — save/reset
 *    src/features/user-memory/ui/UserMemoryTab.tsx                    — save/delete
 *    src/widgets/layout/Header.tsx                                    — log out, etc.
 *
 *  Roughly ~30 high-visibility sites remain (out of ~40 originally
 *  identified). The component is intentionally additive — existing
 *  hand-rolled buttons keep working until they are migrated.
 */
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { LoadingSpinner } from './LoadingSpinner'
import { Tooltip } from './Tooltip'

export type OperationButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost'

export interface OperationButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'disabled'> {
  /** Visual variant — maps to existing `.btn-primary | .btn-secondary | .btn-danger | .btn-ghost`. */
  variant?: OperationButtonVariant
  /** True while a mutation/submission is in flight. Forces `disabled` and `aria-busy`. */
  isOperating?: boolean
  /** External disabled state (validation failure, missing inputs, etc.). */
  disabled?: boolean
  /**
   * Optional override for the label rendered while operating. Defaults to the
   * translated `common.processing` string so screen readers always hear that
   * a request is in flight.
   */
  loadingLabel?: ReactNode
  /**
   * Optional reason surfaced via a Tooltip when the button is disabled (and
   * not currently operating). When set, the disabled button is wrapped in a
   * Tooltip so operators can discover *why* the action is unavailable instead
   * of guessing. Ignored while the button is enabled or busy.
   */
  disabledReason?: string
  /** Visible button content when not operating. */
  children: ReactNode
}

export const OperationButton = forwardRef<HTMLButtonElement, OperationButtonProps>(
  function OperationButton(
    {
      variant = 'primary',
      isOperating = false,
      disabled = false,
      loadingLabel,
      disabledReason,
      children,
      className,
      type,
      ...rest
    },
    ref,
  ) {
    const { t } = useTranslation()

    const classes = [
      'btn',
      `btn-${variant}`,
      isOperating ? 'btn--operating' : '',
      className ?? '',
    ]
      .filter(Boolean)
      .join(' ')

    const button = (
      <button
        {...rest}
        ref={ref}
        type={type ?? 'button'}
        className={classes}
        disabled={isOperating || disabled}
        aria-busy={isOperating || undefined}
      >
        {isOperating ? (
          <>
            <LoadingSpinner size="sm" />
            <span>{loadingLabel ?? t('common.processing')}</span>
          </>
        ) : (
          children
        )}
      </button>
    )

    // Surface the disabled reason via a Tooltip so operators understand *why*
    // the action is unavailable. Only attach the Tooltip when there is a
    // reason and the button is disabled by the caller (not just busy).
    if (disabledReason && disabled && !isOperating) {
      return <Tooltip content={disabledReason}>{button}</Tooltip>
    }

    return button
  },
)

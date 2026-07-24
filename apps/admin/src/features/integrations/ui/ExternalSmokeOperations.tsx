import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { MessageSquare, Network, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { ConfirmDialog, OperationButton } from '../../../shared/ui'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { hasA2aSmokeEvidence, hasSlackSmokeEvidence } from '../../../shared/lib/liveSmokeEvidence'
import { useToastStore } from '../../../shared/store/toast.store'
import type { DashboardReleaseReadinessSummary } from '../../dashboard/types'
import { runA2aLiveSmoke, runSlackLiveSmoke } from '../api'
import type { A2aLiveSmokeResult, SlackLiveSmokeResult } from '../types'
import './external-smoke-operations.css'

type SmokeKind = 'slack' | 'a2a'
type SmokeOperationState = 'pass' | 'warn' | 'fail' | 'idle'

interface ExternalSmokeOperationsProps {
  releaseReadiness?: DashboardReleaseReadinessSummary | null
  readinessRefreshing?: boolean
  onRefreshReadiness: () => Promise<unknown>
}

function readinessMarker(value: number | string | null | undefined): string {
  return value == null ? '' : String(value)
}

function passedCheckSummary(checks: Record<string, { status?: string }>): string {
  const values = Object.values(checks)
  return `${values.filter((check) => check.status === 'passed').length}/${values.length}`
}

function displayScalar(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '-'
}

function resolveSmokeState(result: { ok: boolean } | null, aggregated: boolean): SmokeOperationState {
  if (!result) return 'idle'
  if (!result.ok) return 'fail'
  return aggregated ? 'pass' : 'warn'
}

function smokeStateLabel(
  t: (key: string) => string,
  result: { ok: boolean } | null,
  aggregated: boolean,
): string {
  if (!result) return t('integrationsPage.releaseSmoke.operations.notRun')
  if (!result.ok) return t('integrationsPage.releaseSmoke.operations.failed')
  return aggregated
    ? t('integrationsPage.releaseSmoke.operations.readinessAggregated')
    : t('integrationsPage.releaseSmoke.operations.readinessPending')
}

export function ExternalSmokeOperations({
  releaseReadiness,
  readinessRefreshing = false,
  onRefreshReadiness,
}: ExternalSmokeOperationsProps) {
  const { t } = useTranslation()
  const [confirmation, setConfirmation] = useState<SmokeKind | null>(null)
  const [slackResult, setSlackResult] = useState<SlackLiveSmokeResult | null>(null)
  const [a2aResult, setA2aResult] = useState<A2aLiveSmokeResult | null>(null)
  const [baselineMarkers, setBaselineMarkers] = useState<Record<SmokeKind, string>>({
    slack: '',
    a2a: '',
  })

  const currentMarker = readinessMarker(releaseReadiness?.syncedAt)
  const slackTarget = slackResult?.liveTarget ?? null
  const slackAggregated = slackResult?.ok === true
    && baselineMarkers.slack !== ''
    && currentMarker !== baselineMarkers.slack
    && hasSlackSmokeEvidence(releaseReadiness?.slackGatewaySmoke)
    && (!slackTarget?.channelId
      || releaseReadiness?.slackGatewaySmoke?.channelId === slackTarget.channelId)
  const liveA2aProtocol = a2aResult?.evidence?.a2aProtocol ?? null
  const a2aAggregated = a2aResult?.ok === true
    && baselineMarkers.a2a !== ''
    && currentMarker !== baselineMarkers.a2a
    && hasA2aSmokeEvidence(releaseReadiness?.a2aProtocol)
    && (!liveA2aProtocol?.agentCard?.name
      || releaseReadiness?.a2aProtocol?.agentCard?.name === liveA2aProtocol.agentCard.name)

  const slackMutation = useMutation({
    mutationFn: runSlackLiveSmoke,
    onSuccess: async (result) => {
      setSlackResult(result)
      await onRefreshReadiness()
      useToastStore.getState().addToast({
        type: result.ok ? 'success' : 'error',
        message: result.ok
          ? t('integrationsPage.releaseSmoke.operations.slackSuccess')
          : t('integrationsPage.releaseSmoke.operations.slackFailed'),
      })
    },
    onError: (error: Error) => {
      useToastStore.getState().addToast({ type: 'error', message: getErrorMessage(error) })
    },
  })

  const a2aMutation = useMutation({
    mutationFn: runA2aLiveSmoke,
    onSuccess: async (result) => {
      setA2aResult(result)
      await onRefreshReadiness()
      useToastStore.getState().addToast({
        type: result.ok ? 'success' : 'error',
        message: result.ok
          ? t('integrationsPage.releaseSmoke.operations.a2aSuccess')
          : t('integrationsPage.releaseSmoke.operations.a2aFailed'),
      })
    },
    onError: (error: Error) => {
      useToastStore.getState().addToast({ type: 'error', message: getErrorMessage(error) })
    },
  })

  function confirmSmoke() {
    if (!confirmation) return
    setBaselineMarkers((current) => ({
      ...current,
      [confirmation]: currentMarker,
    }))
    if (confirmation === 'slack') slackMutation.mutate()
    else a2aMutation.mutate()
    setConfirmation(null)
  }

  const a2aTaskCheck = a2aResult?.checks.task_api
  const a2aAgent = liveA2aProtocol?.agentCard?.name ?? null
  const slackState = resolveSmokeState(slackResult, slackAggregated)
  const a2aState = resolveSmokeState(a2aResult, a2aAggregated)

  return (
    <section
      id="external-smoke-operations"
      className="external-smoke-operations"
      aria-label={t('integrationsPage.releaseSmoke.operations.title')}
    >
      <div className="external-smoke-operations__header">
        <div>
          <h4>{t('integrationsPage.releaseSmoke.operations.title')}</h4>
          <p>{t('integrationsPage.releaseSmoke.operations.description')}</p>
        </div>
        <OperationButton
          variant="secondary"
          isOperating={readinessRefreshing}
          onClick={() => { void onRefreshReadiness() }}
        >
          <RefreshCw size={16} aria-hidden="true" />
          {t('integrationsPage.releaseSmoke.operations.refreshReadiness')}
        </OperationButton>
      </div>

      <div className="external-smoke-operations__grid">
        <article className="external-smoke-operation">
          <div className="external-smoke-operation__head">
            <div className="external-smoke-operation__title">
              <MessageSquare size={18} aria-hidden="true" />
              <strong>{t('integrationsPage.releaseSmoke.operations.slackTitle')}</strong>
            </div>
            <span className={`smoke-operation-status is-${slackState}`}>
              <span aria-hidden="true" />
              {smokeStateLabel(t, slackResult, slackAggregated)}
            </span>
          </div>
          <p>{t('integrationsPage.releaseSmoke.operations.slackSideEffect')}</p>
          <OperationButton
            variant="primary"
            isOperating={slackMutation.isPending}
            onClick={() => setConfirmation('slack')}
          >
            <MessageSquare size={16} aria-hidden="true" />
            {t('integrationsPage.releaseSmoke.operations.runSlack')}
          </OperationButton>
          {slackResult && (
            <div
              className="external-smoke-operation__result"
              role="region"
              aria-label={t('integrationsPage.releaseSmoke.operations.slackResult')}
              aria-live="polite"
            >
              <dl>
                <div><dt>{t('integrationsPage.releaseSmoke.slackWorkspace')}</dt><dd>{slackTarget?.workspaceId ?? '-'}</dd></div>
                <div><dt>{t('integrationsPage.releaseSmoke.slackChannel')}</dt><dd>{slackTarget?.channelId ?? '-'}</dd></div>
                <div><dt>{t('integrationsPage.releaseSmoke.slackBotUser')}</dt><dd>{slackTarget?.botUserId ?? '-'}</dd></div>
                <div><dt>{t('integrationsPage.releaseSmoke.operations.checks')}</dt><dd>{passedCheckSummary(slackResult.checks)}</dd></div>
              </dl>
              {slackResult.error && <p className="external-smoke-operation__error">{slackResult.error}</p>}
              <strong>{slackAggregated
                ? t('integrationsPage.releaseSmoke.operations.readinessAggregated')
                : t('integrationsPage.releaseSmoke.operations.readinessPending')}</strong>
            </div>
          )}
        </article>

        <article className="external-smoke-operation">
          <div className="external-smoke-operation__head">
            <div className="external-smoke-operation__title">
              <Network size={18} aria-hidden="true" />
              <strong>{t('integrationsPage.releaseSmoke.operations.a2aTitle')}</strong>
            </div>
            <span className={`smoke-operation-status is-${a2aState}`}>
              <span aria-hidden="true" />
              {smokeStateLabel(t, a2aResult, a2aAggregated)}
            </span>
          </div>
          <p>{t('integrationsPage.releaseSmoke.operations.a2aSideEffect')}</p>
          <OperationButton
            variant="primary"
            isOperating={a2aMutation.isPending}
            onClick={() => setConfirmation('a2a')}
          >
            <Network size={16} aria-hidden="true" />
            {t('integrationsPage.releaseSmoke.operations.runA2a')}
          </OperationButton>
          {a2aResult && (
            <div
              className="external-smoke-operation__result"
              role="region"
              aria-label={t('integrationsPage.releaseSmoke.operations.a2aResult')}
              aria-live="polite"
            >
              <dl>
                <div><dt>{t('integrationsPage.releaseSmoke.operations.peer')}</dt><dd>{a2aResult.base_url ?? '-'}</dd></div>
                <div><dt>{t('integrationsPage.releaseSmoke.a2aAgent')}</dt><dd>{a2aAgent ?? '-'}</dd></div>
                <div><dt>{t('integrationsPage.releaseSmoke.operations.taskId')}</dt><dd>{displayScalar(a2aTaskCheck?.task_id)}</dd></div>
                <div><dt>{t('integrationsPage.releaseSmoke.operations.checks')}</dt><dd>{passedCheckSummary(a2aResult.checks)}</dd></div>
              </dl>
              {a2aResult.error && <p className="external-smoke-operation__error">{a2aResult.error}</p>}
              <strong>{a2aAggregated
                ? t('integrationsPage.releaseSmoke.operations.readinessAggregated')
                : t('integrationsPage.releaseSmoke.operations.readinessPending')}</strong>
            </div>
          )}
        </article>
      </div>

      <p className="external-smoke-operations__audit">
        {t('integrationsPage.releaseSmoke.operations.auditNotice')}
      </p>

      {confirmation && (
        <ConfirmDialog
          title={confirmation === 'slack'
            ? t('integrationsPage.releaseSmoke.operations.slackConfirmTitle')
            : t('integrationsPage.releaseSmoke.operations.a2aConfirmTitle')}
          message={confirmation === 'slack'
            ? t('integrationsPage.releaseSmoke.operations.slackConfirmMessage')
            : t('integrationsPage.releaseSmoke.operations.a2aConfirmMessage')}
          confirmText={confirmation === 'slack' ? 'SLACK' : 'A2A'}
          danger
          onConfirm={confirmSmoke}
          onCancel={() => setConfirmation(null)}
        />
      )}
    </section>
  )
}

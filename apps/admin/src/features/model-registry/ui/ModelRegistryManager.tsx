import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Play, RefreshCw } from 'lucide-react'
import {
  DataTable,
  EmptyState,
  OperationButton,
  TableSkeleton,
} from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { formatLocaleNumber } from '../../../shared/lib/intl'
import {
  hasProviderSmokeEvidence,
  listProviderSmokeMissingCheckIds,
  type ProviderSmokeCheckId,
} from '../../../shared/lib/providerSmokeEvidence'
import {
  RELEASE_PROVIDER_SMOKE_ANCHOR_ID,
  releaseReportBelongsToGate,
} from '../../../shared/releaseWorkflow'
import { usePageHelp } from '../../../shared/lib/usePageHelp'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { useToastStore } from '../../../shared/store/toast.store'
import { listAlertRules } from '../../platform-admin/api'
import { getDashboard } from '../../dashboard/api'
import { listModels, runProviderSmoke } from '../api'
import type { ModelEntry, ProviderLiveSmokeResult } from '../types'
import type { Column } from '../../../shared/ui'
import { ModelDetailDrawer } from './ModelDetailDrawer'

const MONO_CELL: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 'var(--text-xxs)',
}

const NARROW_VIEWPORT_PX = 960

function useIsWideViewport(breakpoint: number): boolean {
  const [isWide, setIsWide] = useState<boolean>(() => {
    if (typeof window === 'undefined') return true
    return window.innerWidth > breakpoint
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    const handler = () => setIsWide(window.innerWidth > breakpoint)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [breakpoint])

  return isWide
}

function listSummary(values: string[] | null | undefined): string {
  return values?.filter(Boolean).join(', ') ?? ''
}

function describeProviderEvidenceValue(
  value: string | null | undefined,
  t: ReturnType<typeof useTranslation>['t'],
): string {
  if (!value) return ''
  const labels: Record<string, string> = {
    passed: '통과',
    warning: '검토 필요',
    blocked: '차단',
    missing: '미연결',
    live_smoke: '실시간 점검',
    required_env: '환경 설정',
    tracing_config: '추적 설정',
    chat_model_invoke: '모델 호출',
    usage_metadata: '사용량 메타데이터',
    provider_smoke: 'AI 모델 응답 시험',
    backend_provider_integration: 'AI 모델 연결',
  }
  return labels[value] ?? t('modelsPage.providerSmoke.unknownEvidence')
}

function displayProvider(t: ReturnType<typeof useTranslation>['t'], value: string | null | undefined): string {
  const normalized = value?.trim().toLowerCase()
  if (normalized === 'ollama') return t('modelsPage.providerSmoke.providerLabels.local')
  if (normalized === 'openai') return t('modelsPage.providerSmoke.providerLabels.openai')
  if (normalized === 'anthropic') return t('modelsPage.providerSmoke.providerLabels.anthropic')
  return t('modelsPage.providerSmoke.providerLabels.unknown')
}

function displayModel(t: ReturnType<typeof useTranslation>['t'], value: string | null | undefined): string {
  const normalized = value?.trim().toLowerCase().replace(/[_.:-]+/g, '') ?? ''
  if (normalized.includes('gpt')) return t('modelsPage.providerSmoke.modelLabels.gpt')
  if (normalized.includes('claude')) return t('modelsPage.providerSmoke.modelLabels.claude')
  if (normalized.includes('gemma')) return t('modelsPage.providerSmoke.modelLabels.gemma')
  if (normalized.includes('qwen')) return t('modelsPage.providerSmoke.modelLabels.qwen')
  return t('modelsPage.providerSmoke.modelLabels.unknown')
}

function displayUsageSource(t: ReturnType<typeof useTranslation>['t'], value: string | null | undefined): string {
  const normalized = value?.trim().toLowerCase().replace(/[_.:-]+/g, '') ?? ''
  return normalized.includes('usagemetadata')
    ? t('modelsPage.providerSmoke.usageSourceLabels.recorded')
    : t('modelsPage.providerSmoke.usageSourceLabels.unknown')
}

function providerSmokeCheckLabel(t: ReturnType<typeof useTranslation>['t'], checkId: ProviderSmokeCheckId): string {
  const labels: Record<ProviderSmokeCheckId, string> = {
    provider: t('modelsPage.providerSmoke.provider'),
    model: t('modelsPage.providerSmoke.model'),
    usage_present: t('modelsPage.providerSmoke.usage'),
    usage_source: t('modelsPage.providerSmoke.source'),
    usage_tokens: t('modelsPage.providerSmoke.tokenCounts'),
    usage_breakdown: t('modelsPage.providerSmoke.breakdown'),
    required_usage_metadata: t('modelsPage.providerSmoke.requiredChecks'),
  }
  return labels[checkId]
}

function filterLocalProviderEnv(names: string[] | null | undefined, localProviderNoKey: boolean): string[] {
  const values = names?.filter(Boolean) ?? []
  if (!localProviderNoKey) return values
  return values.filter((name) => name !== 'OPENAI_API_KEY')
}

function readinessMarker(value: number | string | null | undefined): string {
  return value == null ? '' : String(value)
}

export function ModelRegistryManager() {
  const { t } = useTranslation()
  void t('modelsPage.help', { returnObjects: true })
  usePageHelp({ helpKey: 'modelsPage.help' })
  const isWide = useIsWideViewport(NARROW_VIEWPORT_PX)
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [liveSmokeResult, setLiveSmokeResult] = useState<ProviderLiveSmokeResult | null>(null)
  const [readinessMarkerBeforeLiveSmoke, setReadinessMarkerBeforeLiveSmoke] = useState('')

  const {
    data: models = [],
    isLoading,
    isFetching: modelsFetching,
    isError: modelsUnavailable,
    error: modelsError,
    refetch: refetchModels,
  } = useQuery({
    queryKey: queryKeys.models.list(),
    queryFn: listModels,
  })

  const { data: alertRules = [] } = useQuery({
    queryKey: queryKeys.platformAdmin.alertRules(),
    queryFn: listAlertRules,
  })

  const {
    data: dashboard,
    isFetching: dashboardFetching,
    isError: dashboardUnavailable,
    error: dashboardError,
    refetch: refetchDashboard,
  } = useQuery({
    queryKey: queryKeys.dashboard.main(['reactor.release.readiness']),
    queryFn: () => getDashboard(['reactor.release.readiness']),
  })

  const defaultModel = models.find(m => m.isDefault)
  const selected = models.find(m => m.name === selectedName) ?? null
  const releaseReadiness = dashboard?.releaseReadiness ?? null
  const backendProviderIntegration = releaseReadiness?.backendProviderIntegration ?? null
  const providerUsage = backendProviderIntegration?.usageMetadata ?? null
  const providerChecks = listSummary(
    backendProviderIntegration?.requiredChecks?.map((value) => describeProviderEvidenceValue(value, t)),
  )
  const configuredProvider = backendProviderIntegration?.provider ?? defaultModel?.provider ?? null
  const configuredModel = backendProviderIntegration?.model ?? defaultModel?.name ?? null
  const hasConfiguredFallback = backendProviderIntegration == null && Boolean(configuredProvider || configuredModel)
  const localProviderNoKey = configuredProvider === 'ollama'
  const providerGate = releaseReadiness?.gates?.find((gate) => gate.id === 'provider') ?? null
  const providerGateItem = releaseReadiness?.items?.find((item) =>
    item.name ? releaseReportBelongsToGate(item.name, 'provider') : false,
  ) ?? null
  const providerReports = [
    ...(releaseReadiness?.blockingReports ?? []),
    ...(releaseReadiness?.warningReports ?? []),
  ].filter((report) => releaseReportBelongsToGate(report, 'provider'))
  const providerMissingEnv = filterLocalProviderEnv([
    ...(releaseReadiness?.missingEnvAnyOf ?? []),
    ...(releaseReadiness?.tagRecommendation?.missingEnv ?? []),
  ], localProviderNoKey)
  const missingProviderSmokeChecks = listProviderSmokeMissingCheckIds(backendProviderIntegration)
    .map((checkId) => providerSmokeCheckLabel(t, checkId))
  const providerSmokeReady = hasProviderSmokeEvidence(backendProviderIntegration)
  const showProviderSmokeHandoff = releaseReadiness !== null || dashboardUnavailable
  const showProviderSmokeRemediation = showProviderSmokeHandoff && missingProviderSmokeChecks.length > 0
  const liveProviderEvidence = liveSmokeResult?.evidence?.backendProviderIntegration ?? null
  const liveProviderUsage = liveProviderEvidence?.usageMetadata ?? null
  const liveSmokePassed = liveSmokeResult?.ok === true && hasProviderSmokeEvidence(liveProviderEvidence)
  const liveSmokeAggregated = liveSmokePassed
    && readinessMarkerBeforeLiveSmoke !== ''
    && readinessMarker(releaseReadiness?.syncedAt) !== readinessMarkerBeforeLiveSmoke
    && backendProviderIntegration?.provider === liveProviderEvidence?.provider
    && backendProviderIntegration?.model === liveProviderEvidence?.model
    && hasProviderSmokeEvidence(backendProviderIntegration)

  const providerSmokeMutation = useMutation({
    mutationFn: runProviderSmoke,
    onSuccess: async (result) => {
      setLiveSmokeResult(result)
      await refetchDashboard()
      useToastStore.getState().addToast({
        type: result.ok ? 'success' : 'error',
        message: result.ok
          ? t('modelsPage.providerSmoke.liveRunSuccess')
          : t('modelsPage.providerSmoke.liveRunFailed'),
      })
    },
    onError: (error: Error) => {
      useToastStore.getState().addToast({ type: 'error', message: getErrorMessage(error) })
    },
  })

  const handleRunProviderSmoke = () => {
    setReadinessMarkerBeforeLiveSmoke(readinessMarker(releaseReadiness?.syncedAt))
    providerSmokeMutation.mutate()
  }
  const hasProvider = models.some(m => !!m.provider)
  const hasContext = models.some(m => m.contextLength != null)

  const columns: Column<ModelEntry>[] = [
    {
      key: 'name',
      header: t('common.name'),
      width: isWide ? '28%' : '40%',
      sortable: true,
      render: (row) => (
        <span className="model-name-cell">
          <span className="model-name-value" style={MONO_CELL} title={row.name}>{row.name}</span>
          {row.isDefault && (
            <span className="model-default-label">
              {t('modelsPage.default')}
            </span>
          )}
        </span>
      ),
    },
  ]

  if (isWide && hasProvider) {
    columns.push({
      key: 'provider',
      header: t('modelsPage.provider'),
      width: '16%',
      sortable: true,
      render: (row) => (
        row.provider
          ? <span>{displayProvider(t, row.provider)}</span>
          : <span className="text-muted">—</span>
      ),
    })
  }

  columns.push(
    {
      key: 'inputPricePerMillionTokens',
      header: t(isWide ? 'modelsPage.inputPrice' : 'modelsPage.inputPriceShort'),
      width: isWide ? '18%' : '30%',
      sortable: true,
      render: (row) => (
        <span style={MONO_CELL}>${row.inputPricePerMillionTokens.toFixed(2)}</span>
      ),
    },
    {
      key: 'outputPricePerMillionTokens',
      header: t(isWide ? 'modelsPage.outputPrice' : 'modelsPage.outputPriceShort'),
      width: isWide ? '18%' : '30%',
      sortable: true,
      render: (row) => (
        <span style={MONO_CELL}>${row.outputPricePerMillionTokens.toFixed(2)}</span>
      ),
    },
  )

  if (isWide && hasContext) {
    columns.push({
      key: 'contextLength',
      header: t('modelsPage.contextLength'),
      width: '20%',
      sortable: true,
      render: (row) => (
        <span style={MONO_CELL}>
          {formatLocaleNumber(row.contextLength)}
        </span>
      ),
    })
  }

  if (isLoading) {
    return (
      <div className="model-registry-manager">
        <dl className="model-registry-summary" aria-label={t('modelsPage.summaryLabel')}>
          <div><dt>{t('modelsPage.totalModels')}</dt><dd>…</dd></div>
          <div><dt>{t('modelsPage.defaultModel')}</dt><dd>…</dd></div>
        </dl>
        <TableSkeleton />
      </div>
    )
  }

  if (modelsUnavailable) {
    return (
      <div className="model-registry-manager">
        <section className="model-registry__unavailable" role="alert">
          <div>
            <strong>{t('modelsPage.loadErrorTitle')}</strong>
            <p>{t('modelsPage.loadErrorDescription')}</p>
          </div>
          <OperationButton
            variant="secondary"
            isOperating={modelsFetching}
            onClick={() => { void refetchModels() }}
          >
            <RefreshCw size={16} aria-hidden="true" />
            {t('common.retry')}
          </OperationButton>
          {modelsError ? <details><summary>{t('common.technicalDetails')}</summary><code>{getErrorMessage(modelsError)}</code></details> : null}
        </section>
      </div>
    )
  }

  return (
    <div className="model-registry-manager">

      <dl className="model-registry-summary" aria-label={t('modelsPage.summaryLabel')}>
        <div><dt>{t('modelsPage.totalModels')}</dt><dd>{models.length}</dd></div>
        <div><dt>{t('modelsPage.defaultModel')}</dt><dd>{defaultModel?.name ?? '—'}</dd></div>
      </dl>

      {models.length === 0 ? (
        <EmptyState message={t('modelsPage.noModels')} />
      ) : (
        <DataTable
          columns={columns}
          data={models}
          keyFn={row => row.name}
          onRowClick={row => setSelectedName(row.name)}
          selectedKey={selectedName}
        />
      )}

      {showProviderSmokeHandoff && (
        <section
          id={RELEASE_PROVIDER_SMOKE_ANCHOR_ID}
          className="model-provider-smoke"
          aria-label={t('modelsPage.providerSmoke.title')}
        >
          <div className="model-provider-smoke__header">
            <div>
              <h2 className="model-provider-smoke__title">{t('modelsPage.providerSmoke.title')}</h2>
              <p className="model-provider-smoke__description">{t('modelsPage.providerSmoke.description')}</p>
            </div>
            <span className={`model-provider-smoke__state model-provider-smoke__state--${providerSmokeReady ? 'pass' : 'warn'}`}>
              <span aria-hidden="true" />
              {providerSmokeReady
                ? t('modelsPage.providerSmoke.statusReady')
                : t('modelsPage.providerSmoke.statusNeedsReview')}
            </span>
          </div>
          {dashboardUnavailable ? (
            <section className="model-provider-smoke__unavailable" role="alert">
              <div>
                <strong>{t('modelsPage.providerSmoke.readinessUnavailableTitle')}</strong>
                <p>{t('modelsPage.providerSmoke.readinessUnavailableDescription')}</p>
              </div>
              <OperationButton
                variant="secondary"
                isOperating={dashboardFetching}
                onClick={() => { void refetchDashboard() }}
              >
                <RefreshCw size={16} aria-hidden="true" />
                {t('modelsPage.providerSmoke.refreshReadiness')}
              </OperationButton>
              {dashboardError ? <details><summary>{t('common.technicalDetails')}</summary><code>{getErrorMessage(dashboardError)}</code></details> : null}
            </section>
          ) : (
          <section className="model-provider-smoke__operations" aria-label={t('modelsPage.providerSmoke.operationsTitle')}>
            <div className="model-provider-smoke__operations-header">
              <div>
                <h3>{t('modelsPage.providerSmoke.operationsTitle')}</h3>
                <p>{t('modelsPage.providerSmoke.operationsDescription')}</p>
              </div>
              <span className={`model-provider-smoke__state model-provider-smoke__state--${liveSmokeResult ? liveSmokePassed ? liveSmokeAggregated ? 'pass' : 'warn' : 'fail' : 'muted'}`}>
                <span aria-hidden="true" />
                {liveSmokeResult
                  ? liveSmokePassed
                    ? liveSmokeAggregated
                      ? t('modelsPage.providerSmoke.readinessAggregated')
                      : t('modelsPage.providerSmoke.readinessPending')
                    : t('modelsPage.providerSmoke.liveFailed')
                  : t('modelsPage.providerSmoke.notRun')}
              </span>
            </div>
            <div className="model-provider-smoke__operations-target">
              <span>{t('modelsPage.providerSmoke.configuredTarget')}</span>
              <strong>{configuredProvider ? displayProvider(t, configuredProvider) : t('modelsPage.providerSmoke.missing')} / {configuredModel ? displayModel(t, configuredModel) : t('modelsPage.providerSmoke.missing')}</strong>
            </div>
            <div className="model-provider-smoke__operations-actions">
              <OperationButton
                variant="primary"
                isOperating={providerSmokeMutation.isPending}
                onClick={handleRunProviderSmoke}
              >
                <Play size={16} aria-hidden="true" />
                {t('modelsPage.providerSmoke.runLive')}
              </OperationButton>
              <OperationButton
                variant="secondary"
                isOperating={dashboardFetching}
                onClick={() => { void refetchDashboard() }}
              >
                <RefreshCw size={16} aria-hidden="true" />
                {t('modelsPage.providerSmoke.refreshReadiness')}
              </OperationButton>
            </div>
            <p className="model-provider-smoke__audit-note">{t('modelsPage.providerSmoke.auditNotice')}</p>
            {liveSmokeResult && (
              <div
                className="model-provider-smoke__live-result"
                role="region"
                aria-label={t('modelsPage.providerSmoke.liveResultTitle')}
                aria-live="polite"
              >
                <div className="model-provider-smoke__live-result-header">
                  <strong>{t('modelsPage.providerSmoke.liveResultTitle')}</strong>
                  <span className={`model-provider-smoke__state model-provider-smoke__state--${liveSmokePassed ? 'pass' : 'fail'}`}>
                    <span aria-hidden="true" />
                    {liveSmokePassed ? t('modelsPage.providerSmoke.livePassed') : t('modelsPage.providerSmoke.liveFailed')}
                  </span>
                </div>
                <dl>
                  <div>
                    <dt>{t('modelsPage.providerSmoke.provider')}</dt>
                    <dd>{displayProvider(t, liveProviderEvidence?.provider || liveSmokeResult.provider)}</dd>
                  </div>
                  <div>
                    <dt>{t('modelsPage.providerSmoke.model')}</dt>
                    <dd>{displayModel(t, liveProviderEvidence?.model || liveSmokeResult.model)}</dd>
                  </div>
                  <div>
                    <dt>{t('modelsPage.providerSmoke.tokenCounts')}</dt>
                    <dd>{liveProviderUsage
                      ? `${formatLocaleNumber(liveProviderUsage.inputTokens ?? 0)} / ${formatLocaleNumber(liveProviderUsage.outputTokens ?? 0)} / ${formatLocaleNumber(liveProviderUsage.totalTokens ?? 0)}`
                      : t('modelsPage.providerSmoke.missing')}</dd>
                  </div>
                  <div>
                    <dt>{t('modelsPage.providerSmoke.source')}</dt>
                    <dd>{displayUsageSource(t, liveProviderUsage?.source)}</dd>
                  </div>
                </dl>
                {liveSmokeResult.error ? <details className="model-provider-smoke__live-error"><summary>{t('common.technicalDetails')}</summary><code>{liveSmokeResult.error}</code></details> : null}
                <p className="model-provider-smoke__readiness-state">
                  {liveSmokeAggregated
                    ? t('modelsPage.providerSmoke.readinessAggregated')
                    : t('modelsPage.providerSmoke.readinessPending')}
                </p>
              </div>
            )}
          </section>
          )}
          <details className="model-provider-smoke__evidence">
            <summary>
              <span>{t('modelsPage.providerSmoke.evidenceTitle')}</span>
              <span>{providerSmokeReady
                ? t('modelsPage.providerSmoke.statusReady')
                : t('modelsPage.providerSmoke.statusNeedsReview')}</span>
            </summary>
            <dl className="model-provider-smoke__gate-summary">
            <div>
              <dt>{t('modelsPage.providerSmoke.gateStatus')}</dt>
              <dd>{describeProviderEvidenceValue(providerGate?.status ?? releaseReadiness?.status, t)
                || t('modelsPage.providerSmoke.missing')}</dd>
            </div>
            <div>
              <dt>{t('modelsPage.providerSmoke.gateReports')}</dt>
              <dd>
                {providerReports.length > 0
                  ? providerReports.map((report, index) => (
                    <span key={`${report}-${index}`}>
                      {index > 0 && ', '}
                      {describeProviderEvidenceValue(report, t)}
                    </span>
                  ))
                  : t('modelsPage.providerSmoke.noneMissing')}
              </dd>
            </div>
            <div>
              <dt>{t('modelsPage.providerSmoke.gateMissingEnv')}</dt>
              <dd>{providerMissingEnv.length > 0 ? providerMissingEnv.join(', ') : t('modelsPage.providerSmoke.noneMissing')}</dd>
            </div>
            <div>
              <dt>{t('modelsPage.providerSmoke.gateMode')}</dt>
              <dd>{describeProviderEvidenceValue(providerGateItem?.mode, t) || t('modelsPage.providerSmoke.missing')}</dd>
            </div>
            <div>
              <dt>{t('modelsPage.providerSmoke.gateScope')}</dt>
              <dd>{describeProviderEvidenceValue(providerGateItem?.scope, t) || t('modelsPage.providerSmoke.missing')}</dd>
            </div>
            <div>
              <dt>{t('modelsPage.providerSmoke.gateArtifact')}</dt>
              <dd>{providerGateItem?.artifact ?? t('modelsPage.providerSmoke.missing')}</dd>
            </div>
            </dl>
            <dl className="model-provider-smoke__grid">
            <div>
              <dt>{t('modelsPage.providerSmoke.provider')}</dt>
              <dd>{backendProviderIntegration?.provider ? displayProvider(t, backendProviderIntegration.provider) : t('modelsPage.providerSmoke.missing')}</dd>
            </div>
            <div>
              <dt>{t('modelsPage.providerSmoke.model')}</dt>
              <dd>{backendProviderIntegration?.model ? displayModel(t, backendProviderIntegration.model) : t('modelsPage.providerSmoke.missing')}</dd>
            </div>
            {hasConfiguredFallback && configuredProvider && (
              <div>
                <dt>{t('modelsPage.providerSmoke.configuredProvider')}</dt>
                <dd>{displayProvider(t, configuredProvider)}</dd>
              </div>
            )}
            {hasConfiguredFallback && configuredModel && (
              <div>
                <dt>{t('modelsPage.providerSmoke.configuredModel')}</dt>
                <dd>{displayModel(t, configuredModel)}</dd>
              </div>
            )}
            <div>
              <dt>{t('modelsPage.providerSmoke.usage')}</dt>
              <dd>
                {providerUsage
                  ? `${t('modelsPage.providerSmoke.inputTokens')}: ${formatLocaleNumber(providerUsage.inputTokens ?? 0)}, ${t('modelsPage.providerSmoke.outputTokens')}: ${formatLocaleNumber(providerUsage.outputTokens ?? 0)}, ${t('modelsPage.providerSmoke.totalTokens')}: ${formatLocaleNumber(providerUsage.totalTokens ?? 0)}`
                  : t('modelsPage.providerSmoke.missing')}
              </dd>
            </div>
            <div>
              <dt>{t('modelsPage.providerSmoke.source')}</dt>
              <dd>{displayUsageSource(t, providerUsage?.source)}</dd>
            </div>
            <div>
              <dt>{t('modelsPage.providerSmoke.usagePresent')}</dt>
              <dd>{providerUsage?.present ? t('common.yes') : t('common.no')}</dd>
            </div>
            <div>
              <dt>{t('modelsPage.providerSmoke.breakdown')}</dt>
              <dd>{providerUsage?.totalMatchesBreakdown ? t('common.yes') : t('common.no')}</dd>
            </div>
            <div>
              <dt>{t('modelsPage.providerSmoke.requiredChecks')}</dt>
              <dd>{providerChecks || t('modelsPage.providerSmoke.missing')}</dd>
            </div>
            {localProviderNoKey && (
              <div>
                <dt>{t('modelsPage.providerSmoke.credentialMode')}</dt>
                <dd>
                  <span className="model-provider-smoke__state model-provider-smoke__state--pass">
                    <span aria-hidden="true" />
                    {t('modelsPage.providerSmoke.localProviderNoKey')}
                  </span>
                </dd>
              </div>
            )}
            <div>
              <dt>{t('modelsPage.providerSmoke.contract')}</dt>
              <dd>
                {missingProviderSmokeChecks.length === 0
                  ? t('modelsPage.providerSmoke.contractReady')
                  : t('modelsPage.providerSmoke.contractMissing', {
                      fields: missingProviderSmokeChecks.join(', '),
                    })}
              </dd>
            </div>
            </dl>
            {showProviderSmokeRemediation && (
              <section
                className="model-provider-smoke__remediation"
                aria-label={t('modelsPage.providerSmoke.remediationTitle')}
              >
              <div>
                <h3>{t('modelsPage.providerSmoke.remediationTitle')}</h3>
                <p>{t('modelsPage.providerSmoke.remediationDesc')}</p>
              </div>
              <dl>
                <div>
                  <dt>{t('modelsPage.providerSmoke.remediationMissing')}</dt>
                  <dd>
                    <ul>
                      {missingProviderSmokeChecks.map((check) => (
                        <li key={check}>{check}</li>
                      ))}
                    </ul>
                  </dd>
                </div>
              </dl>
              </section>
            )}
          </details>
        </section>
      )}

      <ModelDetailDrawer
        model={selected}
        alerts={alertRules}
        onClose={() => setSelectedName(null)}
      />
    </div>
  )
}

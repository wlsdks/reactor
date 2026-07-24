import { useTranslation } from 'react-i18next'
import './HealthPage.css'
import { HelpHint, LoadingSpinner, PageHeader, SectionErrorBoundary } from '../shared/ui'
import { WorkspaceUnavailable } from '../shared/ui/WorkspaceUnavailable'
import { useHealthOperations } from '../features/health/useHealthOperations'
import type { DoctorCheck, DoctorSection, DoctorStatus } from '../features/doctor/types'
import { formatRelativeTimeKo } from '../shared/lib/formatRelativeTimeKo'
import { deriveDoctorDisplayStatus } from '../features/doctor/healthStatus'
import { formatMetricValue, formatPercent } from '../shared/lib/formatters'
import { getErrorMessage } from '../shared/lib/getErrorMessage'

function sectionLabel(name: string): string {
  const labels: Record<string, string> = {
    'FastAPI Runtime': '서비스 응답',
    'Runtime Settings': '운영 설정',
    'RAG Store': '지식 검색 자료',
  }
  return labels[name] ?? '추가 연결 상태'
}

function sectionHelp(name: string): string | null {
  const descriptions: Record<string, string> = {
    'FastAPI Runtime': 'FastAPI는 Reactor의 요청을 받는 백엔드 기술입니다. 이 항목은 관리 화면과 외부 연동이 사용할 서버가 응답하는지 확인합니다.',
    'Runtime Settings': '런타임 설정은 서버를 다시 배포하지 않고 바꿀 수 있는 운영 기준입니다. 이 항목은 해당 설정을 읽고 저장할 공간이 연결됐는지 확인합니다.',
    'RAG Store': 'RAG는 질문과 관련된 내부 자료를 먼저 찾아 답변에 근거로 사용하는 방식입니다. 이 항목은 검색할 문서와 조각을 저장하는 공간을 확인합니다.',
  }
  return descriptions[name] ?? null
}

function checkLabel(check: DoctorCheck): string {
  const labels: Record<string, string> = {
    application: '서버 응답',
    store: '연결 상태',
    stats: '저장된 자료',
    connection: '연결 상태',
  }
  return labels[check.name] ?? '확인 결과'
}

function checkDetail(detail: string): string {
  const labels: Record<string, string> = {
    'FastAPI router is responding': '관리 화면이 사용하는 서버가 정상적으로 응답합니다.',
    'runtime settings store is configured': '운영 설정을 읽고 저장할 공간이 연결되어 있습니다.',
    'runtime settings store is not configured': '운영 설정을 저장할 공간이 준비되지 않았습니다.',
    'runtime settings diagnostics failed': '운영 설정의 연결 상태를 확인하지 못했습니다.',
    'RAG diagnostics persistence is not configured': '지식 검색 자료를 저장할 공간이 준비되지 않았습니다.',
    'RAG diagnostics failed': '지식 검색 자료의 연결 상태를 확인하지 못했습니다.',
    'RAG store is not configured': '지식 검색 자료를 저장할 공간이 준비되지 않았습니다.',
    'runtime available': '서비스가 정상적으로 응답하는지 확인했습니다.',
    'not configured': '연결에 필요한 설정이 아직 준비되지 않았습니다.',
  }
  const ragStats = /^documents=(\d+), chunks=(\d+)$/.exec(detail)
  if (ragStats) return `문서 ${ragStats[1]}개 · 청크 ${ragStats[2]}개가 수집되어 있습니다.`
  return labels[detail] ?? '세부 상태를 확인할 수 없습니다. 다시 점검해 주세요.'
}

function statusLabel(status: DoctorStatus): string {
  const labels: Record<DoctorStatus, string> = {
    OK: '정상',
    WARN: '주의',
    ERROR: '장애',
    SKIPPED: '미구성',
  }
  return labels[status]
}

function DoctorSectionRow({ section }: { section: DoctorSection }) {
  const help = sectionHelp(section.name)
  const checks = section.checks.length > 0
    ? section.checks
    : [{ name: 'connection', status: section.status, detail: section.message }]
  return (
    <article className="health-diagnostics__row">
      <div className="health-diagnostics__identity">
        <span className={`health-status-dot is-${section.status.toLowerCase()}`} aria-hidden="true" />
        <div>
          <div className="health-diagnostics__title"><h3>{sectionLabel(section.name)}</h3>{help ? <HelpHint title={sectionLabel(section.name)} label={help} /> : null}</div>
          <span>{statusLabel(section.status)}</span>
        </div>
      </div>
      <div className="health-diagnostics__checks">
        {checks.map((check, index) => (
          <div key={`${check.name}-${index}`}>
            <span className={`health-check-state is-${check.status.toLowerCase()}`} aria-label={statusLabel(check.status)} />
            <strong>{checkLabel(check)}</strong>
            <span>{checkDetail(check.detail)}</span>
          </div>
        ))}
      </div>
    </article>
  )
}

function HealthInformationState({ title, description }: { title: string; description: string }) {
  return (
    <div className="health-information-state">
      <span className="health-information-state__dot" aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <span>{description}</span>
      </div>
    </div>
  )
}

function HealthDataState({
  title,
  description,
  retryLabel,
  onRetry,
}: {
  title: string
  description: string
  retryLabel: string
  onRetry: () => void
}) {
  return (
    <div className="health-data-state" role="status">
      <div>
        <strong>{title}</strong>
        <span>{description}</span>
      </div>
      <button className="btn btn-secondary btn-sm" type="button" onClick={onRetry}>
        {retryLabel}
      </button>
    </div>
  )
}

export function HealthPage() {
  const { t } = useTranslation()
  const {
    doctorQuery,
    platformQuery,
    refresh,
    evaluateAlerts,
    invalidateCache,
    actionPending,
    actionError,
  } = useHealthOperations()

  const doctor = doctorQuery.data
  const platform = platformQuery.data
  const isLoading = doctorQuery.isLoading || platformQuery.isLoading
  const isRefreshing = doctorQuery.isFetching || platformQuery.isFetching
  const failedCount = Number(doctorQuery.isError) + Number(platformQuery.isError)
  const allFailed = failedCount === 2
  const loadFailureDetail = allFailed
    ? [doctorQuery.error, platformQuery.error]
      .filter((error) => error != null)
      .map((error) => getErrorMessage(error))
      .join('\n') || null
    : null
  const sections = doctor?.sections ?? []
  const confirmedDoctorStatus = deriveDoctorDisplayStatus(doctor)
  const passedSections = sections.filter((section) => section.status === 'OK').length
  const attentionSections = sections.length - passedSections
  const diagnosticSections = doctor ? [...doctor.sections].sort((left, right) => {
    const priority: Record<DoctorStatus, number> = { ERROR: 0, WARN: 1, SKIPPED: 2, OK: 3 }
    return priority[left.status] - priority[right.status]
  }) : []
  const summaryStatus = doctorQuery.isError || !confirmedDoctorStatus ? 'unknown' : confirmedDoctorStatus.toLowerCase()
  const summaryLabel = doctorQuery.isError || !confirmedDoctorStatus
    ? t('healthPage.statusUnknown')
    : statusLabel(confirmedDoctorStatus)
  const summaryDescription = doctorQuery.isError || !confirmedDoctorStatus
    ? t('healthPage.unknownSummary')
    : attentionSections > 0
      ? t('healthPage.attentionSummary', { count: attentionSections })
      : t('healthPage.healthySummary')
  const pipelineMetrics = platform?.pipelineMetricsAvailable ? [
    {
      id: 'buffer',
      label: t('healthPage.processingQueue'),
      value: `${platform.pipelineBufferUsage}%`,
      detail: t('healthPage.signals.bufferDetail'),
      status: 'neutral',
    },
    {
      id: 'latency',
      label: t('healthPage.storageDelay'),
      value: `${platform.pipelineWriteLatencyMs}ms`,
      detail: t('healthPage.signals.latencyDetail'),
      status: 'neutral',
    },
    {
      id: 'drops',
      label: t('healthPage.missingEvents'),
      value: formatPercent(platform.pipelineDropRate),
      detail: platform.pipelineDropRate > 0 ? t('healthPage.signals.dropAttention') : t('healthPage.signals.dropHealthy'),
      status: platform.pipelineDropRate > 0 ? 'error' : 'ok',
    },
  ] : []
  const cacheHits = platform ? platform.cacheExactHits + platform.cacheSemanticHits : 0
  const cacheAttempts = cacheHits + (platform?.cacheMisses ?? 0)
  const cacheMetric = platform?.responseCacheEnabled ? {
    id: 'cache',
    label: t('healthPage.cacheHitRate'),
    value: cacheAttempts > 0 ? formatPercent(cacheHits / cacheAttempts) : t('healthPage.noCacheActivity'),
    detail: t('healthPage.signals.cacheDetail', {
      hits: formatMetricValue(cacheHits),
      misses: formatMetricValue(platform.cacheMisses),
    }),
    status: 'neutral',
  } : null
  const healthSignals = cacheMetric ? [...pipelineMetrics, cacheMetric] : pipelineMetrics

  return (
    <SectionErrorBoundary name="health-page">
      <div className="page health-page">
        <PageHeader
          title={t('healthPage.title')}
          description={t('healthPage.description')}
          actions={!failedCount ? (
            <button className="btn btn-secondary" type="button" onClick={() => void refresh()} disabled={isLoading}>
              {isLoading ? <LoadingSpinner size="sm" /> : t('common.refresh')}
            </button>
          ) : undefined}
        />

        {isLoading ? (
          <div className="health-page__loading"><LoadingSpinner /></div>
        ) : allFailed ? (
          <WorkspaceUnavailable
            title={t('healthPage.loadErrorTitle')}
            description={t('healthPage.loadErrorDescription')}
            retryLabel={t('common.retry')}
            retryingLabel={t('common.retrying')}
            onRetry={refresh}
            isRetrying={isRefreshing}
            guide={{
              title: t('healthPage.recoveryGuideTitle'),
              steps: [
                t('healthPage.recoveryCheckAccount'),
                t('healthPage.recoveryCheckConnection'),
                t('healthPage.recoveryRetry'),
              ],
              technicalLabel: t('common.technicalDetails'),
              technicalDetail: loadFailureDetail,
            }}
          />
        ) : (
          <>
            {failedCount > 0 && (
              <div className="health-page__notice" role="status">
                <div><strong>{t('healthPage.partialErrorTitle')}</strong><span>{t('healthPage.partialErrorDescription')}</span></div>
                <button className="btn btn-secondary btn-sm" type="button" onClick={() => void refresh()}>{t('common.retry')}</button>
              </div>
            )}
            {actionError && (
              <div className="health-page__notice health-page__notice--error" role="alert">
                <div><strong>{t('healthPage.actionErrorTitle')}</strong><span>{t('healthPage.actionErrorDescription')}</span></div>
                <button className="btn btn-secondary btn-sm" type="button" onClick={() => void refresh()}>{t('common.refresh')}</button>
              </div>
            )}

            <section className={`health-summary is-${summaryStatus}`} aria-label={t('healthPage.summaryLabel')}>
              <div className="health-summary__decision">
                <span className="health-summary__status-dot" aria-hidden="true" />
                <div>
                  <span>{t('platformAdminPage.healthStatus')}</span>
                  <strong>{summaryLabel}</strong>
                  <p>{summaryDescription}</p>
                </div>
              </div>
              <dl className="health-summary__facts">
                <div><dt>{t('healthPage.diagnosticChecks')}</dt><dd>{doctorQuery.isError ? '—' : `${passedSections}/${sections.length}`}</dd></div>
                <div><dt>{t('platformAdminPage.activeAlerts')}</dt><dd>{platformQuery.isError ? '—' : t('healthPage.alertCount', { value: formatMetricValue(platform?.activeAlerts ?? 0) })}</dd></div>
                <div><dt>{t('healthPage.lastChecked')}</dt><dd>{doctor?.generatedAt ? formatRelativeTimeKo(doctor.generatedAt) : '—'}</dd></div>
              </dl>
            </section>

            <section className="health-page__section" aria-labelledby="health-diagnostics-title">
              <div className="health-page__section-heading">
                <div><h2 id="health-diagnostics-title">{t('healthPage.diagnosticsTitle')}</h2><p>{t('healthPage.diagnosticsDescription')}</p></div>
              </div>
              {doctorQuery.isError ? (
                <HealthDataState
                  title={t('healthPage.doctorLoadError')}
                  description={t('healthPage.doctorLoadErrorDescription')}
                  retryLabel={t('healthPage.retryStatus')}
                  onRetry={() => void refresh()}
                />
              ) : doctor && doctor.sections.length > 0 ? (
                <div className="health-diagnostics">{diagnosticSections.map((section) => <DoctorSectionRow key={section.name} section={section} />)}</div>
              ) : (
                <HealthDataState
                  title={t('healthPage.noDiagnostics')}
                  description={t('healthPage.noDiagnosticsDescription')}
                  retryLabel={t('healthPage.retryStatus')}
                  onRetry={() => void refresh()}
                />
              )}
            </section>

            <section className="health-page__section" aria-labelledby="health-pipeline-title">
              <div className="health-page__section-heading">
                <div><h2 id="health-pipeline-title">{t('healthPage.pipelineTitle')}</h2><p>{t('healthPage.pipelineDescription')}</p></div>
              </div>
              {platformQuery.isError ? (
                <HealthDataState
                  title={t('healthPage.platformLoadError')}
                  description={t('healthPage.platformLoadErrorDescription')}
                  retryLabel={t('healthPage.retryStatus')}
                  onRetry={() => void refresh()}
                />
              ) : platform ? (
                <div className="health-pipeline">
                  {!platform.pipelineMetricsAvailable && (
                    <HealthInformationState
                      title={t('healthPage.pipelineUnavailableTitle')}
                      description={t('healthPage.pipelineUnavailableDescription')}
                    />
                  )}
                  {!platform.responseCacheEnabled && (
                    <HealthInformationState
                      title={t('healthPage.cacheUnavailableTitle')}
                      description={t('healthPage.cacheUnavailableDescription')}
                    />
                  )}
                  {healthSignals.length > 0 && <div role="list">{healthSignals.map((metric) => (
                    <div key={metric.id} className={`health-pipeline__row is-${metric.status}`} role="listitem">
                      <span className="health-pipeline__state" aria-hidden="true" />
                      <strong>{metric.label}</strong>
                      <span>{metric.detail}</span>
                      <b>{metric.value}</b>
                    </div>
                  ))}</div>}
                </div>
              ) : null}
            </section>

            <section className="health-page__section health-operations" aria-labelledby="health-operations-title">
              <div className="health-page__section-heading">
                <div><h2 id="health-operations-title">{t('healthPage.operationsTitle')}</h2><p>{t('healthPage.operationsDescription')}</p></div>
              </div>
              <div className="health-operations__actions">
                <button className="btn btn-primary" type="button" onClick={evaluateAlerts} disabled={actionPending || platformQuery.isError}>
                  {actionPending ? <LoadingSpinner size="sm" /> : t('platformAdminPage.evaluateAlerts')}
                </button>
                <button className="btn btn-secondary" type="button" onClick={invalidateCache} disabled={actionPending || platformQuery.isError}>
                  {actionPending ? <LoadingSpinner size="sm" /> : t('platformAdminPage.invalidateCache')}
                </button>
              </div>
            </section>
          </>
        )}
      </div>
    </SectionErrorBoundary>
  )
}

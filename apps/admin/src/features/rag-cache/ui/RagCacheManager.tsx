import { lazy, Suspense, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import {
  PageHeader,
  LoadingSpinner,
  SectionErrorBoundary,
  SkeletonCard,
  SkeletonChart,
} from '../../../shared/ui'
import { useToastStore } from '../../../shared/store/toast.store'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { usePageHelp } from '../../../shared/lib/usePageHelp'
import { formatPercent } from '../../../shared/lib/formatters'
import { formatLocaleNumber } from '../../../shared/lib/intl'
import * as ragCacheApi from '../api'
import { RagPolicyEditor } from './RagPolicyEditor'
import { RagCandidatesTab } from './RagCandidatesTab'
import { InvalidateCacheModal } from './InvalidateCacheModal'
import { RagQuickSearch } from './RagQuickSearch'
import { RagCacheInsightBar } from './RagCacheInsightBar'
import { CacheRuntimeControls } from './CacheRuntimeControls'
import { RagAnswerContractPanel } from './RagAnswerContractPanel'
import { RagGroundedAnswerProbe } from './RagGroundedAnswerProbe'

// Lazy-load analytics tab — pulls recharts via vendor-charts. The other 3
// tabs (cache/candidates/rag) cover the common operator workflow, so this
// keeps vendor-charts off the default render path.
const RagAnalyticsTab = lazy(() =>
  import('./RagAnalyticsTab').then((m) => ({ default: m.RagAnalyticsTab })),
)

type TabKey = 'cache' | 'candidates' | 'rag' | 'policy' | 'analytics'

const tabKeys = new Set<TabKey>(['cache', 'candidates', 'rag', 'policy', 'analytics'])

function parseTab(value: string | null): TabKey | null {
  return value && tabKeys.has(value as TabKey) ? (value as TabKey) : null
}

export function RagCacheManager() {
  const { t } = useTranslation()
  void t('ragCachePage.helpOverlay', { returnObjects: true })
  usePageHelp({ helpKey: 'ragCachePage.helpOverlay' })
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()

  const [manualTab, setManualTab] = useState<TabKey | null>(null)
  const userTouchedTabRef = useRef(false)
  const candidatesTabRef = useRef<HTMLButtonElement>(null)
  const [showInvalidateConfirm, setShowInvalidateConfirm] = useState(false)

  // --- Cache data ---
  const { data: cacheStats, isLoading: loadingCache, error: cacheError } = useQuery({
    queryKey: queryKeys.ragCache.stats(),
    queryFn: async () => await ragCacheApi.getCacheStats() ?? null,
  })

  // --- RAG data ---
  const { data: vectorStoreStats, isLoading: loadingVectorStore } = useQuery({
    queryKey: queryKeys.ragCache.vectorStore(),
    queryFn: ragCacheApi.getVectorStoreStats,
  })

  // --- RAG policy (for insight bar status) ---
  // opt-in 기능 (reactor.rag.ingestion.dynamic.enabled=true). 미활성 환경에서는
  // 백엔드가 404 → 브라우저 console 에러 방지 위해 404 는 null 로 swallow.
  const { data: ragPolicy } = useQuery({
    queryKey: queryKeys.ragCache.policy(),
    queryFn: async () => {
      try {
        return await ragCacheApi.getRagPolicy()
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        if (msg.includes('HTTP 404') || msg.includes('404')) return null
        throw e
      }
    },
    retry: false,
  })

  // --- Candidate release evidence for smart default, badges, and handoff proof ---
  const { data: releaseCandidates } = useQuery({
    queryKey: queryKeys.ragCache.candidates(),
    queryFn: async () => {
      try {
        return await ragCacheApi.listRagCandidates()
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        if (msg.includes('HTTP 404') || msg.includes('404')) return []
        throw e
      }
    },
    retry: false,
  })
  const pendingCandidatesCount =
    releaseCandidates?.filter((candidate) => candidate.status === 'PENDING').length ?? 0

  // Smart default tab — computed during render:
  //   - If user has manually clicked any tab, respect that choice.
  //   - Otherwise, wait until pending candidate data resolves, then pick
  //     'candidates' (if any pending) or 'rag' (user priority #2).
  //   - Before data loads, fall back to 'rag' so the layout does not flicker.
  const smartDefaultTab: TabKey =
    releaseCandidates === undefined
      ? 'rag'
      : pendingCandidatesCount > 0
        ? 'candidates'
        : 'rag'
  const queryTab = parseTab(searchParams.get('tab'))
  const activeTab: TabKey = manualTab ?? queryTab ?? smartDefaultTab

  function selectTab(tab: TabKey) {
    userTouchedTabRef.current = true
    setManualTab(tab)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('tab', tab)
      return next
    }, { replace: true })
  }

  // Insight bar CTA handler — switch to the candidates tab AND scroll the
  // tablist into view while moving focus to the candidates tab button so
  // keyboard users land in the right place.
  function jumpToCandidates() {
    selectTab('candidates')
    // Defer to next frame so the tab button is guaranteed to exist and be
    // in its active state (in case it was rendered conditionally).
    requestAnimationFrame(() => {
      const node = candidatesTabRef.current
      if (!node) return
      node.scrollIntoView({ block: 'start', behavior: 'smooth' })
      node.focus({ preventScroll: true })
    })
  }

  // --- Mutations ---
  const invalidateMutation = useMutation({
    mutationFn: ragCacheApi.invalidateCache,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ragCache.stats() })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
    },
    onError: (err: Error) => {
      useToastStore.getState().addToast({ type: 'error', message: err.message })
    },
  })

  function handleInvalidate() {
    invalidateMutation.mutate(undefined, {
      onSettled: () => {
        setShowInvalidateConfirm(false)
      },
    })
  }

  function handleRefresh() {
    queryClient.invalidateQueries({ queryKey: queryKeys.ragCache.all() })
    useToastStore.getState().addToast({ type: 'success', message: t('common.toast.refreshed') })
  }

  const isLoadingCacheTab = loadingCache
  const isLoadingRagTab = loadingVectorStore

  return (
    <div className="page">
      <PageHeader
        title={t('nav.ragCache')}
        description={t('nav.help.ragCache')}
      />

      <RagCacheInsightBar
        cacheStats={cacheStats ?? null}
        vectorStoreStats={vectorStoreStats ?? null}
        ragPolicy={ragPolicy ?? null}
        pendingCandidatesCount={pendingCandidatesCount}
        cacheError={!!cacheError}
        onJumpToCandidates={jumpToCandidates}
        onRefresh={handleRefresh}
      />

      <div className="detail-tabs rag-cache-tabs" role="tablist" aria-label={t('ragCachePage.tablistLabel')}>
        <button
          id="rag-cache-tab-cache"
          className={`tab-btn${activeTab === 'cache' ? ' active' : ''}`}
          role="tab"
          type="button"
          aria-selected={activeTab === 'cache'}
          aria-controls="rag-cache-tabpanel-cache"
          onClick={() => selectTab('cache')}
        >
          {t('ragCachePage.tabCache')}
        </button>
        <button
          id="rag-cache-tab-candidates"
          ref={candidatesTabRef}
          className={`tab-btn${activeTab === 'candidates' ? ' active' : ''}`}
          role="tab"
          type="button"
          aria-selected={activeTab === 'candidates'}
          aria-controls="rag-cache-tabpanel-candidates"
          onClick={() => selectTab('candidates')}
        >
          {t('ragCachePage.tabCandidates')}
          {pendingCandidatesCount > 0 && (
            <span className="rag-tab-badge" aria-label={t('ragCachePage.insightBar.pendingLabel')}>
              {pendingCandidatesCount}
            </span>
          )}
        </button>
        <button
          id="rag-cache-tab-rag"
          className={`tab-btn${activeTab === 'rag' ? ' active' : ''}`}
          role="tab"
          type="button"
          aria-selected={activeTab === 'rag'}
          aria-controls="rag-cache-tabpanel-rag"
          onClick={() => selectTab('rag')}
        >
          {t('ragCachePage.tabRag')}
        </button>
        <button
          id="rag-cache-tab-policy"
          className={`tab-btn${activeTab === 'policy' ? ' active' : ''}`}
          role="tab"
          type="button"
          aria-selected={activeTab === 'policy'}
          aria-controls="rag-cache-tabpanel-policy"
          onClick={() => selectTab('policy')}
        >
          {t('ragCachePage.tabPolicy')}
        </button>
        <button
          id="rag-cache-tab-analytics"
          className={`tab-btn${activeTab === 'analytics' ? ' active' : ''}`}
          role="tab"
          type="button"
          aria-selected={activeTab === 'analytics'}
          aria-controls="rag-cache-tabpanel-analytics"
          onClick={() => selectTab('analytics')}
        >
          {t('ragCachePage.tabAnalytics')}
        </button>
      </div>

      {/* ===== Cache Tab ===== */}
      {activeTab === 'cache' && (
        <div id="rag-cache-tabpanel-cache" role="tabpanel" aria-labelledby="rag-cache-tab-cache">
        <SectionErrorBoundary name="rag-cache-tab-cache">
          {isLoadingCacheTab ? (
            // Stat-row + body shape mirrors the resolved layout (4 stat cards
            // followed by a runtime-controls panel and an actions panel).
            <div>
              <div className="stat-row" style={{ marginBottom: 'var(--space-4)' }}>
                <SkeletonCard count={4} height={72} />
              </div>
              <SkeletonCard height={160} />
            </div>
          ) : (
            <>
              {/* R454/R452: Runtime kill-switch & precise invalidate — 인시던트 대응 최상단 배치 */}
              <CacheRuntimeControls />

              <section className="cache-usage-summary" aria-labelledby="cache-usage-title">
                <div>
                  <h2 id="cache-usage-title" className="section-title">{t('ragCachePage.usageTitle')}</h2>
                  <p>{t('ragCachePage.usageDescription')}</p>
                </div>
                <dl className="rag-summary-list">
                  <div><dt>{t('ragCachePage.hitRate')}</dt><dd><strong>{formatPercent(cacheStats?.hitRate)}</strong></dd></div>
                  <div><dt>{t('ragCachePage.exactHits')}</dt><dd><strong>{cacheStats?.totalExactHits ?? '-'}</strong></dd></div>
                  <div><dt>{t('ragCachePage.semanticHits')}</dt><dd><strong>{cacheStats?.totalSemanticHits ?? '-'}</strong></dd></div>
                  <div><dt>{t('ragCachePage.misses')}</dt><dd><strong>{cacheStats?.totalMisses ?? '-'}</strong></dd></div>
                </dl>
              </section>

              {/* Configuration card grid */}
              {cacheStats?.config && (
                <details className="rag-technical-details cache-technical-details">
                  <summary>{t('ragCachePage.cacheTechnicalDetails')}</summary>
                  <div className="rag-config-grid">
                    <div className="rag-config-card">
                      <span className="rag-config-card__label">{t('ragCachePage.ttl')}</span>
                      <span className="rag-config-card__value">{cacheStats.config.ttlMinutes}</span>
                      <span className="rag-config-card__desc">{t('ragCachePage.ttlDesc')}</span>
                    </div>
                    <div className="rag-config-card">
                      <span className="rag-config-card__label">{t('ragCachePage.maxSize')}</span>
                      <span className="rag-config-card__value">{formatLocaleNumber(cacheStats.config.maxSize)}</span>
                      <span className="rag-config-card__desc">{t('ragCachePage.maxSizeDesc')}</span>
                    </div>
                    <div className="rag-config-card">
                      <span className="rag-config-card__label">{t('ragCachePage.threshold')}</span>
                      <span className="rag-config-card__value">{cacheStats.config.similarityThreshold}</span>
                      <span className="rag-config-card__desc">{t('ragCachePage.thresholdDesc')}</span>
                    </div>
                    <div className="rag-config-card">
                      <span className="rag-config-card__label">{t('ragCachePage.maxCandidates')}</span>
                      <span className="rag-config-card__value">{cacheStats.config.maxCandidates}</span>
                      <span className="rag-config-card__desc">{t('ragCachePage.maxCandidatesDesc')}</span>
                    </div>
                    <div className="rag-config-card">
                      <span className="rag-config-card__label">{t('ragCachePage.temperature')}</span>
                      <span className="rag-config-card__value">{cacheStats.config.cacheableTemperature}</span>
                      <span className="rag-config-card__desc">{t('ragCachePage.temperatureDesc')}</span>
                    </div>
                  </div>
                </details>
              )}

              {/* Invalidate button */}
              <div className="cache-danger-action">
                <div>
                  <strong>{t('ragCachePage.invalidateAll')}</strong>
                  <p>{t('ragCachePage.invalidateAllDesc')}</p>
                </div>
                <button
                  className="btn btn-danger"
                  onClick={() => setShowInvalidateConfirm(true)}
                  disabled={invalidateMutation.isPending}
                >
                  {invalidateMutation.isPending
                    ? <LoadingSpinner size="sm" />
                    : t('ragCachePage.invalidateAll')}
                </button>
              </div>
            </>
          )}
        </SectionErrorBoundary>
        </div>
      )}

      {/* ===== Candidates Tab ===== */}
      {activeTab === 'candidates' && (
        <div id="rag-cache-tabpanel-candidates" role="tabpanel" aria-labelledby="rag-cache-tab-candidates">
        <SectionErrorBoundary name="rag-cache-tab-candidates">
          <RagCandidatesTab />
        </SectionErrorBoundary>
        </div>
      )}

      {/* ===== RAG Tab ===== */}
      {activeTab === 'rag' && (
        <div id="rag-cache-tabpanel-rag" role="tabpanel" aria-labelledby="rag-cache-tab-rag">
        <SectionErrorBoundary name="rag-cache-tab-rag">
          {isLoadingRagTab ? (
            // Vector store status (4 stat cards) + policy editor panel.
            <div>
              <div className="stat-row" style={{ marginBottom: 'var(--space-4)' }}>
                <SkeletonCard count={4} height={72} />
              </div>
              <SkeletonCard height={240} />
            </div>
          ) : (
            <>
              <RagAnswerContractPanel
                vectorStoreStats={vectorStoreStats ?? null}
                ragPolicy={ragPolicy ?? null}
                pendingCandidatesCount={pendingCandidatesCount}
                onJumpToCandidates={jumpToCandidates}
              />

              <RagGroundedAnswerProbe />

              {/* Quick Search */}
              <RagQuickSearch />

            </>
          )}
        </SectionErrorBoundary>
        </div>
      )}

      {/* ===== Policy Tab ===== */}
      {activeTab === 'policy' && (
        <div id="rag-cache-tabpanel-policy" role="tabpanel" aria-labelledby="rag-cache-tab-policy">
          <SectionErrorBoundary name="rag-cache-tab-policy">
            <RagPolicyEditor />
          </SectionErrorBoundary>
        </div>
      )}

      {/* ===== Analytics Tab ===== */}
      {activeTab === 'analytics' && (
        <div id="rag-cache-tabpanel-analytics" role="tabpanel" aria-labelledby="rag-cache-tab-analytics">
        <SectionErrorBoundary name="rag-cache-tab-analytics">
          <Suspense fallback={<SkeletonChart height={260} />}>
            <RagAnalyticsTab />
          </Suspense>
        </SectionErrorBoundary>
        </div>
      )}

      {/* Invalidate impact preview modal */}
      <InvalidateCacheModal
        cacheStats={cacheStats ?? null}
        isOpen={showInvalidateConfirm}
        onConfirm={handleInvalidate}
        onCancel={() => setShowInvalidateConfirm(false)}
        isPending={invalidateMutation.isPending}
      />
    </div>
  )
}

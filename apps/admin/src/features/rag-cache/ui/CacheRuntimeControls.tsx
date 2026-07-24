import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { LoadingSpinner, ConfirmDialog } from '../../../shared/ui'
import { useToastStore } from '../../../shared/store/toast.store'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { showApiErrorToast } from '../../../shared/lib/showApiErrorToast'
import * as ragCacheApi from '../api'
import type { RuntimeSetting } from '../api'

/**
 * R454/R455/R452: 캐시 운영 컨트롤.
 *
 * **Design rationale (UX persona):**
 * - 인시던트 대응 시 operator가 첫 눈에 kill switch를 찾을 수 있게 최상단 배치.
 * - 위험도별 색상 구분:
 *   - 토글(yellow, reversible)
 *   - 키 무효화(yellow, single entry)
 *   - 패턴 무효화(red, potentially many)
 * - Optimistic 토글은 안 함 — 실제 DB 반영 확인(30초 Redis TTL) 후 상태 업데이트.
 * - 모든 변경은 감사 로그 기록됨 명시 (하단 hint).
 */
export function CacheRuntimeControls() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)

  const [keyToInvalidate, setKeyToInvalidate] = useState('')
  const [patternToInvalidate, setPatternToInvalidate] = useState('')
  // Holds the pattern that is awaiting destructive-confirmation.
  // null means no dialog is open.
  const [patternPendingConfirm, setPatternPendingConfirm] = useState<string | null>(null)

  // --- Runtime settings (kill switches) ---
  const cacheEnabledQuery = useQuery({
    queryKey: queryKeys.ragCache.runtimeSetting('reactor.cache.enabled'),
    queryFn: () =>
      ragCacheApi.getRuntimeSetting('reactor.cache.enabled').catch(() => null),
  })

  const semanticEnabledQuery = useQuery({
    queryKey: queryKeys.ragCache.runtimeSetting('reactor.cache.semantic.enabled'),
    queryFn: () =>
      ragCacheApi.getRuntimeSetting('reactor.cache.semantic.enabled').catch(() => null),
  })

  const cacheEnabled = readBool(cacheEnabledQuery.data, true)
  const semanticEnabled = readBool(semanticEnabledQuery.data, true)

  const toggleMutation = useMutation({
    mutationFn: (params: { key: string; value: boolean }) =>
      ragCacheApi.updateRuntimeSetting(
        params.key, String(params.value), 'BOOLEAN', 'cache',
      ),
    onSuccess: (_res, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.ragCache.runtimeSetting(variables.key),
      })
      addToast({
        type: 'success',
        message: t('ragCachePage.runtime.toggleSaved'),
      })
    },
    onError: (err: Error, variables) => {
      showApiErrorToast(err, {
        onRetry: () => toggleMutation.mutate(variables),
      })
    },
  })

  // --- Precise invalidate mutations ---
  const keyInvalidateMutation = useMutation({
    mutationFn: (key: string) => ragCacheApi.invalidateCacheKey(key),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ragCache.stats() })
      if (res.invalidated) {
        addToast({
          type: 'success',
          message: t('ragCachePage.runtime.keyInvalidated'),
        })
        setKeyToInvalidate('')
      } else {
        addToast({
          type: 'info',
          message: t('ragCachePage.runtime.keyNotFound'),
        })
      }
    },
    onError: (err: Error, key) => {
      showApiErrorToast(err, {
        onRetry: () => keyInvalidateMutation.mutate(key),
      })
    },
  })

  const patternInvalidateMutation = useMutation({
    mutationFn: (pattern: string) => ragCacheApi.invalidateCacheByPattern(pattern),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ragCache.stats() })
      addToast({
        type: 'success',
        message: t('ragCachePage.runtime.invalidateCountMsg', {
          count: res.invalidatedCount,
        }),
      })
      setPatternToInvalidate('')
    },
    onError: (err: Error, pattern) => {
      showApiErrorToast(err, {
        onRetry: () => patternInvalidateMutation.mutate(pattern),
      })
    },
  })

  function handleToggle(key: string, currentValue: boolean) {
    toggleMutation.mutate({ key, value: !currentValue })
  }

  function handleKeySubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = keyToInvalidate.trim()
    if (!trimmed) return
    keyInvalidateMutation.mutate(trimmed)
  }

  function handlePatternSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = patternToInvalidate.trim()
    if (!trimmed) return
    setPatternPendingConfirm(trimmed)
  }

  const loading = cacheEnabledQuery.isLoading || semanticEnabledQuery.isLoading

  return (
    <section className="cache-operations" aria-labelledby="cache-operations-title">
      <div className="cache-operations__header">
        <div>
          <h2 id="cache-operations-title" className="section-title">
            {t('ragCachePage.runtime.title')}
          </h2>
          <p>{t('ragCachePage.runtime.description')}</p>
        </div>
      </div>

      {loading && <LoadingSpinner size="sm" />}

      {!loading && (
        <>
          {/* Kill Switches */}
          <div className="cache-operations__toggles">
            <ToggleRow
              label={t('ragCachePage.runtime.cacheEnabled')}
              description={t('ragCachePage.runtime.cacheEnabledDesc')}
              checked={cacheEnabled}
              onChange={() => handleToggle('reactor.cache.enabled', cacheEnabled)}
              loading={toggleMutation.isPending}
              tone="warning"
            />
            <ToggleRow
              label={t('ragCachePage.runtime.semanticEnabled')}
              description={t('ragCachePage.runtime.semanticEnabledDesc')}
              checked={semanticEnabled}
              onChange={() => handleToggle('reactor.cache.semantic.enabled', semanticEnabled)}
              loading={toggleMutation.isPending}
              tone="warning"
            />
          </div>

          {/* Precise Invalidate */}
          <details className="cache-operations__cleanup">
            <summary>{t('ragCachePage.runtime.preciseInvalidate')}</summary>
            <p>{t('ragCachePage.runtime.preciseInvalidateDesc')}</p>

            {/* Single key */}
            <form onSubmit={handleKeySubmit} style={{ marginBottom: 'var(--space-3)' }}>
              <div className="form-group">
                <label htmlFor="cache-key-input">
                  {t('ragCachePage.runtime.singleKey')}
                </label>
                <div className="cache-operations__input-row">
                  <input
                    id="cache-key-input"
                    type="text"
                    value={keyToInvalidate}
                    onChange={(e) => setKeyToInvalidate(e.target.value)}
                    placeholder={t('ragCachePage.runtime.keyPlaceholder')}
                  />
                  <button
                    type="submit"
                    className="btn btn-secondary"
                    disabled={!keyToInvalidate.trim() || keyInvalidateMutation.isPending}
                  >
                    {keyInvalidateMutation.isPending
                      ? <LoadingSpinner size="sm" />
                      : t('ragCachePage.runtime.invalidateKey')}
                  </button>
                </div>
              </div>
            </form>

            {/* Pattern (dangerous) */}
            <form onSubmit={handlePatternSubmit}>
              <div className="form-group">
                <label htmlFor="cache-pattern-input">
                  {t('ragCachePage.runtime.pattern')}
                </label>
                <div className="cache-operations__input-row">
                  <input
                    id="cache-pattern-input"
                    type="text"
                    value={patternToInvalidate}
                    onChange={(e) => setPatternToInvalidate(e.target.value)}
                    placeholder={t('ragCachePage.runtime.patternPlaceholder')}
                  />
                <button
                  type="submit"
                  className="btn btn-danger"
                  disabled={!patternToInvalidate.trim() || patternInvalidateMutation.isPending}
                >
                  {patternInvalidateMutation.isPending
                    ? <LoadingSpinner size="sm" />
                    : t('ragCachePage.runtime.invalidatePattern')}
                </button>
              </div>
              <p className="cache-operations__hint">
                {t('ragCachePage.runtime.patternHint')}
              </p>
              </div>
            </form>
          </details>
        </>
      )}

      {patternPendingConfirm !== null && (
        <ConfirmDialog
          title={t('ragCachePage.runtime.patternDeleteConfirmTitle')}
          message={t('ragCachePage.runtime.patternDeleteConfirm', {
            pattern: patternPendingConfirm,
          })}
          danger
          onConfirm={() => {
            const pattern = patternPendingConfirm
            setPatternPendingConfirm(null)
            patternInvalidateMutation.mutate(pattern)
          }}
          onCancel={() => setPatternPendingConfirm(null)}
        />
      )}
    </section>
  )
}

function readBool(setting: RuntimeSetting | null | undefined, fallback: boolean): boolean {
  if (!setting) return fallback
  return setting.value.toLowerCase() === 'true'
}

interface ToggleRowProps {
  label: string
  description: string
  checked: boolean
  onChange: () => void
  loading: boolean
  tone: 'warning' | 'danger'
}

function ToggleRow({ label, description, checked, onChange, loading }: ToggleRowProps) {
  return (
    <div className="cache-toggle-row">
      <label>
        <input
          type="checkbox"
          checked={checked}
          onChange={onChange}
          disabled={loading}
        />
        <span>{label}</span>
      </label>
      <p>{description}</p>
      {loading && <LoadingSpinner size="sm" />}
    </div>
  )
}

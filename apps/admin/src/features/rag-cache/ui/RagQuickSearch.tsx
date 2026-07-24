import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LoadingSpinner, EmptyState } from '../../../shared/ui'
import { useTableExport } from '../../../shared/lib/useTableExport'
import { STORAGE_KEYS, safeGetJson, safeSetJson } from '../../../shared/lib/safeLocalStorage'
import * as ragCacheApi from '../api'
import type { DocumentSearchResult } from '../types'

const HISTORY_LIMIT = 10

function loadHistory(): string[] {
  const parsed = safeGetJson<unknown>(STORAGE_KEYS.ragSearchHistory)
  if (!Array.isArray(parsed)) return []
  return parsed.filter((v): v is string => typeof v === 'string').slice(0, HISTORY_LIMIT)
}

function saveHistory(history: string[]): void {
  safeSetJson(STORAGE_KEYS.ragSearchHistory, history)
}

function scoreColor(score: number): string {
  if (score > 0.8) return 'var(--green)'
  if (score >= 0.5) return 'var(--yellow)'
  return 'var(--red)'
}

function toValueList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .filter((item): item is string | number => typeof item === 'string' || typeof item === 'number')
      .map(String)
      .filter(Boolean)
  }
  if (typeof value === 'string' || typeof value === 'number') return [String(value)]
  return []
}

function metadataValue(metadata: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const values = toValueList(metadata[key])
    if (values.length > 0) return values.join(', ')
  }
  return ''
}

type CitationEvidenceId = 'citationIds' | 'sourceUri' | 'documentId' | 'chunkIndex' | 'contentHash'
type CitationEvidence = { id: CitationEvidenceId, value: string }

function citationEvidence(metadata: Record<string, unknown>): CitationEvidence[] {
  const evidence: CitationEvidence[] = [
    {
      id: 'citationIds',
      value: metadataValue(metadata, ['citation_ids', 'citationIds', 'citation_id', 'citationId']),
    },
    {
      id: 'sourceUri',
      value: metadataValue(metadata, ['source_uri', 'sourceUri', 'uri']),
    },
    {
      id: 'documentId',
      value: metadataValue(metadata, ['document_id', 'documentId', 'doc_id']),
    },
    {
      id: 'chunkIndex',
      value: metadataValue(metadata, ['chunk_index', 'chunkIndex']),
    },
    {
      id: 'contentHash',
      value: metadataValue(metadata, ['content_hash', 'contentHash']),
    },
  ]
  return evidence.filter((item) => item.value)
}

function citationEvidenceLabel(id: CitationEvidenceId, t: (key: string) => string): string {
  if (id === 'citationIds') return t('ragCachePage.quickSearchExt.citationIds')
  if (id === 'sourceUri') return t('ragCachePage.quickSearchExt.sourceUri')
  if (id === 'documentId') return t('ragCachePage.quickSearchExt.documentId')
  if (id === 'chunkIndex') return t('ragCachePage.quickSearchExt.chunkIndex')
  return t('ragCachePage.quickSearchExt.contentHash')
}

function missingCitationEvidenceLabels(evidence: CitationEvidence[], t: (key: string) => string): string[] {
  const evidenceIds = new Set(evidence.map((item) => item.id))
  return [
    evidenceIds.has('citationIds') ? null : citationEvidenceLabel('citationIds', t),
    evidenceIds.has('sourceUri') ? null : citationEvidenceLabel('sourceUri', t),
  ].filter((item): item is string => Boolean(item))
}

interface ScoreBarProps {
  score: number
}

function ScoreBar({ score }: ScoreBarProps) {
  const { t } = useTranslation()
  const clamped = Math.max(0, Math.min(1, score))
  const pct = `${(clamped * 100).toFixed(1)}%`
  const color = scoreColor(score)
  return (
    <span
      className="rag-score"
      role="progressbar"
      aria-valuenow={Number(score.toFixed(3))}
      aria-valuemin={0}
      aria-valuemax={1}
      aria-label={t('ragCachePage.aria.score')}
    >
      <span className="rag-score__track">
        <span className="rag-score__value" style={{ width: pct, background: color }} />
      </span>
      <span className="rag-score__label">{score.toFixed(3)}</span>
    </span>
  )
}

export function RagQuickSearch() {
  const { t } = useTranslation()
  const [searchQuery, setSearchQuery] = useState('')
  const [searchTopK, setSearchTopK] = useState(5)
  const [searchResults, setSearchResults] = useState<DocumentSearchResult[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [history, setHistory] = useState<string[]>(() => loadHistory())
  const pendingRunRef = useRef<string | null>(null)

  // Persist history on every change
  useEffect(() => {
    saveHistory(history)
  }, [history])

  function pushHistory(query: string) {
    setHistory(prev => {
      const next = [query, ...prev.filter(q => q !== query)].slice(0, HISTORY_LIMIT)
      return next
    })
  }

  async function runSearch(query: string, topK: number) {
    const trimmed = query.trim()
    if (!trimmed) return
    setSearching(true)
    try {
      const results = await ragCacheApi.searchDocuments(trimmed, topK)
      setSearchResults(results)
      pushHistory(trimmed)
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }

  function handleSearch() {
    void runSearch(searchQuery, searchTopK)
  }

  function handleHistoryClick(query: string) {
    setSearchQuery(query)
    pendingRunRef.current = query
  }

  // Run search when a history item was clicked (after state flush)
  useEffect(() => {
    if (pendingRunRef.current !== null && pendingRunRef.current === searchQuery) {
      const q = pendingRunRef.current
      pendingRunRef.current = null
      void runSearch(q, searchTopK)
    }
  }, [searchQuery, searchTopK])

  function handleClearHistory() {
    setHistory([])
  }

  // Bespoke buildSearchCsv + manual blob/anchor wiring removed in favour of
  // the shared useTableExport hook. The hook handles BOM, RFC 4180 escaping,
  // dated filename, and the JSON sibling format.
  const { exportAs: exportSearchAs } = useTableExport<DocumentSearchResult>({
    filename: 'rag-search',
    rows: searchResults ?? [],
    columns: [
      { key: 'id', header: 'id', accessor: r => r.id },
      { key: 'score', header: 'score', accessor: r => r.score ?? null },
      { key: 'content', header: 'content', accessor: r => r.content },
    ],
  })

  function handleExportCsv() {
    if (!searchResults || searchResults.length === 0) return
    exportSearchAs('csv')
  }

  return (
    <section className="rag-quick-search" aria-labelledby="rag-quick-search-title">
      <header className="rag-quick-search__header">
        <div>
          <h2 id="rag-quick-search-title" className="section-title">{t('ragCachePage.quickSearch')}</h2>
          <p>{t('ragCachePage.quickSearchExt.description')}</p>
        </div>
      </header>

      <div className="rag-quick-search__form">
        <div className="form-group">
          <input
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder={t('ragCachePage.searchPlaceholder')}
            onKeyDown={e => {
              if (e.key === 'Enter') handleSearch()
            }}
            aria-label={t('ragCachePage.quickSearch')}
          />
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleSearch}
          disabled={searching}
        >
          {searching ? <LoadingSpinner size="sm" /> : t('ragCachePage.search')}
        </button>
      </div>

      <div className="rag-slider-group">
        <div className="rag-slider-group__header">
          <label htmlFor="rag-topk-slider" className="rag-slider-group__label">
            {t('ragCachePage.quickSearchExt.topK')}
          </label>
          <span className="rag-slider-group__value">{searchTopK}</span>
        </div>
        <div className="rag-slider-group__track">
          <span className="rag-slider-group__min">1</span>
          <input
            id="rag-topk-slider"
            type="range"
            className="rag-range-slider"
            min={1}
            max={20}
            value={searchTopK}
            onChange={e => setSearchTopK(Number(e.target.value))}
            aria-valuemin={1}
            aria-valuemax={20}
            aria-valuenow={searchTopK}
          />
          <span className="rag-slider-group__max">20</span>
        </div>
      </div>

      {history.length > 0 && (
        <section className="rag-quick-search__history" aria-labelledby="rag-search-history-title">
          <div className="rag-quick-search__history-header">
            <strong id="rag-search-history-title">
              {t('ragCachePage.quickSearchExt.history')}
            </strong>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleClearHistory}
            >
              {t('ragCachePage.quickSearchExt.clearHistory')}
            </button>
          </div>
          <div className="rag-quick-search__history-list">
            {history.map(q => (
              <button
                type="button"
                key={q}
                className="btn btn-secondary btn-sm"
                onClick={() => handleHistoryClick(q)}
              >
                {q}
              </button>
            ))}
          </div>
        </section>
      )}

      {searchResults !== null && (
        <section className="rag-quick-search__results" aria-live="polite">
          {searchResults.length === 0 ? (
            <EmptyState message={t('common.noData')} />
          ) : (
            <>
              <div className="rag-quick-search__results-header">
                <p>
                  {t('ragCachePage.resultsFound', { count: searchResults.length })}
                </p>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleExportCsv}
                >
                  {t('ragCachePage.quickSearchExt.exportCsv')}
                </button>
              </div>
              <div className="rag-quick-search__result-list">
                {searchResults.map((result) => {
                  const evidence = citationEvidence(result.metadata)
                  const missingCitationEvidence = missingCitationEvidenceLabels(evidence, t)
                  return (
                    <article
                      key={result.id}
                      className="rag-quick-search__result"
                    >
                      <div className="rag-quick-search__result-meta">
                        <span className={`rag-quick-search__evidence${missingCitationEvidence.length === 0 ? '' : ' rag-quick-search__evidence--warn'}`}>
                          <span aria-hidden="true" />
                          {missingCitationEvidence.length === 0
                            ? t('ragCachePage.quickSearchExt.citationReady')
                            : t('ragCachePage.quickSearchExt.citationNeedsReview')}
                        </span>
                        {result.score !== null && <ScoreBar score={result.score} />}
                      </div>
                      <p className="rag-quick-search__content">{result.content}</p>
                      <details className="rag-technical-details rag-quick-search__technical">
                        <summary>{t('ragCachePage.quickSearchExt.technicalDetails')}</summary>
                        <dl className="rag-candidate-evidence" aria-label={t('ragCachePage.quickSearchExt.citationEvidence')}>
                          <div>
                            <dt>{t('ragCachePage.quickSearchExt.resultId')}</dt>
                            <dd>{result.id}</dd>
                          </div>
                          {evidence.map((item) => (
                            <div key={item.id}>
                              <dt>{citationEvidenceLabel(item.id, t)}</dt>
                              <dd>{item.value}</dd>
                            </div>
                          ))}
                        </dl>
                        {missingCitationEvidence.length > 0 && (
                          <p>{t('ragCachePage.quickSearchExt.citationMissing', {
                            fields: missingCitationEvidence.join(', '),
                          })}</p>
                        )}
                      </details>
                    </article>
                  )
                })}
              </div>
            </>
          )}
        </section>
      )}
    </section>
  )
}

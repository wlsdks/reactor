import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  DataTable,
  EmptyState,
  HelpHint,
  LoadingSpinner,
  SideDrawer,
  Tooltip,
  type BulkAction,
  type Column,
} from '../../../shared/ui'
import { useToastStore } from '../../../shared/store/toast.store'
import * as documentsApi from '../api'
import type { SearchResultResponse } from '../types'

interface DocumentSearchTabProps {
  onSearch: (query: string, topK: number, threshold: number) => Promise<SearchResultResponse[]>
  onDeleteResult: (id: string) => Promise<void>
  onRegister: () => void
}

function hasMetadataValue(metadata: Record<string, unknown> | undefined, keys: string[]): boolean {
  if (!metadata) return false
  return keys.some((key) => {
    const value = metadata[key]
    if (Array.isArray(value)) return value.some((item) => String(item).trim().length > 0)
    return typeof value === 'string' && value.trim().length > 0
  })
}

function isCitationReadyResult(result: SearchResultResponse): boolean {
  const hasCitationId = hasMetadataValue(result.metadata, ['citation_ids', 'citationIds', 'citation_id', 'citationId'])
  const hasSource = hasMetadataValue(result.metadata, ['source_uri', 'sourceUri', 'source'])
  return hasCitationId && hasSource
}

function documentTitle(result: SearchResultResponse, fallback: string): string {
  const title = result.metadata?.title
  return typeof title === 'string' && title.trim() ? title.trim() : fallback
}

function documentSource(result: SearchResultResponse, fallback: string): string {
  const source = result.metadata?.source ?? result.metadata?.source_uri ?? result.metadata?.sourceUri
  return typeof source === 'string' && source.trim() ? source.trim() : fallback
}

function matchPercent(score: number | null): string {
  if (score == null) return '—'
  return `${Math.round(Math.max(0, Math.min(1, score)) * 100)}%`
}

export function DocumentSearchTab({ onSearch, onDeleteResult, onRegister }: DocumentSearchTabProps) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(5)
  const [threshold, setThreshold] = useState(0)
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState<SearchResultResponse[]>([])
  const [selectedResult, setSelectedResult] = useState<SearchResultResponse | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [initialLoading, setInitialLoading] = useState(true)
  const [hasSearched, setHasSearched] = useState(false)

  useEffect(() => {
    let cancelled = false
    void documentsApi.listDocuments(100).then((rows) => {
      if (cancelled) return
      setResults(rows.map((document) => ({
        id: document.id,
        content: document.content,
        metadata: document.metadata ?? {},
        score: null,
      })))
    }).catch(() => {
      // Older backends may not expose the list endpoint. Search remains available.
    }).finally(() => {
      if (!cancelled) setInitialLoading(false)
    })
    return () => { cancelled = true }
  }, [])

  async function handleSearch() {
    setSearching(true)
    setHasSearched(true)
    setSelectedResult(null)
    try {
      setResults(await onSearch(query, topK, threshold))
    } finally {
      setSearching(false)
    }
  }

  async function handleDeleteResult(id: string) {
    setDeletingId(id)
    try {
      await onDeleteResult(id)
      setResults((current) => current.filter((row) => row.id !== id))
      setSelectedResult(null)
    } finally {
      setDeletingId(null)
    }
  }

  async function handleBulkDelete(rows: SearchResultResponse[]) {
    const ids = rows.map((row) => row.id)
    try {
      await documentsApi.deleteDocuments(ids)
      setResults((current) => current.filter((row) => !ids.includes(row.id)))
      if (selectedResult && ids.includes(selectedResult.id)) setSelectedResult(null)
      useToastStore.getState().addToast({
        type: 'success',
        message: t('documentsPage.bulk.deleteResult', { count: ids.length }),
      })
    } catch (error) {
      useToastStore.getState().addToast({
        type: 'error',
        message: error instanceof Error ? error.message : String(error),
      })
    }
  }

  async function handleBulkReindex(rows: SearchResultResponse[]) {
    const documents = rows.map((row) => ({ content: row.content, metadata: row.metadata }))
    try {
      await documentsApi.deleteDocuments(rows.map((row) => row.id))
      await documentsApi.addDocumentsBatch({ documents })
      useToastStore.getState().addToast({
        type: 'success',
        message: t('documentsPage.bulk.reindexResult', { count: rows.length }),
      })
    } catch (error) {
      useToastStore.getState().addToast({
        type: 'error',
        message: error instanceof Error ? error.message : String(error),
      })
    }
  }

  const documentBulkActions: BulkAction<SearchResultResponse>[] = [
    {
      id: 'delete',
      label: t('documentsPage.bulk.delete'),
      variant: 'danger',
      confirmMessage: (rows) => t('documentsPage.bulk.deleteConfirm', { count: rows.length }),
      perform: handleBulkDelete,
    },
    {
      id: 'reindex',
      label: t('documentsPage.bulk.reindex'),
      variant: 'secondary',
      confirmMessage: (rows) => t('documentsPage.bulk.reindexConfirm', { count: rows.length }),
      perform: handleBulkReindex,
    },
  ]

  const resultColumns: Column<SearchResultResponse>[] = [
    {
      key: 'title',
      header: t('documentsPage.columnTitle'),
      width: '30%',
      responsivePriority: 1,
      render: (row) => (
        <div className="document-library-title">
          <Tooltip content={documentTitle(row, t('documentsPage.library.untitled'))}>
            <span>{documentTitle(row, t('documentsPage.library.untitled'))}</span>
          </Tooltip>
          <small>{documentSource(row, t('documentsPage.library.sourceUnknown'))}</small>
        </div>
      ),
    },
    {
      key: 'content',
      header: t('documentsPage.columnContent'),
      width: '52%',
      responsivePriority: 1,
      render: (row) => (
        <Tooltip content={row.content}>
          <span className="document-library-excerpt">{row.content}</span>
        </Tooltip>
      ),
    },
    {
      key: 'score',
      header: t('documentsPage.library.match'),
      width: '18%',
      responsivePriority: 2,
      render: (row) => matchPercent(row.score),
    },
  ]

  const citationReadyCount = results.filter(isCitationReadyResult).length
  const citationNeedsMetadataCount = Math.max(0, results.length - citationReadyCount)

  return (
    <div className="document-library-workspace">
      <header className="document-library-header">
        <div>
          <h2>{t('documentsPage.library.title')}</h2>
          <p>{t('documentsPage.library.description')}</p>
        </div>
      </header>

      <section className="document-library-search" aria-labelledby="document-library-search-title">
        <label id="document-library-search-title" htmlFor="doc-search-query">
          {t('documentsPage.library.searchLabel')}
        </label>
        <div className="document-library-search__command">
          <input
            id="doc-search-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('documentsPage.library.searchPlaceholder')}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !searching) void handleSearch()
            }}
          />
          <button type="button" className="btn btn-primary" onClick={() => void handleSearch()} disabled={searching}>
            {searching ? <LoadingSpinner size="sm" /> : t('documentsPage.search')}
          </button>
        </div>
        <details className="document-library-search__advanced">
          <summary>{t('documentsPage.library.advancedSearch')}</summary>
          <div>
            <label htmlFor="doc-search-topk">
              <span>{t('documentsPage.library.resultLimit')}</span>
              <HelpHint label={t('documentsPage.help.topK')} />
              <input
                id="doc-search-topk"
                type="number"
                min={1}
                max={50}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value) || 1)}
              />
            </label>
            <label htmlFor="doc-search-threshold">
              <span>{t('documentsPage.library.minimumMatch')}</span>
              <HelpHint label={t('documentsPage.help.similarityThreshold')} />
              <input
                id="doc-search-threshold"
                type="number"
                step="0.01"
                min={0}
                max={1}
                value={threshold}
                onChange={(event) => setThreshold(Number(event.target.value) || 0)}
              />
            </label>
          </div>
        </details>
      </section>

      <section className="document-library-collection" aria-labelledby="document-library-results-title">
        <div className="document-library-collection__heading">
          <div>
            <h3 id="document-library-results-title">{t('documentsPage.library.resultsTitle')}</h3>
            <p>{hasSearched ? t('documentsPage.library.searchResultsDescription') : t('documentsPage.library.savedDescription')}</p>
          </div>
          {!initialLoading && results.length > 0 && (
            <div className="document-library-summary" aria-label={t('documentsPage.library.summaryAria')}>
              <span><strong>{results.length}</strong>{t('documentsPage.library.total')}</span>
              <span><strong>{citationReadyCount}</strong>{t('documentsPage.library.sourceReady')}</span>
              <span><strong>{citationNeedsMetadataCount}</strong>{t('documentsPage.library.sourceNeeded')}</span>
            </div>
          )}
        </div>

        {initialLoading ? (
          <div className="document-library-loading"><LoadingSpinner size="sm" /></div>
        ) : results.length === 0 ? (
          <EmptyState
            message={hasSearched ? t('documentsPage.searchNoResults') : t('documentsPage.noDocsYet')}
            description={hasSearched ? t('documentsPage.library.noResultsDescription') : t('documentsPage.library.noDocumentsDescription')}
            actionLabel={hasSearched ? undefined : t('documentsPage.library.registerAction')}
            onAction={hasSearched ? undefined : onRegister}
          />
        ) : (
          <DataTable
            tableId="document-library-results"
            columns={resultColumns}
            data={results}
            keyFn={(row) => row.id}
            selectedKey={selectedResult?.id ?? null}
            onRowClick={setSelectedResult}
            selectable
            bulkActions={documentBulkActions}
          />
        )}
      </section>

      <SideDrawer
        open={Boolean(selectedResult)}
        title={selectedResult ? documentTitle(selectedResult, t('documentsPage.library.untitled')) : t('documentsPage.library.detailTitle')}
        onClose={() => setSelectedResult(null)}
        size="wide"
      >
        {selectedResult && (
          <div className="document-library-detail">
            <div className="document-library-detail__summary">
              <span>{documentSource(selectedResult, t('documentsPage.library.sourceUnknown'))}</span>
              <span>{t('documentsPage.library.matchValue', { value: matchPercent(selectedResult.score) })}</span>
            </div>
            <section>
              <span className="document-library-detail__label">{t('documentsPage.columnContent')}</span>
              <p>{selectedResult.content}</p>
            </section>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={deletingId === selectedResult.id}
              onClick={() => void handleDeleteResult(selectedResult.id)}
            >
              {deletingId === selectedResult.id ? <LoadingSpinner size="sm" /> : t('documentsPage.library.deleteAction')}
            </button>
            <details className="document-library-detail__technical">
              <summary>{t('common.technicalDetails')}</summary>
              <dl>
                <div><dt>{t('documentsPage.columnId')}</dt><dd>{selectedResult.id}</dd></div>
              </dl>
              {Object.keys(selectedResult.metadata ?? {}).length > 0 && (
                <pre>{JSON.stringify(selectedResult.metadata, null, 2)}</pre>
              )}
            </details>
          </div>
        )}
      </SideDrawer>
    </div>
  )
}

import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { SavedViewsControl } from '../../../shared/ui'
import { applyScopedParams, extractScopedParams } from '../../../shared/lib/useUrlState'
import { localizeReviewStatus, STATUS_OPTIONS, type StatusFilter } from './ragCandidatesUtils'

interface RagCandidatesToolbarProps {
  statusFilter: StatusFilter
  onStatusFilterChange: (next: StatusFilter) => void
  onExport: (format: 'csv' | 'json') => void
  canExport: boolean
}

export function RagCandidatesToolbar({
  statusFilter,
  onStatusFilterChange,
  onExport,
  canExport,
}: RagCandidatesToolbarProps) {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const [exportMenuOpen, setExportMenuOpen] = useState(false)

  return (
    <div className="rag-candidates-toolbar">
      <div className="rag-candidates-toolbar__intro">
        <h2 className="section-title">{t('ragCachePage.candidates.queue')}</h2>
        <p>{t('ragCachePage.candidates.queueDesc')}</p>
      </div>
      <div className="rag-candidates-toolbar__controls">
        <div className="form-group rag-candidates-toolbar__filter">
          <label htmlFor="rag-candidates-status-filter">
            {t('ragCachePage.candidates.filterStatus')}
          </label>
          <select
            id="rag-candidates-status-filter"
            value={statusFilter}
            onChange={(e) => onStatusFilterChange(e.target.value as StatusFilter)}
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>
                {opt === 'ALL'
                  ? t('ragCachePage.candidates.statusAll')
                  : localizeReviewStatus(opt, t)}
              </option>
            ))}
          </select>
        </div>
        <SavedViewsControl
          scope="rag-candidates"
          currentParams={extractScopedParams(searchParams, 'rag-candidates')}
          onApply={(params) => setSearchParams(applyScopedParams(searchParams, 'rag-candidates', params), { replace: true })}
        />
        <div className="data-table-export-menu">
          <button
            type="button"
            className="btn btn-secondary btn-sm data-table-export-menu__trigger"
            onClick={() => setExportMenuOpen(prev => !prev)}
            disabled={!canExport}
            aria-haspopup="menu"
            aria-expanded={exportMenuOpen}
            title={!canExport ? t('common.tableExport.emptyDisabled') : undefined}
          >
            <span>{t('common.tableExport.menuLabel')}</span>
            <span aria-hidden="true" className="data-table-export-menu__chevron">
              {exportMenuOpen ? '접기' : '열기'}
            </span>
          </button>
          {exportMenuOpen && (
            <div className="data-table-export-menu__panel" role="menu">
              <button
                type="button"
                role="menuitem"
                className="data-table-export-menu__item"
                onClick={() => { setExportMenuOpen(false); onExport('csv') }}
              >
                {t('common.tableExport.csvOption')}
              </button>
              <button
                type="button"
                role="menuitem"
                className="data-table-export-menu__item"
                onClick={() => { setExportMenuOpen(false); onExport('json') }}
              >
                {t('common.tableExport.jsonOption')}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

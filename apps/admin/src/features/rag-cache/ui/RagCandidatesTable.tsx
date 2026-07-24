import type { ChangeEvent, KeyboardEvent, MouseEvent as ReactMouseEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDate, localizeReviewStatus, truncate } from './ragCandidatesUtils'
import type { RagCandidate } from '../types'
import type { RagCandidatesSelection } from './useRagCandidatesSelection'

interface RagCandidatesTableProps {
  data: RagCandidate[]
  selection: RagCandidatesSelection
  bulkBusy: boolean
  selectedRow: RagCandidate | null
  onSelectRow: (row: RagCandidate) => void
}

export function RagCandidatesTable({
  data,
  selection,
  bulkBusy,
  selectedRow,
  onSelectRow,
}: RagCandidatesTableProps) {
  const { t } = useTranslation()
  const {
    selectedIds,
    pendingIds,
    allPendingSelected,
    somePendingSelected,
    handleRowCheckboxChange,
    handleSelectAll,
  } = selection

  function handleCheckboxKeyDown(
    event: KeyboardEvent<HTMLInputElement>,
    row: RagCandidate,
    index: number,
  ) {
    if (event.key === ' ') {
      event.preventDefault()
      handleRowCheckboxChange(row, index, event.shiftKey)
    }
  }

  return (
    <div className="table-wrapper">
      <table className="data-table rag-candidates-table">
        <thead>
          <tr>
            <th scope="col" className="rag-candidates-table__checkbox-cell">
              <input
                type="checkbox"
                aria-label={t('ragCachePage.candidates.selectAll')}
                checked={allPendingSelected}
                ref={(el) => {
                  if (el) el.indeterminate = !allPendingSelected && somePendingSelected
                }}
                disabled={pendingIds.length === 0 || bulkBusy}
                onChange={(e: ChangeEvent<HTMLInputElement>) =>
                  handleSelectAll(e.target.checked)
                }
              />
            </th>
            <th scope="col" style={{ width: '15%' }}>
              {t('ragCachePage.candidates.channel')}
            </th>
            <th scope="col">{t('ragCachePage.candidates.query')}</th>
            <th scope="col" style={{ width: '12%' }}>
              {t('ragCachePage.candidates.status')}
            </th>
            <th scope="col" style={{ width: '18%' }}>
              {t('ragCachePage.candidates.capturedAt')}
            </th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => {
            const isPending = row.status === 'PENDING'
            // Find index inside the PENDING-only list for range selection.
            const pendingIndex = isPending
              ? pendingIds.indexOf(row.id)
              : -1
            const checked = selectedIds.has(row.id)
            const isRowSelected = selectedRow?.id === row.id
            return (
              <tr
                key={row.id}
                className={[
                  'clickable',
                  isRowSelected ? 'is-selected' : '',
                  checked ? 'is-bulk-selected' : '',
                ]
                  .filter(Boolean)
                  .join(' ') || undefined}
                onClick={(e: ReactMouseEvent<HTMLTableRowElement>) => {
                  // Clicks inside the checkbox cell should not open the drawer.
                  const target = e.target as HTMLElement
                  if (target.closest('.rag-candidates-table__checkbox-cell')) {
                    return
                  }
                  onSelectRow(row)
                }}
                onKeyDown={(e: KeyboardEvent<HTMLTableRowElement>) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    onSelectRow(row)
                  }
                }}
                tabIndex={0}
                role="button"
              >
                <td
                  className="rag-candidates-table__checkbox-cell"
                  onClick={(e) => e.stopPropagation()}
                >
                  <input
                    type="checkbox"
                    aria-label={t('ragCachePage.candidates.selectRow', {
                      query: truncate(row.query, 40),
                    })}
                    checked={checked}
                    disabled={!isPending || bulkBusy}
                    onClick={(e) => {
                      // ChangeEvent does not expose shiftKey — snapshot
                      // it here and delegate to the shared handler which
                      // onChange will re-enter (we prevent double-toggle
                      // by handling from onClick only).
                      if (!isPending) return
                      e.stopPropagation()
                      e.preventDefault()
                      handleRowCheckboxChange(row, pendingIndex, e.shiftKey)
                    }}
                    onChange={() => {
                      // No-op: handled in onClick to capture shiftKey.
                    }}
                    onKeyDown={(e) => handleCheckboxKeyDown(e, row, pendingIndex)}
                  />
                </td>
                <td>{row.channel || '-'}</td>
                <td>
                  <span>{truncate(row.query, 80)}</span>
                </td>
                <td>
                  <span className={`rag-candidate-status rag-candidate-status--${row.status.toLowerCase()}`}>
                    <span aria-hidden="true" />
                    {localizeReviewStatus(row.status, t)}
                  </span>
                </td>
                <td>
                  <span className="data-mono" style={{ fontSize: '0.85em' }}>
                    {formatDate(row.capturedAt)}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

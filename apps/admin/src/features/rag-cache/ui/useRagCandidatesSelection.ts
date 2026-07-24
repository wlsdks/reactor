import { useRef, useState } from 'react'
import type { RagCandidate } from '../types'

/**
 * Selection state for the RAG candidates table.
 *
 * Only PENDING candidates are bulk-actionable — non-PENDING rows render
 * disabled checkboxes and are excluded from select-all / range selection. The
 * hook tracks the last toggled index so Shift+Click can extend the previous
 * anchor across the PENDING-only ordering.
 */
export interface RagCandidatesSelection {
  /** Currently checked candidate ids (PENDING only). */
  selectedIds: Set<string>
  /** PENDING candidate ids in their stable display order. */
  pendingIds: string[]
  /** True when every PENDING candidate is currently selected. */
  allPendingSelected: boolean
  /** True when at least one (but not all) PENDING candidates are selected. */
  somePendingSelected: boolean
  /** Drop every selection and reset the Shift+Click anchor. */
  clearSelection: () => void
  /**
   * Toggle a single row, or extend a range from the previous anchor when
   * `shiftKey` is true and a prior anchor exists. No-ops for non-PENDING rows.
   */
  handleRowCheckboxChange: (row: RagCandidate, index: number, shiftKey: boolean) => void
  /** Select-all / clear-all entry point used by the header checkbox. */
  handleSelectAll: (checked: boolean) => void
}

export function useRagCandidatesSelection(data: RagCandidate[]): RagCandidatesSelection {
  // Bulk selection state — ids of PENDING candidates only.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  // Anchor index for Shift+Click range selection.
  const lastToggledIndexRef = useRef<number | null>(null)

  // Only PENDING rows are bulk-actionable. Derived list is the stable order
  // used for range selection (Shift+Click) and select-all.
  const pendingRows: RagCandidate[] = data.filter((row) => row.status === 'PENDING')
  const pendingIds: string[] = pendingRows.map((row) => row.id)
  const allPendingSelected =
    pendingIds.length > 0 && pendingIds.every((id) => selectedIds.has(id))
  const somePendingSelected = pendingIds.some((id) => selectedIds.has(id))

  function clearSelection() {
    setSelectedIds(new Set())
    lastToggledIndexRef.current = null
  }

  function toggleOne(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function selectRange(fromIndex: number, toIndex: number) {
    const start = Math.min(fromIndex, toIndex)
    const end = Math.max(fromIndex, toIndex)
    setSelectedIds((prev) => {
      const next = new Set(prev)
      for (let i = start; i <= end; i++) {
        const id = pendingIds[i]
        if (id != null) next.add(id)
      }
      return next
    })
  }

  function handleRowCheckboxChange(row: RagCandidate, index: number, shiftKey: boolean) {
    if (row.status !== 'PENDING') return
    const anchor = lastToggledIndexRef.current
    if (shiftKey && anchor != null && anchor !== index) {
      selectRange(anchor, index)
    } else {
      toggleOne(row.id)
    }
    lastToggledIndexRef.current = index
  }

  function handleSelectAll(checked: boolean) {
    if (!checked) {
      clearSelection()
      return
    }
    setSelectedIds(new Set(pendingIds))
  }

  return {
    selectedIds,
    pendingIds,
    allPendingSelected,
    somePendingSelected,
    clearSelection,
    handleRowCheckboxChange,
    handleSelectAll,
  }
}

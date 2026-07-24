import { Fragment, useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type React from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronLeft, ChevronRight, MoreVertical } from 'lucide-react'
import { useAnnouncer } from './LiveAnnouncer'
import { RowContextMenu } from './RowContextMenu'
import type { RowAction } from './RowContextMenu'
import { ConfirmDialog } from './ConfirmDialog'
import { OperationButton } from './OperationButton'
import type { OperationButtonVariant } from './OperationButton'
import { Tooltip } from './Tooltip'
import { useUrlState } from '../lib/useUrlState'
import { useTableExport, type ExportColumn } from '../lib/useTableExport'
import { pageRange } from './pageRange'
import { InlineCellEdit } from './InlineCellEdit'
import type { InlineCellEditType, InlineCellEditOption } from './InlineCellEdit'
import './DataTable.css'

/**
 * Declarative bulk action surfaced in the sticky bulk-action bar that the
 * DataTable renders when `selectable` is enabled and ≥1 row is selected.
 *
 * `perform` receives the array of currently selected rows (in the original
 * `data` order). When `confirmMessage` returns a non-empty string the table
 * shows a `ConfirmDialog` first; the action only fires after the operator
 * confirms. While `perform` is in flight the bar shows a busy state and
 * dispatches a polite `LiveAnnouncer` message on completion. Selection is
 * cleared after a successful `perform()` so the operator is not left holding
 * stale ids that may have been deleted server-side.
 */
export interface BulkAction<T> {
  /** Stable id used as the React key and as the key passed to LiveAnnouncer. */
  id: string
  /** Human label rendered on the action button. */
  label: string
  /** Optional inline icon rendered before the label. */
  icon?: ReactNode
  /** Visual variant — maps onto OperationButton's `primary | secondary | danger`. */
  variant?: 'primary' | 'danger' | 'secondary'
  /** Persist handler. May be async; the bar shows a spinner until it resolves. */
  perform: (rows: T[]) => Promise<void> | void
  /** When true, the action button is hidden for the current selection. */
  hidden?: (rows: T[]) => boolean
  /** When true, the action button is rendered disabled (still visible). */
  disabled?: (rows: T[]) => boolean
  /** When provided and returns a non-empty string, a ConfirmDialog is shown
   *  before `perform` fires. The string is used as the dialog message. */
  confirmMessage?: (rows: T[]) => string
}

export interface Column<T> {
  key: string
  /**
   * Column header. Plain strings are the common case (used as-is for the
   * exported file header and screen-reader announcements). A `ReactNode` is
   * also accepted so callers can attach inline help glyphs (e.g. `HelpHint`)
   * or icons next to the label — when non-string, `key` is used as the
   * fallback for the export header and any aria-only consumer.
   */
  header: ReactNode
  render: (row: T) => ReactNode
  width?: string
  sortable?: boolean
  /**
   * When true (the default for string cell values), the cell will be rendered
   * with single-line truncation CSS plus a `title` attribute containing the
   * full text. When false, no truncation CSS or title is applied.
   *
   * Non-string render output (ReactNode) is always rendered as-is; this flag
   * only affects plain string values.
   */
  truncate?: boolean
  /**
   * When true, a resize handle is rendered at the right edge of the column
   * header. Users can drag (or use ArrowLeft/ArrowRight while focused) to
   * change the column width.
   */
  resizable?: boolean
  /**
   * Responsive drop priority for narrow viewports (≤900px).
   *
   * Lower numbers are kept; columns with priority ≥3 are hidden in the main
   * table and instead revealed inline via a per-row details expander.
   * Columns without this prop are always visible (equivalent to priority 1).
   *
   * Opt-in: omitting the prop preserves the existing (non-responsive)
   * behaviour, so no caller needs to migrate.
   */
  responsivePriority?: number
  /**
   * Optional export accessor — used by `exportable` to derive a primitive
   * value when the column's `render` returns a ReactNode. When omitted, the
   * derived export reads `row[key]` if it is a primitive, otherwise the
   * column is skipped from the export with a dev-mode warning.
   */
  exportAccessor?: (row: T) => string | number | boolean | null | undefined
  /**
   * When true, this column is excluded from auto-derived exports even if
   * `exportable` is enabled. Useful for selection checkboxes or action
   * columns that have no meaningful exportable value.
   */
  excludeFromExport?: boolean
  /**
   * Opt-in inline-cell-edit. When provided, the cell renders an
   * `<InlineCellEdit />` driven by the column's render output: in idle mode
   * the cell looks identical to the existing render path, but a click /
   * Enter / Space activates an inline editor. The committed value is passed
   * back via `onCommit` so the caller can fire its own mutation.
   *
   * The default `InlineCellEdit` reads its idle-mode display string from the
   * extracted `value`. Pass `format` to render something more compact (e.g.
   * a status pill) — the row's `render` callback is still used for cells
   * without `inlineEdit` and for ReactNode-only columns.
   *
   * Backward compat: omitting this prop preserves the existing render path,
   * so no caller needs to migrate.
   */
  inlineEdit?: {
    /** Editor flavour. */
    type: InlineCellEditType
    /** Required when `type === 'select'`. */
    options?: InlineCellEditOption<unknown>[]
    /** Extract the editable value from the row. */
    getValue: (row: T) => unknown
    /** Optional formatter for the idle / read-only display. */
    format?: (value: unknown) => string
    /** Optional sync validator. */
    validate?: (value: unknown) => string | null
    /** Persist handler — may be async. */
    onCommit: (row: T, value: unknown) => Promise<void> | void
    /** When false, outside-clicks cancel the edit instead of committing. */
    commitOnBlur?: boolean
    /** Accessible edit action label derived from the current row. */
    ariaLabel?: (row: T) => string
    /** When true, the cell renders read-only (idle text only). */
    disabled?: (row: T) => boolean
  }
}

interface DataTableProps<T> {
  columns: Column<T>[]
  data: T[]
  keyFn: (row: T) => string
  onRowClick?: (row: T) => void
  selectedKey?: string | null
  rowClassName?: (row: T) => string | undefined
  page?: number
  pageSize?: number
  totalCount?: number
  onPageChange?: (page: number) => void
  sortKey?: string | null
  sortDirection?: 'asc' | 'desc' | null
  onSort?: (key: string, direction: 'asc' | 'desc' | null) => void
  /**
   * Stable identifier for persisting per-column widths to localStorage.
   * When provided, resized widths are saved under
   * `reactor-admin-datatable-{tableId}-widths`. When omitted, widths are kept
   * in component state only and reset on remount.
   */
  tableId?: string
  /**
   * When set, the table mirrors its `page`, `sortKey`, and `sortDirection`
   * state to URL search params and restores them on mount. The key is used
   * as a prefix so multiple tables on the same route do not collide:
   *
   *   `${urlStateKey}_p` → 1-based page number
   *   `${urlStateKey}_s` → active sort column key
   *   `${urlStateKey}_d` → 'asc' or 'desc'
   *
   * URL writes happen via `useSearchParams`'s `replace: true` mode so they
   * never inflate the browser history. Default values (page === 1, no sort)
   * are removed from the URL to keep shareable links tidy.
   *
   * Opt-in: omitting this prop preserves the existing local-state behaviour,
   * so callers that have not migrated keep working unchanged.
   */
  urlStateKey?: string
  /**
  /**
   * When provided, renders an export menu in the table toolbar (top-right
   * of the table) with CSV / JSON download options. The hook downloads the
   * currently rendered `data` rows — pass the post-filter, post-page slice
   * to align the export with what the user sees, or pass the full filtered
   * set when "export all visible" semantics are required.
   *
   * `columns` defaults to the visible DataTable columns minus any flagged
   * with `excludeFromExport`. Each column's `exportAccessor` is used when
   * present; otherwise primitive `row[key]` values are read directly.
   * Columns without an accessor and a non-primitive `row[key]` are skipped
   * (with a `console.warn` in dev mode) to avoid exporting `[object Object]`.
   */
  exportable?: {
    /** Filename base — the hook appends `-YYYY-MM-DD.<ext>`. */
    filename: string
    /** Optional explicit column list. When omitted, derived from `columns`. */
    columns?: ExportColumn<T>[]
    /** Token written for null/undefined cells in CSV. Default: `'-'`. */
    fallbackEmpty?: string
  }
  /**
   * Optional row-level actions surfaced via the right-click context menu, the
   * row-actions hover trigger, and `Shift+Enter` on a focused row. When omitted
   * none of those affordances render and the table behaves exactly as before.
   */
  rowActions?: RowAction<T>[]
  /**
   * When provided, renders a `<select>` next to the pagination controls so
   * the operator can switch the table's page size without leaving the screen.
   *
   * Resolution order (first defined value wins):
   *   1. URL param `${urlStateKey}_ps` — when `urlStateKey` is set, the
   *      selected size round-trips through the URL so links / back-navigation
   *      are shareable.
   *   2. localStorage `reactor-admin-datatable-{tableId}-pageSize` — when
   *      `tableId` is set, the selection sticks across reloads (mirroring the
   *      `resizable` width-persistence pattern).
   *   3. `defaultPageSize` prop, or `25` when the prop is omitted.
   *
   * On change the new value is persisted to URL + localStorage (when their
   * keys are configured) and propagated up through `onPageSizeChange` plus a
   * `onPageChange(1)` reset so the parent's slicing math stays in sync.
   *
   * Opt-in: omitting this prop preserves the existing render path so callers
   * that have not migrated keep their hand-rolled `pageSize` plumbing.
   */
  pageSizeOptions?: number[]
  /**
   * Default page size used when neither URL nor localStorage carries a
   * persisted value. Defaults to `25` when omitted. Ignored unless
   * `pageSizeOptions` is also provided.
   */
  defaultPageSize?: number
  /**
   * Emitted when the user picks a new page size from the selector. Required
   * for the parent to keep its slicing math in sync — DataTable calls this
   * before reseting the page to 1 via `onPageChange`.
   */
  onPageSizeChange?: (pageSize: number) => void
  /**
   * When true, renders a leading checkbox column plus a sticky bulk-action
   * bar (when ≥1 row is selected). Backward-compatible — omitting the prop
   * keeps the existing render path so non-migrated callers stay unchanged.
   */
  selectable?: boolean
  /**
   * Action descriptors rendered in the bulk bar. Ignored unless `selectable`
   * is also set. See `BulkAction<T>` for confirm / hidden / disabled hooks.
   */
  bulkActions?: BulkAction<T>[]
  /**
   * Optional per-row gate. When it returns false, the row's checkbox renders
   * disabled (with a `title` hint) and the row is excluded from `selectAll`
   * + Shift+Click range selection. Useful for protected rows like the
   * default persona that should never be bulk-acted upon.
   */
  rowSelectable?: (row: T) => boolean
  /**
   * By default, the selected-id set is cleared whenever `data` changes
   * identity (typically after a query refresh). Set to true to preserve
   * the selection across data refreshes — caller is responsible for
   * ensuring the ids remain valid (e.g. paginated server-side data).
   * @default false
   */
  keepSelectionAcrossDataChange?: boolean
}

const MIN_COLUMN_WIDTH_PX = 40
const KEYBOARD_RESIZE_STEP_PX = 10
/** Width (px) at or below which low-priority columns are hidden in favour of
 *  a per-row expander. Matches the tablet-tier breakpoint documented in
 *  `src/index.css`. */
const RESPONSIVE_HIDE_MAX_WIDTH_PX = 900
const RESPONSIVE_PRIORITY_HIDE_THRESHOLD = 3

function storageKey(tableId: string): string {
  return `reactor-admin-datatable-${tableId}-widths`
}

/** Storage key for the per-table page-size preference. Mirrors the resizable
 *  widths pattern (PR #281) so the same `tableId` namespace owns both. */
function pageSizeStorageKey(tableId: string): string {
  return `reactor-admin-datatable-${tableId}-pageSize`
}

function readStoredPageSize(tableId: string | undefined): number | null {
  if (!tableId || typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(pageSizeStorageKey(tableId))
    if (!raw) return null
    const parsed = Number.parseInt(raw, 10)
    if (Number.isFinite(parsed) && parsed > 0) return parsed
  } catch {
    // Ignore storage access errors.
  }
  return null
}

function writeStoredPageSize(tableId: string, pageSize: number): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(pageSizeStorageKey(tableId), String(pageSize))
  } catch {
    // Ignore quota / access errors.
  }
}

function readStoredWidths(tableId: string | undefined): Record<string, number> {
  if (!tableId || typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(storageKey(tableId))
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const result: Record<string, number> = {}
      for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
        if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
          result[key] = value
        }
      }
      return result
    }
  } catch {
    // Ignore malformed JSON; treat as no stored widths.
  }
  return {}
}

function writeStoredWidths(tableId: string, widths: Record<string, number>): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(storageKey(tableId), JSON.stringify(widths))
  } catch {
    // Ignore storage quota / access errors.
  }
}

function getNextSortDirection(current: 'asc' | 'desc' | null): 'asc' | 'desc' | null {
  if (current === 'asc') return 'desc'
  if (current === 'desc') return null
  return 'asc'
}

/**
 * Resolves the active sort state for a given column key.
 * Returns 'asc' / 'desc' when this column is actively sorted, otherwise null.
 */
function getActiveSortDirection(
  key: string,
  sortKey: string | null | undefined,
  sortDirection: 'asc' | 'desc' | null | undefined,
): 'asc' | 'desc' | null {
  if (sortKey !== key || !sortDirection) return null
  return sortDirection
}

/**
 * Renders the sort indicator. When the column is the active sort, shows a
 * product-accent triangle pointing in the sort direction. When the column is
 * sortable but inactive, shows a faint up/down chevron pair (opacity 0.3,
 * promoted to 0.7 on hover via CSS) to advertise sortability.
 */
function SortIcon({ direction }: { direction: 'asc' | 'desc' | null }) {
  if (direction === 'asc') {
    return (
      <svg
        className="data-table-sort-icon data-table-sort-icon--active"
        width="8"
        height="8"
        viewBox="0 0 8 8"
        aria-hidden="true"
        focusable="false"
      >
        <path d="M4 1L7 6H1L4 1Z" fill="currentColor" />
      </svg>
    )
  }
  if (direction === 'desc') {
    return (
      <svg
        className="data-table-sort-icon data-table-sort-icon--active"
        width="8"
        height="8"
        viewBox="0 0 8 8"
        aria-hidden="true"
        focusable="false"
      >
        <path d="M4 7L1 2H7L4 7Z" fill="currentColor" />
      </svg>
    )
  }
  // Inactive sortable column: faint dual chevrons hint at sortability.
  return (
    <svg
      className="data-table-sort-icon data-table-sort-icon--inactive"
      width="8"
      height="10"
      viewBox="0 0 8 10"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M4 0L7 4H1L4 0Z" fill="currentColor" />
      <path d="M4 10L1 6H7L4 10Z" fill="currentColor" />
    </svg>
  )
}

function getAriaSortValue(
  key: string,
  sortKey: string | null | undefined,
  sortDirection: 'asc' | 'desc' | null | undefined,
): 'ascending' | 'descending' | 'none' {
  if (sortKey === key && sortDirection === 'asc') return 'ascending'
  if (sortKey === key && sortDirection === 'desc') return 'descending'
  return 'none'
}

/** Mobile breakpoint (px) at or below which numbered page buttons collapse
 *  to a compact previous/next control + jump-input layout. Matches the product mobile
 *  cutoff used elsewhere in shared-components.css. */
const PAGINATION_MOBILE_MAX_WIDTH_PX = 640

/**
 * Tracks the viewport against the pagination mobile breakpoint. Returns true
 * when the numbered page buttons should be hidden in favour of the compact
 * input-only layout. SSR-safe (returns false before browser attaches).
 */
function useIsPaginationMobile(): boolean {
  const [isMobile, setIsMobile] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return window.innerWidth <= PAGINATION_MOBILE_MAX_WIDTH_PX
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    const query = window.matchMedia(`(max-width: ${PAGINATION_MOBILE_MAX_WIDTH_PX}px)`)
    const update = () => setIsMobile(query.matches)
    update()
    if (typeof query.addEventListener === 'function') {
      query.addEventListener('change', update)
      return () => query.removeEventListener('change', update)
    }
    query.addListener(update)
    return () => query.removeListener(update)
  }, [])

  return isMobile
}


/** True when the column should be hidden in the main table on narrow
 *  viewports (and instead surfaced via the row expander). */
function isLowPriorityColumn<T>(col: Column<T>): boolean {
  return (
    typeof col.responsivePriority === 'number' &&
    col.responsivePriority >= RESPONSIVE_PRIORITY_HIDE_THRESHOLD
  )
}

/**
 * Tracks the current viewport width against the responsive hide threshold.
 * Returns true when the viewport is narrow enough that low-priority columns
 * should collapse. SSR-safe (returns false before the browser attaches).
 */
function useIsNarrowViewport(enabled: boolean): boolean {
  const [isNarrow, setIsNarrow] = useState<boolean>(() => {
    if (!enabled || typeof window === 'undefined') return false
    return window.innerWidth <= RESPONSIVE_HIDE_MAX_WIDTH_PX
  })

  useEffect(() => {
    if (!enabled || typeof window === 'undefined') return
    const query = window.matchMedia(`(max-width: ${RESPONSIVE_HIDE_MAX_WIDTH_PX}px)`)
    const update = () => setIsNarrow(query.matches)
    update()
    // Safari <14 exposes addListener/removeListener only; modern browsers
    // expose addEventListener. Use addEventListener when available.
    if (typeof query.addEventListener === 'function') {
      query.addEventListener('change', update)
      return () => query.removeEventListener('change', update)
    }
    // Fallback for very old browsers.
    query.addListener(update)
    return () => query.removeListener(update)
  }, [enabled])

  return isNarrow
}

/**
 * Internal bridge that mirrors page / sort props to the URL via
 * `useUrlState`. Mounted only when DataTable receives a `urlStateKey`, so the
 * default render path keeps working without a router context.
 */
interface UrlStateBridgeProps {
  urlStateKey: string
  page: number | undefined
  sortKey: string | null | undefined
  sortDirection: 'asc' | 'desc' | null | undefined
  onPageChange: ((page: number) => void) | undefined
  onSort: ((key: string, direction: 'asc' | 'desc' | null) => void) | undefined
  /** Optional page-size sync. When the parent has opted in to the
   *  page-size selector, the bridge mirrors `pageSize` to `${prefix}_ps` and
   *  surfaces back-navigation changes through `onPageSizeChange`. */
  pageSize: number | undefined
  onPageSizeChange: ((pageSize: number) => void) | undefined
  defaultPageSize: number | undefined
}

function UrlStateBridge({
  urlStateKey,
  page,
  sortKey,
  sortDirection,
  onPageChange,
  onSort,
  pageSize,
  onPageSizeChange,
  defaultPageSize,
}: UrlStateBridgeProps) {
  // The default for `ps` mirrors the resolved default page size so that a
  // value equal to the default clears the URL (matching `useUrlState` semantics
  // for page === 1 / no sort).
  const psDefault = defaultPageSize ?? 0
  const [urlState, setUrlState] = useUrlState(
    { p: 1, s: '' as string, d: '' as string, ps: psDefault },
    { prefix: urlStateKey },
  )
  // Track whether we have already applied the initial URL → parent sync.
  const initializedRef = useRef(false)
  // Track the last URL values we wrote, to avoid re-applying our own writes.
  const lastWrittenRef = useRef<{ p: number; s: string; d: string; ps: number } | null>(null)

  // Initial mount: apply URL → parent props if URL carries non-default state
  // that differs from current props. Subsequent URL changes (e.g. browser
  // back/forward) also flow back into parent state.
  useEffect(() => {
    const urlPage = urlState.p
    const urlSortKey = urlState.s
    const urlSortDir = urlState.d
    const urlPageSize = urlState.ps
    const lastWritten = lastWrittenRef.current
    // Skip echoes of our own writes — those would cause an infinite ping-pong.
    if (
      lastWritten &&
      lastWritten.p === urlPage &&
      lastWritten.s === urlSortKey &&
      lastWritten.d === urlSortDir &&
      lastWritten.ps === urlPageSize
    ) {
      initializedRef.current = true
      return
    }
    if (onPageChange && urlPage !== (page ?? 1)) {
      onPageChange(urlPage)
    }
    if (onSort) {
      const dir =
        urlSortDir === 'asc' || urlSortDir === 'desc' ? urlSortDir : null
      const key = urlSortKey || ''
      const currentKey = sortKey ?? ''
      const currentDir = sortDirection ?? null
      if (key !== currentKey || dir !== currentDir) {
        if (key) {
          onSort(key, dir)
        } else if (currentKey) {
          // URL cleared the sort entirely.
          onSort(currentKey, null)
        }
      }
    }
    if (
      onPageSizeChange &&
      urlPageSize > 0 &&
      urlPageSize !== (pageSize ?? psDefault)
    ) {
      onPageSizeChange(urlPageSize)
    }
    initializedRef.current = true
  // We intentionally watch only URL state; reacting to parent changes here
  // would echo back the writes we are about to make below.
  }, [urlState.p, urlState.s, urlState.d, urlState.ps])

  // Parent → URL: whenever the parent's authoritative props change, mirror
  // them out to the URL. Default values (page 1 / no sort) clear the param.
  useEffect(() => {
    if (!initializedRef.current) return
    const next = {
      p: page ?? 1,
      s: sortKey ?? '',
      d: sortDirection ?? '',
      ps: pageSize ?? psDefault,
    }
    lastWrittenRef.current = next
    setUrlState(next)
  // setUrlState identity changes per render via React Router; intentionally
  // omit it to avoid an extra write loop — the writer reads current URL on
  // every call, so a stale closure is safe.
  }, [page, sortKey, sortDirection, pageSize])

  return null
}

/**
 * Derives an `ExportColumn[]` list from DataTable `Column[]` when the caller
 * does not supply an explicit list. Selection / action columns are filtered
 * via `excludeFromExport`. Columns without an `exportAccessor` are kept only
 * when `row[key]` will plausibly produce a primitive — runtime sniffing
 * happens lazily inside the accessor itself, so we cannot pre-filter ReactNode
 * columns at this layer. Dev-mode warnings happen at first render in
 * `warnNonPrimitiveExports` below.
 */
function deriveExportColumns<T>(columns: Column<T>[]): ExportColumn<T>[] {
  return columns
    .filter(col => !col.excludeFromExport)
    .map<ExportColumn<T>>(col => ({
      key: col.key,
      header: typeof col.header === 'string' ? col.header : col.key,
      accessor: col.exportAccessor
        ? col.exportAccessor
        : (row: T) => {
            const value = (row as Record<string, unknown>)[col.key]
            if (
              value === null ||
              value === undefined ||
              typeof value === 'string' ||
              typeof value === 'number' ||
              typeof value === 'boolean'
            ) {
              return value
            }
            // Non-primitive: warn once in dev so the caller adds an
            // explicit `exportAccessor`. Production stays silent.
            if (import.meta.env.DEV) {
              warnNonPrimitiveExport(col.key)
            }
            return undefined
          },
    }))
}

const warnedExportKeys = new Set<string>()
function warnNonPrimitiveExport(key: string): void {
  if (warnedExportKeys.has(key)) return
  warnedExportKeys.add(key)
  console.warn(
    `[DataTable] column "${key}" has no \`exportAccessor\` and \`row[${key}]\` is not a primitive — value omitted from export.`,
  )
}

interface ExportMenuProps {
  filename: string
  exportColumns: ExportColumn<unknown>[]
  rows: unknown[]
  fallbackEmpty: string | undefined
}

/**
 * Lightweight chevron-button + popover menu. Uses pure-CSS positioning
 * (absolute on a relatively-positioned wrapper) so we avoid Floating UI for
 * a 2-item list. Click-outside / Escape close are handled here.
 */
function ExportMenu({ filename, exportColumns, rows, fallbackEmpty }: ExportMenuProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const wrapperRef = useRef<HTMLDivElement | null>(null)
  const { exportAs, isReady } = useTableExport({
    filename,
    rows,
    columns: exportColumns,
    fallbackEmpty,
  })

  useEffect(() => {
    if (!open) return
    const onDocClick = (event: MouseEvent) => {
      const target = event.target as Node | null
      if (target && wrapperRef.current && !wrapperRef.current.contains(target)) {
        setOpen(false)
      }
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const handlePick = (format: 'csv' | 'json') => {
    setOpen(false)
    exportAs(format)
  }

  const disabled = !isReady
  const menuLabel = t('common.tableExport.menuLabel')
  const emptyTitle = disabled ? t('common.tableExport.emptyDisabled') : undefined

  return (
    <div className="data-table-export-menu" ref={wrapperRef}>
      <button
        type="button"
        className="btn btn-secondary btn-sm data-table-export-menu__trigger"
        onClick={() => setOpen(prev => !prev)}
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        title={emptyTitle}
      >
        <span>{menuLabel}</span>
        <ChevronDown
          className={`data-table-export-menu__chevron${open ? ' is-open' : ''}`}
          aria-hidden="true"
          size={14}
          strokeWidth={1.8}
        />
      </button>
      {open && (
        <div
          className="data-table-export-menu__panel"
          role="menu"
          aria-label={menuLabel}
        >
          <button
            type="button"
            className="data-table-export-menu__item"
            role="menuitem"
            onClick={() => handlePick('csv')}
          >
            {t('common.tableExport.csvOption')}
          </button>
          <button
            type="button"
            className="data-table-export-menu__item"
            role="menuitem"
            onClick={() => handlePick('json')}
          >
            {t('common.tableExport.jsonOption')}
          </button>
        </div>
      )}
    </div>
  )
}

interface PaginationProps {
  page: number
  totalPages: number
  onPageChange: (page: number) => void
  /** Optional page-size selector wired in by DataTable when callers opt in
   *  via `pageSizeOptions`. The selector renders inline at the right edge of
   *  the pagination row so it stays adjacent to the page-jump controls. */
  pageSizeSelector?: {
    options: number[]
    value: number
    onChange: (size: number) => void
  }
}

/**
 * Pagination row rendered beneath the table when totalPages > 1.
 *
 * Layout (desktop ≥641px):
 *   [previous] [1] [2] … [5] [6] [7] … [99] [next] 페이지 [_5_] / 99 [이동]
 *
 * Layout (mobile ≤640px): [previous] N/M [next] 페이지 [_5_] / 99 [이동]
 *   The numbered button row collapses; previous/next controls + numeric N/M label + jump-input
 *   stay so the user can still navigate without the wide button group.
 */
function Pagination({ page, totalPages, onPageChange, pageSizeSelector }: PaginationProps) {
  const { t } = useTranslation()
  const isMobile = useIsPaginationMobile()
  const [jumpDraft, setJumpDraft] = useState<string>(String(page))
  // Stable per-instance id so multiple DataTables on the same screen do not
  // collide when wiring the jump-input ↔ label association.
  const jumpInputId = useId()
  const pageSizeSelectId = useId()

  // Keep the visible jump-input synced when external page changes (URL state,
  // sort reset, parent-driven nav). The user's own typing wins until commit.
  useEffect(() => {
    setJumpDraft(String(page))
  }, [page])

  const commitJump = () => {
    const parsed = Number.parseInt(jumpDraft, 10)
    if (!Number.isFinite(parsed)) {
      setJumpDraft(String(page))
      return
    }
    const clamped = Math.min(totalPages, Math.max(1, parsed))
    setJumpDraft(String(clamped))
    if (clamped !== page) onPageChange(clamped)
  }

  const handleJumpKey = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      commitJump()
    }
  }

  const items = pageRange(page, totalPages)

  return (
    <nav
      className="table-pagination"
      role="navigation"
      aria-label={t('common.pagination.navLabel')}
    >
      <button
        type="button"
        className="btn btn-sm btn-secondary table-pagination__nav"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        aria-label={t('common.pagination.previousPage')}
      >
        <ChevronLeft aria-hidden="true" size={16} strokeWidth={1.8} />
      </button>

      {!isMobile && (
        <ol className="table-pagination__pages" aria-label={t('common.pagination.pagesLabel')}>
          {items.map((item, index) =>
            item === 'ellipsis' ? (
              <li
                key={`ellipsis-${index}`}
                className="table-pagination__ellipsis"
                aria-hidden="true"
              >
                …
              </li>
            ) : (
              <li key={item}>
                <button
                  type="button"
                  className="table-pagination__page-btn"
                  aria-current={item === page ? 'page' : undefined}
                  aria-label={t('common.pagination.gotoPage', { page: item })}
                  onClick={() => {
                    if (item !== page) onPageChange(item)
                  }}
                >
                  {item}
                </button>
              </li>
            ),
          )}
        </ol>
      )}

      {isMobile && (
        <span className="table-pagination-info" aria-live="polite">
          {t('common.pagination.pageOf', { current: page, total: totalPages })}
        </span>
      )}

      <button
        type="button"
        className="btn btn-sm btn-secondary table-pagination__nav"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
        aria-label={t('common.pagination.nextPage')}
      >
        <ChevronRight aria-hidden="true" size={16} strokeWidth={1.8} />
      </button>

      <span className="table-pagination__jump">
        <label className="table-pagination__jump-label" htmlFor={jumpInputId}>
          {t('common.pagination.pageLabel')}
        </label>
        <input
          id={jumpInputId}
          type="number"
          inputMode="numeric"
          min={1}
          max={totalPages}
          value={jumpDraft}
          onChange={event => setJumpDraft(event.target.value)}
          onKeyDown={handleJumpKey}
          onBlur={() => {
            // Quietly snap back to the current page when the user blurs an
            // empty / unparseable draft without committing. Avoids surprising
            // page jumps from accidental focus loss.
            if (jumpDraft.trim() === '') setJumpDraft(String(page))
          }}
          className="table-pagination__jump-input"
          aria-label={t('common.pagination.jumpInputLabel', { total: totalPages })}
        />
        <span className="table-pagination__jump-separator" aria-hidden="true">
          / {totalPages}
        </span>
        <button
          type="button"
          className="btn btn-sm btn-secondary table-pagination__jump-btn"
          onClick={commitJump}
        >
          {t('common.pagination.goAction')}
        </button>
      </span>

      {pageSizeSelector && (
        <span className="table-pagination__page-size">
          <label
            className="table-pagination__page-size-label"
            htmlFor={pageSizeSelectId}
          >
            {t('common.pagination.pageSizeLabel')}
          </label>
          <select
            id={pageSizeSelectId}
            className="table-pagination__page-size-select"
            value={pageSizeSelector.value}
            onChange={(event) => {
              const next = Number.parseInt(event.target.value, 10)
              if (Number.isFinite(next) && next > 0) {
                pageSizeSelector.onChange(next)
              }
            }}
            aria-label={t('common.pagination.pageSizeLabel')}
          >
            {pageSizeSelector.options.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
          <span className="table-pagination__page-size-suffix" aria-hidden="true">
            {t('common.pagination.pageSizeSuffix')}
          </span>
        </span>
      )}
    </nav>
  )
}

export function DataTable<T>({
  columns,
  data,
  keyFn,
  onRowClick,
  selectedKey,
  rowClassName,
  page,
  pageSize,
  totalCount,
  onPageChange,
  sortKey,
  sortDirection,
  onSort,
  tableId,
  urlStateKey,
  exportable,
  rowActions,
  pageSizeOptions,
  defaultPageSize,
  onPageSizeChange,
  selectable = false,
  bulkActions,
  rowSelectable,
  keepSelectionAcrossDataChange = false,
}: DataTableProps<T>) {
  const { t } = useTranslation()
  const { announce } = useAnnouncer()

  // Single mounted RowContextMenu shared across all rows. Tracks which row
  // opened the menu and where to anchor it (viewport coordinates).
  const hasRowActions = !!rowActions && rowActions.length > 0
  const [menuState, setMenuState] = useState<{
    row: T
    position: { x: number; y: number }
  } | null>(null)
  const closeMenu = () => setMenuState(null)
  const openMenu = (row: T, x: number, y: number) => {
    if (!hasRowActions) return
    setMenuState({ row, position: { x, y } })
  }

  // ── Bulk selection state ──
  // Track selected row keys (keyFn output) plus the anchor index for
  // Shift+Click range selection. When `selectable` is false the entire
  // bulk-selection branch short-circuits below so non-migrated callers stay
  // on the legacy render path.
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => new Set())
  const lastToggledIndexRef = useRef<number | null>(null)
  // Captured from the row checkbox `onClick` and consumed by the immediately
  // following `onChange`. The browser fires click → change synchronously when
  // a checkbox toggles, but the ChangeEvent does not expose `shiftKey`, so we
  // bridge the two via a ref.
  const shiftKeySnapshotRef = useRef<boolean>(false)
  // Track the running `perform` so the bar can render a busy state and we
  // can suppress duplicate fires while a request is in flight.
  const [pendingActionId, setPendingActionId] = useState<string | null>(null)
  // Action awaiting confirmation (when `confirmMessage` returns a string).
  const [confirmingAction, setConfirmingAction] = useState<{
    action: BulkAction<T>
    message: string
    rows: T[]
  } | null>(null)

  // Selectable rows in the *current* `data` slice. Used for select-all toggling
  // and Shift+Click range bounds. Filtered through `rowSelectable` so disabled
  // rows are never auto-selected.
  const selectableRowKeys: string[] = selectable
    ? data
        .filter(row => !rowSelectable || rowSelectable(row))
        .map(row => keyFn(row))
    : []

  const selectedCount = selectedKeys.size
  const allSelectableSelected =
    selectableRowKeys.length > 0 &&
    selectableRowKeys.every(key => selectedKeys.has(key))
  const someSelectableSelected =
    selectableRowKeys.some(key => selectedKeys.has(key))

  function clearSelection() {
    setSelectedKeys(new Set())
    lastToggledIndexRef.current = null
  }

  function toggleSelectionFor(key: string) {
    setSelectedKeys(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  function selectRange(fromIndex: number, toIndex: number) {
    const start = Math.min(fromIndex, toIndex)
    const end = Math.max(fromIndex, toIndex)
    setSelectedKeys(prev => {
      const next = new Set(prev)
      for (let i = start; i <= end; i++) {
        const key = selectableRowKeys[i]
        if (key != null) next.add(key)
      }
      return next
    })
  }

  function handleSelectAllChange(checked: boolean) {
    if (!checked) {
      clearSelection()
      return
    }
    setSelectedKeys(new Set(selectableRowKeys))
  }

  // Reset selection when the *content* of the data changes (a new query
  // refresh, sort, or filter pass). We hash the row keys so identity-only
  // re-renders (e.g. parent slicing the array each render) do not clear an
  // active selection. Caller can opt out via `keepSelectionAcrossDataChange`.
  const dataKeyHash = selectable
    ? data.map(row => keyFn(row)).join('')
    : ''
  const prevDataHashRef = useRef<string | null>(null)
  useEffect(() => {
    if (!selectable) return
    if (keepSelectionAcrossDataChange) {
      prevDataHashRef.current = dataKeyHash
      return
    }
    if (prevDataHashRef.current === null) {
      prevDataHashRef.current = dataKeyHash
      return
    }
    if (prevDataHashRef.current !== dataKeyHash) {
      prevDataHashRef.current = dataKeyHash
      clearSelection()
    }
  }, [dataKeyHash, selectable, keepSelectionAcrossDataChange])

  // Announce selection-count changes to screen readers. Skip the very first
  // render so AT does not hear "0 selected" on mount.
  const prevSelectedCountRef = useRef<number>(0)
  useEffect(() => {
    if (!selectable) return
    if (prevSelectedCountRef.current === selectedCount) return
    prevSelectedCountRef.current = selectedCount
    if (selectedCount > 0) {
      announce(t('common.bulk.selectedCount', { count: selectedCount }))
    }
  }, [selectable, selectedCount, announce, t])

  async function runBulkAction(action: BulkAction<T>) {
    if (pendingActionId) return
    const rows = data.filter(row => selectedKeys.has(keyFn(row)))
    if (rows.length === 0) return
    setPendingActionId(action.id)
    try {
      await action.perform(rows)
      announce(
        t('common.bulk.actionCompleted', {
          label: action.label,
          count: rows.length,
        }),
      )
      clearSelection()
    } finally {
      setPendingActionId(null)
    }
  }

  function requestBulkAction(action: BulkAction<T>) {
    const rows = data.filter(row => selectedKeys.has(keyFn(row)))
    if (rows.length === 0) return
    if (action.confirmMessage) {
      const message = action.confirmMessage(rows)
      if (message) {
        setConfirmingAction({ action, message, rows })
        return
      }
    }
    void runBulkAction(action)
  }

  const [resizedWidths, setResizedWidths] = useState<Record<string, number>>(() =>
    readStoredWidths(tableId),
  )
  const thRefs = useRef<Record<string, HTMLTableCellElement | null>>({})

  useEffect(() => {
    if (!tableId) return
    writeStoredWidths(tableId, resizedWidths)
  }, [tableId, resizedWidths])

  // Page-size selector wiring (opt-in via `pageSizeOptions`). The parent owns
  // the authoritative `pageSize`; DataTable seeds it on mount from
  // URL (`${urlStateKey}_ps`) → localStorage → `defaultPageSize` → 25, then
  // emits `onPageSizeChange` so the parent updates its slicing math. Effects
  // fire only when the caller has opted in so non-migrated callers stay on
  // the legacy code path. The URL bridge owns ongoing back/forward syncing
  // when `urlStateKey` is set, so the mount-only seed below skips URL when
  // the bridge will handle it.
  const pageSizeSelectorEnabled = !!pageSizeOptions && pageSizeOptions.length > 0
  const resolvedDefaultPageSize = defaultPageSize ?? 25
  const seededPageSizeRef = useRef(false)
  useEffect(() => {
    if (!pageSizeSelectorEnabled || seededPageSizeRef.current) return
    seededPageSizeRef.current = true
    if (!onPageSizeChange) return
    // When URL state is wired in, the bridge synchronously surfaces the URL
    // value on its first effect — fall through to the bridge so we do not
    // race two emits. localStorage is still the responsibility of this seed
    // because the bridge cannot read storage.
    if (urlStateKey) {
      // Only seed from localStorage when the URL does NOT already carry a
      // `_ps` value. Otherwise the URL wins and the bridge handles it.
      if (typeof window !== 'undefined') {
        const params = new URLSearchParams(window.location.search)
        if (params.get(`${urlStateKey}_ps`)) return
      }
    }
    const stored = readStoredPageSize(tableId)
    if (stored == null) return
    if (stored === pageSize) return
    onPageSizeChange(stored)
  // Mount-only seed; we deliberately skip the rest of the dependency array so
  // a parent re-render does not re-trigger the seed (the ref guard would
  // already short-circuit, but tracking only the gates documents intent).
  }, [pageSizeSelectorEnabled, tableId, urlStateKey])

  const handleSelectorChange = (next: number) => {
    if (!pageSizeSelectorEnabled) return
    if (tableId) writeStoredPageSize(tableId, next)
    onPageSizeChange?.(next)
    // Always reset to the first page so the slice math stays sane after the
    // window grows / shrinks. The URL bridge writes the new `_ps` (and
    // implicitly clears `_p` because page === 1).
    onPageChange?.(1)
  }

  // Responsive column dropping: active only when at least one column opts in.
  const hasResponsiveColumns = columns.some(isLowPriorityColumn)
  const isNarrow = useIsNarrowViewport(hasResponsiveColumns)
  const responsiveActive = hasResponsiveColumns && isNarrow

  const visibleColumns = responsiveActive
    ? columns.filter(col => !isLowPriorityColumn(col))
    : columns
  const hiddenColumns = responsiveActive
    ? columns.filter(isLowPriorityColumn)
    : []

  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({})

  const toggleExpanded = (rowKey: string) => {
    setExpandedRows(prev => ({ ...prev, [rowKey]: !prev[rowKey] }))
  }

  // Render-time gate: treat the expander state as empty when responsive mode
  // is off so a width-reflow up/down cycle never leaks stale open rows. We
  // avoid an effect + setState because that would cascade an extra render.
  const activeExpandedRows: Record<string, boolean> = responsiveActive ? expandedRows : {}

  const isPaginated =
    page != null && pageSize != null && totalCount != null && onPageChange != null
  const totalPages = isPaginated ? Math.max(1, Math.ceil(totalCount / pageSize)) : 1

  // Announce filtered row-count changes to screen readers. When the caller
  // paginates we treat `totalCount` as the filtered total (what applying a
  // filter changes) and the current page `data.length` as `shown`. Without
  // pagination both collapse to the plain data length.
  //
  // We skip the very first render so AT does not hear an announcement on
  // page load — only when the filtered total changes afterwards.
  const filteredTotal = totalCount ?? data.length
  const shownOnPage = data.length
  const prevTotalRef = useRef<number | null>(null)
  useEffect(() => {
    if (prevTotalRef.current == null) {
      prevTotalRef.current = filteredTotal
      return
    }
    if (prevTotalRef.current !== filteredTotal) {
      prevTotalRef.current = filteredTotal
      announce(
        t('common.a11y.filteredRowCount', { shown: shownOnPage, total: filteredTotal }),
      )
    }
  }, [filteredTotal, shownOnPage, announce, t])

  const handleHeaderClick = (col: Column<T>) => {
    if (!col.sortable || !onSort) return
    const nextDirection =
      sortKey === col.key ? getNextSortDirection(sortDirection ?? null) : 'asc'
    onSort(col.key, nextDirection)
  }

  const applyWidth = (key: string, nextWidth: number): void => {
    const clamped = Math.max(MIN_COLUMN_WIDTH_PX, Math.round(nextWidth))
    setResizedWidths(prev => {
      if (prev[key] === clamped) return prev
      return { ...prev, [key]: clamped }
    })
  }

  const startPointerResize = (
    event: React.PointerEvent<HTMLSpanElement>,
    col: Column<T>,
  ) => {
    event.preventDefault()
    event.stopPropagation()
    const th = thRefs.current[col.key]
    if (!th) return
    const startX = event.clientX
    const startWidth = resizedWidths[col.key] ?? th.getBoundingClientRect().width

    const handleMove = (moveEvent: PointerEvent) => {
      const delta = moveEvent.clientX - startX
      applyWidth(col.key, startWidth + delta)
    }
    const handleUp = () => {
      window.removeEventListener('pointermove', handleMove)
      window.removeEventListener('pointerup', handleUp)
      window.removeEventListener('pointercancel', handleUp)
    }
    window.addEventListener('pointermove', handleMove)
    window.addEventListener('pointerup', handleUp)
    window.addEventListener('pointercancel', handleUp)
  }

  const handleHandleKeyDown = (
    event: React.KeyboardEvent<HTMLSpanElement>,
    col: Column<T>,
  ) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    event.stopPropagation()
    const th = thRefs.current[col.key]
    const current = resizedWidths[col.key] ?? th?.getBoundingClientRect().width ?? 0
    const delta = event.key === 'ArrowRight' ? KEYBOARD_RESIZE_STEP_PX : -KEYBOARD_RESIZE_STEP_PX
    applyWidth(col.key, current + delta)
  }

  const resolveThStyle = (col: Column<T>): React.CSSProperties | undefined => {
    const resized = resizedWidths[col.key]
    if (resized != null) return { width: `${resized}px` }
    if (col.width) return { width: col.width }
    return undefined
  }

  const renderCell = (col: Column<T>, row: T, keySuffix: string) => {
    const isActiveSort = sortKey === col.key && !!sortDirection

    // Inline-edit branch — replaces the column's `render` output with an
    // `InlineCellEdit`. The display string is derived from the editable
    // value (so the cell stays consistent across read/write modes); callers
    // can override via `inlineEdit.format`. Truncation CSS does not apply
    // here because the editor needs room to grow.
    if (col.inlineEdit) {
      const editValue = col.inlineEdit.getValue(row)
      const isDisabled = col.inlineEdit.disabled ? col.inlineEdit.disabled(row) : false
      const cellClasses = [isActiveSort ? 'col-sort-active' : ''].filter(Boolean).join(' ')
      return (
        <td key={`${col.key}-${keySuffix}`} className={cellClasses || undefined}>
          <InlineCellEdit<unknown>
            value={editValue}
            type={col.inlineEdit.type}
            options={col.inlineEdit.options}
            format={col.inlineEdit.format}
            validate={col.inlineEdit.validate}
            commitOnBlur={col.inlineEdit.commitOnBlur}
            ariaLabel={col.inlineEdit.ariaLabel?.(row)}
            disabled={isDisabled}
            onCommit={(next) => col.inlineEdit!.onCommit(row, next)}
          />
        </td>
      )
    }

    const rendered = col.render(row)
    const isString = typeof rendered === 'string'
    const shouldTruncate = isString && col.truncate !== false
    const cellClasses = [
      shouldTruncate ? 'data-table-cell-truncate' : '',
      isActiveSort ? 'col-sort-active' : '',
    ].filter(Boolean).join(' ')
    return (
      <td
        key={`${col.key}-${keySuffix}`}
        className={cellClasses || undefined}
        title={shouldTruncate ? (rendered as string) : undefined}
      >
        {rendered}
      </td>
    )
  }

  // colSpan for the expander row needs to count: visible columns + leading
  // expander column (if responsive) + leading selection column (if selectable)
  // + trailing trigger column (if rowActions).
  const trailingActionColumns = hasRowActions ? 1 : 0
  const leadingSelectionColumns = selectable ? 1 : 0
  const expanderColumnCount =
    visibleColumns.length + 1 + trailingActionColumns + leadingSelectionColumns

  // Resolve export columns once per render. The cost is small (a column-count
  // map + filter), so we skip useMemo and let the React Compiler memoise.
  const resolvedExportColumns: ExportColumn<T>[] | null = exportable
    ? exportable.columns ?? deriveExportColumns(columns)
    : null

  return (
    <div className="table-wrapper">
      {urlStateKey && (
        <UrlStateBridge
          urlStateKey={urlStateKey}
          page={page}
          sortKey={sortKey}
          sortDirection={sortDirection}
          onPageChange={onPageChange}
          onSort={onSort}
          pageSize={pageSizeSelectorEnabled ? pageSize : undefined}
          onPageSizeChange={pageSizeSelectorEnabled ? onPageSizeChange : undefined}
          defaultPageSize={pageSizeSelectorEnabled ? resolvedDefaultPageSize : undefined}
        />
      )}
      {exportable && resolvedExportColumns && (
        <div className="data-table-toolbar">
          <ExportMenu
            filename={exportable.filename}
            exportColumns={resolvedExportColumns as ExportColumn<unknown>[]}
            rows={data as unknown[]}
            fallbackEmpty={exportable.fallbackEmpty}
          />
        </div>
      )}
      {hasRowActions && menuState && (
        // Key on the position so a right-click that re-targets a different row
        // remounts the menu (resetting active selection / clamp visibility).
        <RowContextMenu<T>
          key={`${menuState.position.x}:${menuState.position.y}`}
          row={menuState.row}
          actions={rowActions!}
          position={menuState.position}
          onClose={closeMenu}
        />
      )}
      {selectable && selectedCount > 0 && (
        <div
          className="data-table-bulk-bar"
          role="region"
          aria-label={t('common.bulk.barLabel')}
        >
          <span className="data-table-bulk-bar__count">
            {t('common.bulk.selectedCount', { count: selectedCount })}
          </span>
          <div className="data-table-bulk-bar__actions">
            {(bulkActions ?? []).map(action => {
              const rows = data.filter(row => selectedKeys.has(keyFn(row)))
              if (action.hidden && action.hidden(rows)) return null
              const isDisabled =
                (action.disabled && action.disabled(rows)) ||
                (pendingActionId !== null && pendingActionId !== action.id)
              const isOperating = pendingActionId === action.id
              const variant: OperationButtonVariant = action.variant ?? 'secondary'
              return (
                <OperationButton
                  key={action.id}
                  variant={variant}
                  className="btn-sm"
                  isOperating={isOperating}
                  disabled={isDisabled}
                  onClick={() => requestBulkAction(action)}
                >
                  {action.icon != null && (
                    <span aria-hidden="true" className="data-table-bulk-bar__icon">
                      {action.icon}
                    </span>
                  )}
                  <span>{action.label}</span>
                </OperationButton>
              )
            })}
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={clearSelection}
              disabled={pendingActionId !== null}
            >
              {t('common.bulk.clearSelection')}
            </button>
          </div>
        </div>
      )}
      {confirmingAction && (
        <ConfirmDialog
          title={confirmingAction.action.label}
          message={confirmingAction.message}
          danger={confirmingAction.action.variant === 'danger'}
          onCancel={() => setConfirmingAction(null)}
          onConfirm={() => {
            const action = confirmingAction.action
            setConfirmingAction(null)
            void runBulkAction(action)
          }}
        />
      )}
      <table className={`data-table${responsiveActive ? ' data-table--responsive' : ''}`}>
        <thead>
          <tr>
            {selectable && (
              <th
                scope="col"
                className="data-table-select-col"
                aria-label={t('common.bulk.selectAll')}
              >
                <input
                  type="checkbox"
                  className="data-table-select-checkbox"
                  aria-label={t('common.bulk.selectAll')}
                  checked={allSelectableSelected}
                  ref={(el) => {
                    if (el) {
                      el.indeterminate = !allSelectableSelected && someSelectableSelected
                    }
                  }}
                  disabled={
                    selectableRowKeys.length === 0 || pendingActionId !== null
                  }
                  onChange={(e) => handleSelectAllChange(e.target.checked)}
                />
              </th>
            )}
            {responsiveActive && (
              <th
                scope="col"
                className="data-table-expander-col"
                aria-label={t('common.table.detailsColumn', { defaultValue: 'Row details' })}
              />
            )}
            {visibleColumns.map(col => {
              const isSortable = col.sortable && onSort
              const activeDirection = isSortable
                ? getActiveSortDirection(col.key, sortKey, sortDirection)
                : null
              const headerClasses = [
                isSortable ? 'sortable-header' : '',
                activeDirection ? 'sortable-header--active' : '',
              ].filter(Boolean).join(' ')
              const thNode = (
                <th
                  key={col.key}
                  ref={el => { thRefs.current[col.key] = el }}
                  scope="col"
                  style={resolveThStyle(col)}
                  className={headerClasses || undefined}
                  onClick={isSortable ? () => handleHeaderClick(col) : undefined}
                  onKeyDown={isSortable ? (e: React.KeyboardEvent) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      handleHeaderClick(col)
                    }
                  } : undefined}
                  tabIndex={isSortable ? 0 : undefined}
                  role={isSortable ? 'button' : undefined}
                  aria-sort={isSortable ? getAriaSortValue(col.key, sortKey, sortDirection) : undefined}
                >
                  {col.header}
                  {isSortable && <SortIcon direction={activeDirection} />}
                  {col.resizable && (
                    <Tooltip content={t('common.tooltip.resizeColumn')} placement="bottom">
                      <span
                        className="data-table-resize-handle"
                        role="separator"
                        aria-orientation="vertical"
                        aria-label={t('common.aria.resizeColumn', { defaultValue: 'Resize column' })}
                        tabIndex={0}
                        onPointerDown={e => startPointerResize(e, col)}
                        onKeyDown={e => handleHandleKeyDown(e, col)}
                        onClick={e => e.stopPropagation()}
                      />
                    </Tooltip>
                  )}
                </th>
              )
              if (isSortable) {
                return (
                  <Tooltip
                    key={col.key}
                    content={t('common.tooltip.sortColumn')}
                    placement="bottom"
                  >
                    {thNode}
                  </Tooltip>
                )
              }
              return thNode
            })}
            {hasRowActions && (
              <th
                scope="col"
                className="data-table-row-trigger-cell"
                aria-label={t('common.rowActions.menuLabel')}
              />
            )}
          </tr>
        </thead>
        <tbody>
          {data.map(row => {
            const rowKey = keyFn(row)
            const isExpanded = !!activeExpandedRows[rowKey]
            const isBulkSelected = selectable && selectedKeys.has(rowKey)
            const isRowSelectable =
              selectable && (!rowSelectable || rowSelectable(row))
            const selectableIndex = isRowSelectable
              ? selectableRowKeys.indexOf(rowKey)
              : -1
            const classes = [
              onRowClick ? 'clickable' : '',
              selectedKey != null && selectedKey === rowKey ? 'is-selected' : '',
              isBulkSelected ? 'is-bulk-selected' : '',
              rowClassName ? rowClassName(row) : '',
            ].filter(Boolean).join(' ')

            // Compose the per-row keydown handler so both onRowClick (Enter/
            // Space) and rowActions (Shift+Enter) can coexist on the same row
            // without one shadowing the other.
            const handleRowKeyDown = (onRowClick || hasRowActions)
              ? (e: React.KeyboardEvent<HTMLTableRowElement>) => {
                  if (hasRowActions && e.key === 'Enter' && e.shiftKey) {
                    e.preventDefault()
                    const rect = (e.currentTarget as HTMLTableRowElement).getBoundingClientRect()
                    openMenu(row, rect.right - 8, rect.bottom)
                    return
                  }
                  if (onRowClick && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault()
                    onRowClick(row)
                  }
                }
              : undefined

            const handleRowContextMenu = hasRowActions
              ? (e: React.MouseEvent<HTMLTableRowElement>) => {
                  e.preventDefault()
                  openMenu(row, e.clientX, e.clientY)
                }
              : undefined

            return (
              <Fragment key={rowKey}>
                <tr
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onContextMenu={handleRowContextMenu}
                  onKeyDown={handleRowKeyDown}
                  tabIndex={(onRowClick || hasRowActions) ? 0 : undefined}
                  role={onRowClick ? 'button' : undefined}
                  className={classes || undefined}
                >
                  {selectable && (
                    <td
                      className="data-table-select-cell"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        className="data-table-select-checkbox"
                        aria-label={t('common.bulk.selectRow')}
                        checked={isBulkSelected}
                        disabled={!isRowSelectable || pendingActionId !== null}
                        // Snapshot shift-key state from the click event before
                        // the change handler fires (ChangeEvent does not
                        // surface `shiftKey`). The shift snapshot lives in a
                        // ref so it is accurate even when React batches the
                        // click → change transition.
                        onClick={(e) => {
                          e.stopPropagation()
                          shiftKeySnapshotRef.current = e.shiftKey
                        }}
                        onChange={() => {
                          if (!isRowSelectable) return
                          const anchor = lastToggledIndexRef.current
                          const shift = shiftKeySnapshotRef.current
                          shiftKeySnapshotRef.current = false
                          if (shift && anchor != null && anchor !== selectableIndex) {
                            selectRange(anchor, selectableIndex)
                          } else {
                            toggleSelectionFor(rowKey)
                          }
                          lastToggledIndexRef.current = selectableIndex
                        }}
                        onKeyDown={(e) => {
                          if (e.key === ' ') {
                            e.preventDefault()
                            if (!isRowSelectable) return
                            const anchor = lastToggledIndexRef.current
                            if (e.shiftKey && anchor != null && anchor !== selectableIndex) {
                              selectRange(anchor, selectableIndex)
                            } else {
                              toggleSelectionFor(rowKey)
                            }
                            lastToggledIndexRef.current = selectableIndex
                          }
                        }}
                      />
                    </td>
                  )}
                  {responsiveActive && (
                    <td className="data-table-expander-cell">
                      <button
                        type="button"
                        className={`data-table-expander${isExpanded ? ' is-expanded' : ''}`}
                        aria-expanded={isExpanded}
                        aria-label={
                          isExpanded
                            ? t('common.table.hideDetails', { defaultValue: 'Hide details' })
                            : t('common.table.showDetails', { defaultValue: 'Show details' })
                        }
                        onClick={(e) => {
                          e.stopPropagation()
                          toggleExpanded(rowKey)
                        }}
                      >
                        <ChevronRight
                          className="data-table-expander__chevron"
                          aria-hidden="true"
                          size={16}
                          strokeWidth={1.8}
                        />
                        <span className="data-table-expander-label">
                          {t('common.table.details', { defaultValue: 'Details' })}
                        </span>
                      </button>
                    </td>
                  )}
                  {visibleColumns.map(col => renderCell(col, row, rowKey))}
                  {hasRowActions && (
                    <td className="data-table-row-trigger-cell">
                      <button
                        type="button"
                        className="data-table-row-trigger"
                        aria-label={t('common.rowActions.menuLabel')}
                        aria-haspopup="menu"
                        onClick={(e) => {
                          e.stopPropagation()
                          const rect = (e.currentTarget as HTMLButtonElement).getBoundingClientRect()
                          openMenu(row, rect.left, rect.bottom)
                        }}
                      >
                        <MoreVertical aria-hidden="true" size={16} strokeWidth={1.8} />
                      </button>
                    </td>
                  )}
                </tr>
                {isExpanded && hiddenColumns.length > 0 && (
                  <tr className="data-table-expanded-row">
                    <td colSpan={expanderColumnCount}>
                      <dl className="data-table-expanded-grid">
                        {hiddenColumns.map(col => (
                          <div className="data-table-expanded-item" key={`exp-${col.key}-${rowKey}`}>
                            <dt>{col.header}</dt>
                            <dd>{col.render(row)}</dd>
                          </div>
                        ))}
                      </dl>
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>

      {isPaginated && (totalPages > 1 || pageSizeSelectorEnabled) && (
        <Pagination
          page={page}
          totalPages={totalPages}
          onPageChange={onPageChange}
          pageSizeSelector={
            pageSizeSelectorEnabled
              ? {
                  options: pageSizeOptions!,
                  value: pageSize,
                  onChange: handleSelectorChange,
                }
              : undefined
          }
        />
      )}
    </div>
  )
}

import { downloadFile } from './downloadFile'
import { formatDateCompact } from './formatters'

/**
 * Supported export formats for table downloads.
 */
export type ExportFormat = 'csv' | 'json'

/**
 * Per-column export descriptor.
 *
 * `accessor` returns the raw, exportable value for a row. When omitted, the
 * hook falls back to `row[key]` and stringifies the result. Cells whose
 * runtime value is a non-stringifiable ReactNode (function, JSX element,
 * symbol) should provide an explicit `accessor` so downstream consumers do
 * not see "[object Object]" in their exports.
 */
export interface ExportColumn<T> {
  /** Stable identifier — must match the DataTable column key when paired. */
  key: string
  /** Display label written into the CSV header row and JSON object key. */
  header: string
  /** Optional accessor returning the exportable cell value. */
  accessor?: (row: T) => string | number | boolean | null | undefined
}

export interface UseTableExportOptions<T> {
  /** Filename base without extension or date — the hook appends `-YYYY-MM-DD.<ext>`. */
  filename: string
  /** Rows currently visible to the user (after filters / sorts have been applied). */
  rows: T[]
  /** Column descriptors — order is preserved in CSV columns and JSON object keys. */
  columns: ExportColumn<T>[]
  /** Token written for null/undefined values in CSV output. Default: `'-'`. */
  fallbackEmpty?: string
}

export interface TableExportApi {
  /** Triggers a file download in the requested format. No-op when there are no rows. */
  exportAs: (format: ExportFormat) => void
  /** True when at least one row is available to export. */
  isReady: boolean
}

/**
 * UTF-8 BOM character. Excel on Korean Windows requires this prefix to detect
 * the file as UTF-8; without it Korean characters render as mojibake.
 */
const UTF8_BOM = '﻿'

/**
 * Escapes a single CSV cell. RFC 4180-compatible:
 *  - Wraps the value in double quotes when it contains `,`, `"`, `\n`, or `\r`.
 *  - Doubles any internal `"` so they survive the quoted-field encoding.
 */
function escapeCsvCell(value: string): string {
  if (/[",\n\r]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`
  }
  return value
}

/**
 * Stringifies a raw cell value for CSV output. Booleans and numbers are
 * passed through `String(...)`; null/undefined falls back to `fallbackEmpty`.
 */
function csvStringify(value: unknown, fallbackEmpty: string): string {
  if (value === null || value === undefined) return fallbackEmpty
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  // Defensive: should not happen if accessors return primitives, but keeps
  // the export from emitting "[object Object]" if a caller forgets.
  try {
    return JSON.stringify(value)
  } catch {
    return fallbackEmpty
  }
}

function resolveCellValue<T>(
  column: ExportColumn<T>,
  row: T,
): string | number | boolean | null | undefined {
  if (column.accessor) return column.accessor(row)
  // Fallback: read row[key] when no accessor is provided. Only primitive
  // values are usable; anything else is coerced via JSON.stringify in
  // `csvStringify` / left as-is for JSON output.
  const value = (row as Record<string, unknown>)[column.key]
  if (
    value === null ||
    value === undefined ||
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
  ) {
    return value
  }
  return undefined
}

/**
 * Builds the full CSV body — header row plus all data rows joined by `\n`.
 * The leading UTF-8 BOM is added by the caller (so callers writing the
 * payload to a non-Excel sink can omit it).
 */
function buildCsv<T>(
  columns: ExportColumn<T>[],
  rows: T[],
  fallbackEmpty: string,
): string {
  const header = columns.map(col => escapeCsvCell(col.header)).join(',')
  const body = rows.map(row =>
    columns
      .map(col => escapeCsvCell(csvStringify(resolveCellValue(col, row), fallbackEmpty)))
      .join(','),
  )
  return [header, ...body].join('\n')
}

/**
 * Builds the JSON payload — an array of plain objects keyed by `column.key`,
 * with cell values resolved via `accessor`. Pretty-printed with 2-space
 * indentation for human readability.
 */
function buildJson<T>(columns: ExportColumn<T>[], rows: T[]): string {
  const records = rows.map(row => {
    const record: Record<string, string | number | boolean | null> = {}
    for (const col of columns) {
      const value = resolveCellValue(col, row)
      record[col.key] = value === undefined ? null : value
    }
    return record
  })
  return JSON.stringify(records, null, 2)
}

/**
 * `useTableExport` — produce CSV / JSON downloads from in-memory table rows.
 *
 * The hook is intentionally a pure factory (no internal state, no effects)
 * so the React Compiler can hoist it freely and so callers can re-derive
 * `exportAs` per render without extra useCallback wrapping. All work happens
 * lazily inside `exportAs`; constructing the hook never serialises the rows.
 *
 * Filename pattern: `${filename}-${YYYY-MM-DD}.${ext}` — date is the local
 * time-zone "today" via `formatDateCompact`.
 */
export function useTableExport<T>(options: UseTableExportOptions<T>): TableExportApi {
  const { filename, rows, columns, fallbackEmpty = '-' } = options
  const isReady = rows.length > 0

  const exportAs = (format: ExportFormat): void => {
    if (!isReady) return
    const today = formatDateCompact(new Date())
    const safeBase = filename || 'table-export'
    if (format === 'csv') {
      const csv = buildCsv(columns, rows, fallbackEmpty)
      downloadFile(UTF8_BOM + csv, `${safeBase}-${today}.csv`, 'text/csv;charset=utf-8;')
      return
    }
    // JSON
    const json = buildJson(columns, rows)
    downloadFile(json, `${safeBase}-${today}.json`, 'application/json')
  }

  return { exportAs, isReady }
}

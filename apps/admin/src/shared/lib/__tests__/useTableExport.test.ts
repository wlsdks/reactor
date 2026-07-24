import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useTableExport, type ExportColumn } from '../useTableExport'
import * as downloadFileMod from '../downloadFile'

interface Row {
  id: string
  name: string
  count: number
  active: boolean
  notes: string | null
}

const sampleColumns: ExportColumn<Row>[] = [
  { key: 'id', header: 'ID', accessor: r => r.id },
  { key: 'name', header: 'Name', accessor: r => r.name },
  { key: 'count', header: 'Count', accessor: r => r.count },
  { key: 'active', header: 'Active', accessor: r => r.active },
  { key: 'notes', header: 'Notes', accessor: r => r.notes },
]

const sampleRows: Row[] = [
  { id: '1', name: 'Alice', count: 10, active: true, notes: 'first' },
  { id: '2', name: 'Bob, Jr.', count: 5, active: false, notes: 'has "quote"' },
  { id: '3', name: 'Line\nBreak', count: 0, active: true, notes: null },
]

describe('useTableExport', () => {
  let downloadSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    downloadSpy = vi.spyOn(downloadFileMod, 'downloadFile').mockImplementation(() => undefined)
  })

  afterEach(() => {
    downloadSpy.mockRestore()
  })

  describe('CSV output', () => {
    it('escapes commas, quotes, and newlines per RFC 4180', () => {
      const { exportAs } = useTableExport({
        filename: 'rows',
        rows: sampleRows,
        columns: sampleColumns,
      })
      exportAs('csv')

      expect(downloadSpy).toHaveBeenCalledTimes(1)
      const [payload, filename, mime] = downloadSpy.mock.calls[0] as [string, string, string]
      // Strip BOM for stable comparison
      const csv = payload.replace(/^\uFEFF/, '')
      const lines = csv.split('\n')
      expect(lines[0]).toBe('ID,Name,Count,Active,Notes')
      expect(lines[1]).toBe('1,Alice,10,true,first')
      // Comma in name gets quoted; internal " is doubled
      expect(lines[2]).toBe('2,"Bob, Jr.",5,false,"has ""quote"""')
      // Newline-containing value gets quoted — split('\n') will fragment the
      // quoted cell across two lines, so assert against the raw payload.
      expect(csv).toContain('"Line\nBreak"')
      // null falls back to '-' — payload ends with the trailing cell `,-`
      expect(csv.endsWith(',-')).toBe(true)

      expect(filename).toMatch(/^rows-\d{4}-\d{2}-\d{2}\.csv$/)
      expect(mime).toContain('text/csv')
    })

    it('prefixes payload with UTF-8 BOM for Excel KO compatibility', () => {
      const { exportAs } = useTableExport({
        filename: 'rows',
        rows: sampleRows,
        columns: sampleColumns,
      })
      exportAs('csv')
      const [payload] = downloadSpy.mock.calls[0] as [string]
      expect(payload.charCodeAt(0)).toBe(0xfeff)
    })

    it('uses custom fallbackEmpty when provided', () => {
      const { exportAs } = useTableExport({
        filename: 'rows',
        rows: [{ id: '1', name: 'x', count: 0, active: false, notes: null }],
        columns: sampleColumns,
        fallbackEmpty: 'N/A',
      })
      exportAs('csv')
      const [payload] = downloadSpy.mock.calls[0] as [string]
      expect(payload).toContain(',N/A')
    })

    it('emits header-only output is never produced — empty rows disable export', () => {
      const { exportAs, isReady } = useTableExport({
        filename: 'rows',
        rows: [],
        columns: sampleColumns,
      })
      expect(isReady).toBe(false)
      exportAs('csv')
      expect(downloadSpy).not.toHaveBeenCalled()
    })
  })

  describe('JSON output', () => {
    it('produces a pretty-printed array of objects keyed by column.key', () => {
      const { exportAs } = useTableExport({
        filename: 'rows',
        rows: sampleRows.slice(0, 2),
        columns: sampleColumns,
      })
      exportAs('json')

      const [payload, filename, mime] = downloadSpy.mock.calls[0] as [string, string, string]
      // 2-space indent — should contain "\n  " between fields
      expect(payload).toMatch(/^\[\n {2}\{/)
      const parsed = JSON.parse(payload) as Array<Record<string, unknown>>
      expect(parsed).toHaveLength(2)
      expect(parsed[0]).toEqual({
        id: '1',
        name: 'Alice',
        count: 10,
        active: true,
        notes: 'first',
      })
      expect(parsed[1].notes).toBe('has "quote"')

      expect(filename).toMatch(/^rows-\d{4}-\d{2}-\d{2}\.json$/)
      expect(mime).toBe('application/json')
    })

    it('coerces undefined accessor return to null in JSON', () => {
      const { exportAs } = useTableExport<Row>({
        filename: 'rows',
        rows: [sampleRows[0]],
        columns: [
          { key: 'id', header: 'ID', accessor: r => r.id },
          { key: 'maybe', header: 'Maybe', accessor: () => undefined },
        ],
      })
      exportAs('json')
      const [payload] = downloadSpy.mock.calls[0] as [string]
      const parsed = JSON.parse(payload) as Array<Record<string, unknown>>
      expect(parsed[0].maybe).toBeNull()
    })
  })

  describe('filename pattern', () => {
    it('appends today\'s date in YYYY-MM-DD format', () => {
      const { exportAs } = useTableExport({
        filename: 'audit-log',
        rows: sampleRows,
        columns: sampleColumns,
      })
      exportAs('csv')
      const [, filename] = downloadSpy.mock.calls[0] as [string, string]
      expect(filename).toMatch(/^audit-log-\d{4}-\d{2}-\d{2}\.csv$/)
    })

    it('falls back to "table-export" when filename is empty', () => {
      const { exportAs } = useTableExport({
        filename: '',
        rows: sampleRows,
        columns: sampleColumns,
      })
      exportAs('json')
      const [, filename] = downloadSpy.mock.calls[0] as [string, string]
      expect(filename).toMatch(/^table-export-\d{4}-\d{2}-\d{2}\.json$/)
    })
  })

  describe('readiness flag', () => {
    it('isReady is false for empty rows and true otherwise', () => {
      expect(useTableExport({ filename: 'r', rows: [], columns: sampleColumns }).isReady).toBe(false)
      expect(
        useTableExport({ filename: 'r', rows: sampleRows, columns: sampleColumns }).isReady,
      ).toBe(true)
    })
  })

  describe('column accessor fallback', () => {
    it('reads row[key] as a primitive when accessor is omitted', () => {
      const cols: ExportColumn<Row>[] = [
        { key: 'id', header: 'ID' },
        { key: 'name', header: 'Name' },
      ]
      const { exportAs } = useTableExport({
        filename: 'r',
        rows: [sampleRows[0]],
        columns: cols,
      })
      exportAs('csv')
      const [payload] = downloadSpy.mock.calls[0] as [string]
      expect(payload).toContain('1,Alice')
    })
  })
})

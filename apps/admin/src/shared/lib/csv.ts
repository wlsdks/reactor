export interface CsvColumn<T> {
  key: keyof T & string
  header: string
  format?: (value: unknown) => string
}

function escapeCell(value: unknown): string {
  if (value === null || value === undefined) return ''
  const str = String(value)
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`
  }
  return str
}

export function generateCsv<T extends Record<string, unknown>>(
  columns: CsvColumn<T>[],
  rows: T[],
): string {
  const header = columns.map(c => escapeCell(c.header)).join(',')
  const body = rows.map(row =>
    columns.map(col => {
      const raw = row[col.key]
      const value = col.format ? col.format(raw) : raw
      return escapeCell(value)
    }).join(','),
  )
  return [header, ...body].join('\n')
}

export function downloadCsv(csv: string, filename: string): void {
  const bom = '\uFEFF'
  const blob = new Blob([bom + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

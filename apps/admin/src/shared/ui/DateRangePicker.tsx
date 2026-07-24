import { useTranslation } from 'react-i18next'

export type DatePreset = '24h' | '7d' | '30d' | '90d' | 'custom'

export interface DateRange {
  from: number
  to: number
}

interface DateRangePickerProps {
  value: DateRange
  onChange: (range: DateRange) => void
  presets?: DatePreset[]
}

const PRESET_MS: Record<Exclude<DatePreset, 'custom'>, number> = {
  '24h': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
  '30d': 30 * 24 * 60 * 60 * 1000,
  '90d': 90 * 24 * 60 * 60 * 1000,
}

function matchPreset(duration: number): DatePreset | null {
  for (const [key, ms] of Object.entries(PRESET_MS)) {
    if (Math.abs(duration - ms) < 1_000) {
      return key as DatePreset
    }
  }
  return null
}

function toDateInputValue(ms: number): string {
  const d = new Date(ms)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function createPresetRange(preset: Exclude<DatePreset, 'custom'>): DateRange {
  const now = Date.now()
  return { from: now - PRESET_MS[preset], to: now }
}

export function DateRangePicker({
  value,
  onChange,
  presets = ['24h', '7d', '30d', '90d', 'custom'],
}: DateRangePickerProps) {
  const { t } = useTranslation()

  const duration = value.to - value.from
  const activePreset = matchPreset(duration)
  const showCustom = presets.includes('custom')
  const isCustomActive = activePreset === null

  function handlePresetClick(preset: Exclude<DatePreset, 'custom'>) {
    onChange(createPresetRange(preset))
  }

  function handleFromChange(e: React.ChangeEvent<HTMLInputElement>) {
    const date = new Date(e.target.value)
    if (!Number.isNaN(date.getTime())) {
      onChange({ ...value, from: date.getTime() })
    }
  }

  function handleToChange(e: React.ChangeEvent<HTMLInputElement>) {
    const date = new Date(e.target.value)
    if (!Number.isNaN(date.getTime())) {
      onChange({ ...value, to: date.getTime() })
    }
  }

  const presetLabels: Record<Exclude<DatePreset, 'custom'>, string> = {
    '24h': t('dateRange.24h', '24h'),
    '7d': t('dateRange.7d', '7d'),
    '30d': t('dateRange.30d', '30d'),
    '90d': t('dateRange.90d', '90d'),
  }

  return (
    <div className="date-range-picker" role="group" aria-label={t('dateRange.label')}>
      <div className="date-range-presets">
        {presets
          .filter((p): p is Exclude<DatePreset, 'custom'> => p !== 'custom')
          .map((preset) => (
            <button
              key={preset}
              type="button"
              className={`btn btn-sm btn-secondary ${activePreset === preset ? 'active-filter' : ''}`}
              onClick={() => handlePresetClick(preset)}
            >
              {presetLabels[preset]}
            </button>
          ))}
      </div>
      {showCustom && isCustomActive && (
        <div className="date-range-custom">
          <input
            type="date"
            className="date-range-input"
            value={toDateInputValue(value.from)}
            onChange={handleFromChange}
            aria-label={t('dateRange.from')}
          />
          <span className="date-range-separator">-</span>
          <input
            type="date"
            className="date-range-input"
            value={toDateInputValue(value.to)}
            onChange={handleToChange}
            aria-label={t('dateRange.to')}
          />
        </div>
      )}
    </div>
  )
}

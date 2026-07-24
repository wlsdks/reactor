import { useRef, useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Search, X } from 'lucide-react'

interface SessionSearchBarProps {
  value: string
  onChange: (query: string) => void
  placeholder?: string
}

export function SessionSearchBar({ value, onChange, placeholder }: SessionSearchBarProps) {
  const { t } = useTranslation()
  const [localValue, setLocalValue] = useState(value)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sync external value changes
  useEffect(() => {
    setLocalValue(value)
  }, [value])

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const newValue = e.target.value
    setLocalValue(newValue)

    if (timerRef.current) {
      clearTimeout(timerRef.current)
    }

    timerRef.current = setTimeout(() => {
      onChange(newValue)
    }, 300)
  }

  function handleClear() {
    setLocalValue('')
    onChange('')

    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
    }
  }, [])

  return (
    <div className="session-search-bar">
      <Search className="session-search-bar__icon" size={16} aria-hidden="true" />
      <input
        type="text"
        value={localValue}
        onChange={handleChange}
        placeholder={placeholder ?? t('conversations.feed.search')}
      />
      {localValue && (
        <button
          type="button"
          className="session-search-bar__clear"
          onClick={handleClear}
          aria-label={t('common.aria.clearSearch')}
        >
          <X size={16} aria-hidden="true" />
        </button>
      )}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { formatLocaleTime } from './intl'

const CLOCK_UPDATE_INTERVAL_MS = 1000

function formatTime(date: Date): string {
  return formatLocaleTime(date)
}

function formatDate(date: Date): string {
  // Intentionally en-CA so the date strip stays ISO-like (YYYY-MM-DD).
  return date.toLocaleDateString('en-CA')
}

export function useClockDisplay() {
  const [time, setTime] = useState(() => formatTime(new Date()))
  const [date, setDate] = useState(() => formatDate(new Date()))

  useEffect(() => {
    const id = setInterval(() => {
      const now = new Date()
      setTime(formatTime(now))
      setDate(formatDate(now))
    }, CLOCK_UPDATE_INTERVAL_MS)
    return () => clearInterval(id)
  }, [])

  return { time, date }
}

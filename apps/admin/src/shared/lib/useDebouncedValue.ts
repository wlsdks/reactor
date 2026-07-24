import { useEffect, useState } from 'react'

/**
 * useDebouncedValue
 *
 * Returns a debounced copy of `value` that only updates after `delay`ms of
 * stable input. Used for real-time form validation feedback so the UI does
 * not flicker on every keystroke.
 *
 * @param value Source value to debounce.
 * @param delay Debounce window in milliseconds. Defaults to 250ms.
 */
export function useDebouncedValue<T>(value: T, delay: number = 250): T {
  const [debounced, setDebounced] = useState<T>(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}

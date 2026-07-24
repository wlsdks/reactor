import { useEffect } from 'react'

export function useBodyOverflowLock(active: boolean) {
  useEffect(() => {
    if (!active) return
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [active])
}

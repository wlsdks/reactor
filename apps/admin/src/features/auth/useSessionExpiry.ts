import { useEffect } from 'react'
import { useToastStore } from '../../shared/store/toast.store'
import type { User } from './types'
import { getAuthToken } from '../../shared/api/client'
import { getTokenExpiry } from '../../shared/lib/jwt'
import i18n from '../../shared/i18n/config'

const MAX_TIMEOUT_DELAY_MS = 2_147_483_647

export function useSessionExpiry(user: User | null) {
  useEffect(() => {
    if (!user) return

    const token = getAuthToken()
    if (!token) return

    const exp = getTokenExpiry(token)
    if (!exp) return

    const nowSec = Math.floor(Date.now() / 1000)
    const remainingSec = exp - nowSec
    if (remainingSec <= 0) return

    const timers: ReturnType<typeof setTimeout>[] = []
    let cancelled = false

    const scheduleWarning = (delayMs: number, getMessage: () => string) => {
      if (delayMs <= 0) return

      const timer = setTimeout(() => {
        if (cancelled) return
        if (delayMs > MAX_TIMEOUT_DELAY_MS) {
          scheduleWarning(delayMs - MAX_TIMEOUT_DELAY_MS, getMessage)
          return
        }
        useToastStore.getState().addToast({ type: 'warning', message: getMessage() })
      }, Math.min(delayMs, MAX_TIMEOUT_DELAY_MS))

      timers.push(timer)
    }

    // 5-minute warning
    const fiveMinMs = (remainingSec - 300) * 1000
    scheduleWarning(fiveMinMs, () => i18n.t('common.toast.sessionExpiring5'))

    // 1-minute warning
    const oneMinMs = (remainingSec - 60) * 1000
    scheduleWarning(oneMinMs, () => i18n.t('common.toast.sessionExpiring1'))

    return () => {
      cancelled = true
      timers.forEach(clearTimeout)
    }
  }, [user])
}

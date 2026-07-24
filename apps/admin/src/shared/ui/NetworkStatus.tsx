import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'

export function NetworkStatus() {
  const [isOnline, setIsOnline] = useState(navigator.onLine)
  const { t } = useTranslation()

  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  if (isOnline) return null

  return (
    <div className="network-banner" role="alert">
      {t('error.offline')}
    </div>
  )
}

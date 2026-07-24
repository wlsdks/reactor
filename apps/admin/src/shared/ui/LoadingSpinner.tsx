import { useTranslation } from 'react-i18next'

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
}

export function LoadingSpinner({ size = 'md' }: LoadingSpinnerProps) {
  const { t } = useTranslation()
  const sizeMap = { sm: 14, md: 22, lg: 36 }
  const px = sizeMap[size]
  return (
    <svg
      className="spinner"
      width={px}
      height={px}
      viewBox="0 0 24 24"
      fill="none"
      aria-label={t('common.aria.loading')}
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2.5" strokeDasharray="30 60" />
    </svg>
  )
}

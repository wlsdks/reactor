import { useTranslation } from 'react-i18next'

interface RefreshButtonProps {
  onRefresh: () => void
  isFetching?: boolean
}

export function RefreshButton({ onRefresh, isFetching }: RefreshButtonProps) {
  const { t } = useTranslation()

  function handleClick() {
    onRefresh()
  }

  return (
    <button
      className="btn btn-secondary btn-sm"
      onClick={handleClick}
      disabled={isFetching}
    >
      {isFetching ? '...' : t('common.refresh')}
    </button>
  )
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { OperationButton } from '../../../shared/ui/OperationButton'
import { useAnnouncer } from '../../../shared/ui/LiveAnnouncer'
import { useToastStore } from '../../../shared/store/toast.store'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getFaqChannel, ingestFaqChannel } from '../api'

interface Props {
  channelId: string
}

function formatTimestamp(ts: number): string {
  if (!Number.isFinite(ts) || ts <= 0) return '—'
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(ts))
}

export function FaqReindex({ channelId }: Props) {
  const { t } = useTranslation()
  const { announce } = useAnnouncer()
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)

  const channelQuery = useQuery({
    queryKey: queryKeys.slackFaq.channel(channelId),
    queryFn: () => getFaqChannel(channelId),
  })

  const mutation = useMutation({
    mutationFn: () => ingestFaqChannel(channelId),
    onSuccess: () => {
      addToast({ type: 'success', message: t('slackFaq.reindex.success') })
      announce(t('slackFaq.reindex.success'))
      queryClient.invalidateQueries({ queryKey: queryKeys.slackFaq.channel(channelId) })
    },
    onError: (error: unknown) => {
      addToast({ type: 'error', message: getErrorMessage(error) })
    },
  })

  const lastIngestedAt = channelQuery.data?.lastIngestedAt

  return (
    <div className="faq-reindex" data-testid="faq-reindex">
      <h3>{t('slackFaq.reindex.title')}</h3>
      <p className="faq-reindex__hint">
        {lastIngestedAt
          ? t('slackFaq.reindex.lastIngested', { time: formatTimestamp(lastIngestedAt) })
          : t('slackFaq.reindex.neverIngested')}
      </p>
      <OperationButton
        type="button"
        variant="secondary"
        isOperating={mutation.isPending}
        onClick={() => mutation.mutate()}
        data-testid="faq-reindex-btn"
      >
        {t('slackFaq.reindex.submit')}
      </OperationButton>
    </div>
  )
}

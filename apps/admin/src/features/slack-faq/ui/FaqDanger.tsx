import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { ConfirmDialog } from '../../../shared/ui/ConfirmDialog'
import { OperationButton } from '../../../shared/ui/OperationButton'
import { useToastStore } from '../../../shared/store/toast.store'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { deleteFaqChannel } from '../api'

interface Props {
  channelId: string
  onChannelDeleted: () => void
}

export function FaqDanger({ channelId, onChannelDeleted }: Props) {
  const { t } = useTranslation()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)

  const mutation = useMutation({
    mutationFn: () => deleteFaqChannel(channelId),
    onSuccess: () => {
      addToast({ type: 'success', message: t('slackFaq.danger.deleted') })
      queryClient.invalidateQueries({ queryKey: queryKeys.slackFaq.channelsRoot() })
      setConfirmOpen(false)
      onChannelDeleted()
    },
    onError: (error: unknown) => {
      addToast({ type: 'error', message: getErrorMessage(error) })
    },
  })

  return (
    <div className="faq-danger" data-testid="faq-danger">
      <h3>{t('slackFaq.danger.title')}</h3>
      <p className="faq-danger__warning">{t('slackFaq.danger.warning')}</p>
      <OperationButton
        type="button"
        variant="danger"
        isOperating={mutation.isPending}
        onClick={() => setConfirmOpen(true)}
        data-testid="faq-danger-delete-btn"
      >
        {t('slackFaq.danger.delete')}
      </OperationButton>

      {confirmOpen && (
        <ConfirmDialog
          title={t('slackFaq.danger.confirmTitle')}
          message={t('slackFaq.danger.confirmMessage', { channelId })}
          danger
          confirmText={channelId}
          confirmTextLabel={t('slackFaq.danger.typeToConfirmLabel', { channelId })}
          onConfirm={() => mutation.mutate()}
          onCancel={() => setConfirmOpen(false)}
        />
      )}
    </div>
  )
}

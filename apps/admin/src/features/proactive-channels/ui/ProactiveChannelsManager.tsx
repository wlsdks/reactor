import { useMemo, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import {
  ConfirmDialog,
  DataTable,
  EmptyState,
  OperationButton,
  RefreshButton,
  SideDrawer,
  SkeletonTable,
  WorkspaceUnavailable,
} from '../../../shared/ui'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { useToastStore } from '../../../shared/store/toast.store'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { formatDateTimeCompact } from '../../../shared/lib/formatters'
import * as channelApi from '../api'
import type { ProactiveChannel } from '../types'
import './proactive-channels.css'

const CHANNEL_ID_PATTERN = /^C[A-Z0-9]{8,}$/

export function ProactiveChannelsManager() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [channelId, setChannelId] = useState('')
  const [channelName, setChannelName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<ProactiveChannel | null>(null)

  const selectedChannelId = searchParams.get('channel')
  const addDrawerOpen = searchParams.get('channelAction') === 'add'

  const { data: channels = [], isLoading, error, isFetching } = useQuery({
    queryKey: queryKeys.proactiveChannels.list(),
    queryFn: channelApi.listProactiveChannels,
    retry: false,
  })

  const selected = channels.find(channel => channel.channelId === selectedChannelId) ?? null
  const normalizedChannelId = channelId.trim().toUpperCase()
  const channelIdValid = CHANNEL_ID_PATTERN.test(normalizedChannelId)

  function updateWorkspaceParams(updates: Record<string, string | null>) {
    setSearchParams(current => {
      const next = new URLSearchParams(current)
      Object.entries(updates).forEach(([key, value]) => {
        if (value === null) next.delete(key)
        else next.set(key, value)
      })
      return next
    })
  }

  function openAddDrawer() {
    updateWorkspaceParams({ channel: null, channelAction: 'add' })
  }

  function closeAddDrawer() {
    updateWorkspaceParams({ channelAction: null })
  }

  function closeDetailDrawer() {
    updateWorkspaceParams({ channel: null })
  }

  const addMutation = useMutation({
    mutationFn: channelApi.addProactiveChannel,
    onSuccess: created => {
      queryClient.invalidateQueries({ queryKey: queryKeys.proactiveChannels.all() })
      useToastStore.getState().addToast({
        type: 'success',
        message: t('proactiveChannels.addSuccess', { id: created.channelId }),
      })
      setChannelId('')
      setChannelName('')
      updateWorkspaceParams({ channelAction: null, channel: created.channelId })
    },
    onError: err => {
      const message = getErrorMessage(err)
      useToastStore.getState().addToast({
        type: 'error',
        message: message === 'CONFLICT'
          ? t('proactiveChannels.alreadyExists')
          : t('proactiveChannels.addError'),
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => channelApi.removeProactiveChannel(id),
    onSuccess: (_data, deletedId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.proactiveChannels.all() })
      useToastStore.getState().addToast({
        type: 'success',
        message: t('proactiveChannels.removeSuccess', { id: deletedId }),
      })
      closeDetailDrawer()
      setDeleteTarget(null)
    },
    onError: () => {
      useToastStore.getState().addToast({ type: 'error', message: t('proactiveChannels.removeError') })
      setDeleteTarget(null)
    },
  })

  function handleAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!channelIdValid) return
    addMutation.mutate({
      channelId: normalizedChannelId,
      channelName: channelName.trim() || undefined,
    })
  }

  const columns = useMemo(() => [
    {
      key: 'channelName',
      header: t('proactiveChannels.destination'),
      width: '46%',
      responsivePriority: 1,
      render: (channel: ProactiveChannel) => (
        <div className="channel-identity">
          <span className="channel-identity__name">
            {channel.channelName || t('proactiveChannels.unnamedChannel')}
          </span>
          <span className="channel-identity__hint">{t('proactiveChannels.slackChannel')}</span>
        </div>
      ),
    },
    {
      key: 'channelId',
      header: t('proactiveChannels.channelId'),
      width: '28%',
      responsivePriority: 1,
      render: (channel: ProactiveChannel) => <span className="channel-id">{channel.channelId}</span>,
    },
    {
      key: 'addedAt',
      header: t('proactiveChannels.addedAt'),
      width: '26%',
      responsivePriority: 1,
      render: (channel: ProactiveChannel) => formatDateTimeCompact(channel.addedAt),
    },
  ], [t])

  return (
    <div className="page proactive-channels-page">
      <div className="channel-page-header">
        <div>
          <h2>{t('proactiveChannels.title')}</h2>
          <p>{t('proactiveChannels.description')}</p>
        </div>
        <div className="channel-page-header__actions">
          <>
            {channels.length > 0 && (
              <button className="btn btn-primary btn-sm" onClick={openAddDrawer}>
                {t('proactiveChannels.addAction')}
              </button>
            )}
            <RefreshButton
              onRefresh={() => queryClient.invalidateQueries({ queryKey: queryKeys.proactiveChannels.all() })}
              isFetching={isFetching}
            />
          </>
        </div>
      </div>

      {error ? (
        <WorkspaceUnavailable
          title={t('proactiveChannels.loadErrorTitle')}
          description={t('proactiveChannels.loadErrorDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={() => void queryClient.invalidateQueries({ queryKey: queryKeys.proactiveChannels.all() })}
          isRetrying={isFetching}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{
            title: t('proactiveChannels.recoveryGuideTitle'),
            steps: [t('proactiveChannels.recoveryCheckConnection'), t('proactiveChannels.recoveryCheckPermission')],
            technicalLabel: t('common.technicalDetails'),
            technicalDetail: getErrorMessage(error),
          }}
        />
      ) : (
        <section className="channel-workspace" aria-labelledby="proactive-channel-list-title">
          <div className="channel-workspace__summary">
            <div>
              <h2 id="proactive-channel-list-title">{t('proactiveChannels.listTitle')}</h2>
              <p>
                {channels.length > 0
                  ? t('proactiveChannels.summary', { count: channels.length })
                  : t('proactiveChannels.summaryEmpty')}
              </p>
            </div>
          </div>

          {isLoading ? (
            <div className="channel-workspace__loading" aria-label={t('common.loading')}>
              <SkeletonTable rows={4} columns={3} />
            </div>
          ) : channels.length === 0 ? (
            <EmptyState
              message={t('proactiveChannels.empty')}
              description={t('proactiveChannels.emptyDescription')}
              actionLabel={t('proactiveChannels.addAction')}
              onAction={openAddDrawer}
            />
          ) : (
            <DataTable
              tableId="proactive-channels"
              columns={columns}
              data={channels}
              keyFn={channel => channel.channelId}
              onRowClick={channel => updateWorkspaceParams({ channel: channel.channelId, channelAction: null })}
              selectedKey={selected?.channelId ?? null}
            />
          )}
        </section>
      )}

      <SideDrawer open={addDrawerOpen} title={t('proactiveChannels.addTitle')} onClose={closeAddDrawer}>
        <form className="channel-form" onSubmit={handleAdd}>
          <p className="channel-form__intro">{t('proactiveChannels.addDescription')}</p>

          <div className="form-group">
            <label htmlFor="proactive-channel-id">{t('proactiveChannels.channelId')}</label>
            <input
              id="proactive-channel-id"
              value={channelId}
              onChange={event => setChannelId(event.target.value)}
              placeholder={t('proactiveChannels.channelIdPlaceholder')}
              maxLength={50}
              autoComplete="off"
              autoCapitalize="characters"
              aria-invalid={channelId.length > 0 && !channelIdValid}
              aria-describedby="proactive-channel-id-help"
            />
            <p id="proactive-channel-id-help" className="form-help">
              {channelId.length > 0 && !channelIdValid
                ? t('proactiveChannels.channelIdInvalid')
                : t('proactiveChannels.channelIdHelp')}
            </p>
          </div>

          <div className="form-group">
            <label htmlFor="proactive-channel-name">{t('proactiveChannels.channelName')}</label>
            <input
              id="proactive-channel-name"
              value={channelName}
              onChange={event => setChannelName(event.target.value)}
              placeholder={t('proactiveChannels.channelNamePlaceholder')}
              maxLength={200}
              autoComplete="off"
            />
            <p className="form-help">{t('proactiveChannels.channelNameHelp')}</p>
          </div>

          <div className="channel-form__notice">
            <strong>{t('proactiveChannels.deliveryNoticeTitle')}</strong>
            <p>{t('proactiveChannels.deliveryNoticeDescription')}</p>
          </div>

          <div className="drawer-actions">
            <OperationButton type="button" variant="secondary" onClick={closeAddDrawer}>
              {t('common.cancel')}
            </OperationButton>
            <OperationButton type="submit" disabled={!channelIdValid} isOperating={addMutation.isPending}>
              {t('proactiveChannels.add')}
            </OperationButton>
          </div>
        </form>
      </SideDrawer>

      <SideDrawer
        open={Boolean(selected)}
        title={selected?.channelName || t('proactiveChannels.channelDetails')}
        onClose={closeDetailDrawer}
      >
        {selected && (
          <div className="channel-detail">
            <div className="channel-detail__status">
              <span className="status-dot status-dot--success" aria-label={t('proactiveChannels.deliveryEnabled')} title={t('proactiveChannels.deliveryEnabled')} />
              <div>
                <strong>{t('proactiveChannels.deliveryEnabled')}</strong>
                <p>{t('proactiveChannels.deliveryEnabledDescription')}</p>
              </div>
            </div>

            <dl className="channel-detail__facts">
              <div>
                <dt>{t('proactiveChannels.channelName')}</dt>
                <dd>{selected.channelName || t('proactiveChannels.unnamedChannel')}</dd>
              </div>
              <div>
                <dt>{t('proactiveChannels.channelId')}</dt>
                <dd><span className="channel-id">{selected.channelId}</span></dd>
              </div>
              <div>
                <dt>{t('proactiveChannels.addedAt')}</dt>
                <dd>{formatDateTimeCompact(selected.addedAt)}</dd>
              </div>
            </dl>

            <details className="channel-detail__maintenance">
              <summary>{t('proactiveChannels.maintenanceTitle')}</summary>
              <p>{t('proactiveChannels.maintenanceDescription')}</p>
              <button className="btn btn-danger" onClick={() => setDeleteTarget(selected)}>
                {t('proactiveChannels.removeChannel')}
              </button>
            </details>
          </div>
        )}
      </SideDrawer>

      {deleteTarget && (
        <ConfirmDialog
          title={t('proactiveChannels.removeTitle')}
          message={t('proactiveChannels.removeMessage', { id: deleteTarget.channelId })}
          danger
          confirmText={deleteTarget.channelId}
          confirmTextLabel={t('proactiveChannels.removeConfirmLabel')}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => deleteMutation.mutate(deleteTarget.channelId)}
        />
      )}
    </div>
  )
}

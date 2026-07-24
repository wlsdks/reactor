import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import {
  ConfirmDialog,
  DataTable,
  EmptyState,
  RefreshButton,
  SideDrawer,
  SkeletonTable,
} from '../../../shared/ui'
import type { Column } from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { useToastStore } from '../../../shared/store/toast.store'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { formatDateTimeCompact } from '../../../shared/lib/formatters'
import * as slackBotApi from '../api'
import type { SlackBot } from '../types'
import { SlackBotFormModal } from './SlackBotFormModal'
import './slack-bots.css'

export function SlackBotTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const addToast = useToastStore(state => state.addToast)
  const [searchParams, setSearchParams] = useSearchParams()
  const [deletingBot, setDeletingBot] = useState<SlackBot | null>(null)

  const selectedBotId = searchParams.get('bot')
  const botAction = searchParams.get('botAction')

  const { data: bots = [], isLoading, isFetching, error } = useQuery({
    queryKey: queryKeys.slackBots.list(),
    queryFn: slackBotApi.listSlackBots,
    retry: false,
  })

  const selectedBot = bots.find(bot => bot.id === selectedBotId) ?? null
  const editingBot = botAction === 'edit' ? selectedBot : null
  const formOpen = botAction === 'create' || Boolean(editingBot)

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

  function openCreate() {
    updateWorkspaceParams({ bot: null, botAction: 'create' })
  }

  function closeForm() {
    updateWorkspaceParams({ botAction: null })
  }

  function closeDetails() {
    updateWorkspaceParams({ bot: null, botAction: null })
  }

  const deleteMutation = useMutation({
    mutationFn: slackBotApi.deleteSlackBot,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.slackBots.all() })
      addToast({ type: 'success', message: t('slackBotsTab.deleted') })
      setDeletingBot(null)
      closeDetails()
    },
    onError: () => {
      addToast({ type: 'error', message: t('slackBotsTab.deleteError') })
      setDeletingBot(null)
    },
  })

  const columns = useMemo<Column<SlackBot>[]>(() => [
    {
      key: 'name',
      header: t('slackBotsTab.connectionName'),
      width: '36%',
      responsivePriority: 1,
      render: row => (
        <div className="slack-bot-identity">
          <span className="slack-bot-identity__name">{row.name}</span>
          <span>{row.description || t('slackBotsTab.noDescription')}</span>
        </div>
      ),
    },
    {
      key: 'workspace',
      header: t('slackBotsTab.workspace'),
      width: '34%',
      responsivePriority: 1,
      render: row => <span className="slack-bot-workspace">{row.workspace}</span>,
    },
    {
      key: 'status',
      header: t('common.status'),
      width: '30%',
      responsivePriority: 1,
      render: row => (
        <span className={`slack-bot-status${row.isActive ? ' is-active' : ''}`}>
          <span aria-hidden="true" />
          {row.isActive ? t('slackBotsTab.statusActive') : t('slackBotsTab.statusInactive')}
        </span>
      ),
    },
  ], [t])

  return (
    <div className="slack-bots-tab">
      <div className="slack-bots-header">
        <div>
          <h2>{t('slackBotsTab.title')}</h2>
          <p>{t('slackBotsTab.description')}</p>
        </div>
        <div className="slack-bots-header__actions">
          {bots.length > 0 && (
            <button className="btn btn-primary btn-sm" onClick={openCreate}>
              {t('slackBotsTab.addBot')}
            </button>
          )}
          <RefreshButton
            onRefresh={() => queryClient.invalidateQueries({ queryKey: queryKeys.slackBots.all() })}
            isFetching={isFetching}
          />
        </div>
      </div>

      {error ? (
        <section className="slack-bots-unavailable" role="alert">
          <div>
            <h3>{t('slackBotsTab.loadErrorTitle')}</h3>
            <p>{t('slackBotsTab.loadErrorDescription')}</p>
          </div>
          <button
            className="btn btn-secondary"
            onClick={() => queryClient.invalidateQueries({ queryKey: queryKeys.slackBots.all() })}
          >
            {t('common.retry')}
          </button>
          <details>
            <summary>{t('common.technicalDetails')}</summary>
            <code>{getErrorMessage(error)}</code>
          </details>
        </section>
      ) : (
        <section className="slack-bots-workspace" aria-labelledby="slack-bots-list-title">
          <div className="slack-bots-workspace__summary">
            <div>
              <h3 id="slack-bots-list-title">{t('slackBotsTab.listTitle')}</h3>
              <p>
                {bots.length > 0
                  ? t('slackBotsTab.listSummary', { count: bots.length })
                  : t('slackBotsTab.listSummaryEmpty')}
              </p>
            </div>
            {bots.length > 0 && <span aria-label={t('slackBotsTab.count', { count: bots.length })}>{bots.length}</span>}
          </div>

          {isLoading ? (
            <div className="slack-bots-workspace__loading"><SkeletonTable rows={4} columns={3} /></div>
          ) : bots.length === 0 ? (
            <EmptyState
              message={t('slackBotsTab.empty')}
              description={t('slackBotsTab.emptyDescription')}
              actionLabel={t('slackBotsTab.addBot')}
              onAction={openCreate}
            />
          ) : (
            <DataTable
              tableId="slack-bots"
              columns={columns}
              data={bots}
              keyFn={row => row.id}
              selectedKey={selectedBot?.id ?? null}
              onRowClick={bot => updateWorkspaceParams({ bot: bot.id, botAction: null })}
            />
          )}
        </section>
      )}

      <SideDrawer
        open={Boolean(selectedBot) && !formOpen}
        title={selectedBot?.name ?? t('slackBotsTab.detailsTitle')}
        onClose={closeDetails}
      >
        {selectedBot && (
          <div className="slack-bot-detail">
            <div className="slack-bot-detail__status">
              <span className={`slack-bot-status${selectedBot.isActive ? ' is-active' : ''}`}>
                <span aria-hidden="true" />
                {selectedBot.isActive ? t('slackBotsTab.statusActive') : t('slackBotsTab.statusInactive')}
              </span>
              <p>
                {selectedBot.isActive
                  ? t('slackBotsTab.statusActiveDescription')
                  : t('slackBotsTab.statusInactiveDescription')}
              </p>
            </div>

            <dl className="slack-bot-detail__facts">
              <div><dt>{t('slackBotsTab.workspace')}</dt><dd>{selectedBot.workspace}</dd></div>
              <div><dt>{t('common.description')}</dt><dd>{selectedBot.description || t('slackBotsTab.noDescription')}</dd></div>
              <div><dt>{t('slackBotsTab.updatedAt')}</dt><dd>{formatDateTimeCompact(selectedBot.updatedAt)}</dd></div>
            </dl>

            <button
              className="btn btn-primary"
              onClick={() => updateWorkspaceParams({ botAction: 'edit' })}
            >
              {t('slackBotsTab.editSettings')}
            </button>

            <details className="slack-bot-detail__maintenance">
              <summary>{t('slackBotsTab.maintenanceTitle')}</summary>
              <p>{t('slackBotsTab.maintenanceDescription')}</p>
              <button className="btn btn-danger" onClick={() => setDeletingBot(selectedBot)}>
                {t('slackBotsTab.deleteConnection')}
              </button>
            </details>
          </div>
        )}
      </SideDrawer>

      {formOpen && (
        <SlackBotFormModal bot={editingBot} onClose={closeForm} />
      )}

      {deletingBot && (
        <ConfirmDialog
          title={t('slackBotsTab.confirmDelete')}
          message={t('slackBotsTab.confirmDeleteMsg', { name: deletingBot.name })}
          danger
          confirmText={deletingBot.name}
          confirmTextLabel={t('slackBotsTab.confirmDeleteLabel')}
          onConfirm={() => deleteMutation.mutate(deletingBot.id)}
          onCancel={() => setDeletingBot(null)}
        />
      )}
    </div>
  )
}

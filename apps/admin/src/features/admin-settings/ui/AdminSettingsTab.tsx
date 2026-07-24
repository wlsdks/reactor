import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  ConfirmDialog,
  DataTable,
  LoadingSpinner,
  SideDrawer,
  TableSkeleton,
  WorkspaceUnavailable,
} from '../../../shared/ui'
import { useToastStore } from '../../../shared/store/toast.store'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { showApiErrorToast } from '../../../shared/lib/showApiErrorToast'
import { formatISODate } from '../../../shared/lib/formatters'
import { listSettings, updateSetting, deleteSetting, refreshSettingsCache, reloadSlackPrompts } from '../api'
import type { AdminSetting } from '../types'
import { getOperatorSettingName } from '../settingDisplay'
import { SettingEditModal } from './SettingEditModal'
import './AdminSettingsTab.css'

export function AdminSettingsTab() {
  const { t } = useTranslation()
  const settingLabels = {
    cacheEnabled: t('adminSettingsTab.settingLabels.cacheEnabled'),
    unknown: t('adminSettingsTab.unknownSetting'),
  }
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [selectedSetting, setSelectedSetting] = useState<AdminSetting | null>(null)
  const [editingSetting, setEditingSetting] = useState<AdminSetting | null>(null)
  const [deletingKey, setDeletingKey] = useState<string | null>(null)

  const { data: settings = [], isLoading, isFetching, error, refetch } = useQuery({
    queryKey: queryKeys.adminSettings.list(),
    queryFn: listSettings,
  })

  const updateMutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => updateSetting(key, value),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminSettings.all() })
      useToastStore.getState().addToast({ type: 'success', message: t('adminSettingsTab.updated') })
      setEditingSetting(null)
    },
    onError: (err: Error) => { showApiErrorToast(err) },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteSetting,
    onSuccess: (_data, deletedKey) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminSettings.all() })
      useToastStore.getState().addToast({ type: 'success', message: t('adminSettingsTab.deleted') })
      setDeletingKey(null)
      if (selectedSetting?.key === deletedKey) setSelectedSetting(null)
    },
    onError: (err: Error) => { showApiErrorToast(err) },
  })

  const refreshMutation = useMutation({
    mutationFn: refreshSettingsCache,
    onSuccess: () => {
      // Cache refresh on the BE may surface new defaults / reloaded values, so
      // invalidate the list to pick them up rather than showing the previous
      // snapshot until the next manual page navigation.
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminSettings.all() })
      useToastStore.getState().addToast({ type: 'success', message: t('adminSettingsTab.cacheRefreshed') })
    },
    onError: (err: Error) => { showApiErrorToast(err) },
  })

  const reloadSlackPromptsMutation = useMutation({
    mutationFn: reloadSlackPrompts,
    onSuccess: (data) => {
      // Slack prompt reload can mutate prompt-backed settings; refresh the list
      // so the table reflects post-reload values without a manual reload.
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminSettings.all() })
      useToastStore.getState().addToast({
        type: 'success',
        message: t('adminSettingsTab.slackPromptsReloaded', { count: data.sectionCount }),
      })
    },
    onError: (err: Error) => { showApiErrorToast(err) },
  })

  const filtered = search
    ? settings.filter(s => `${s.key} ${s.description ?? ''} ${s.category}`.toLowerCase().includes(search.toLowerCase()))
    : settings

  const displayValue = (setting: AdminSetting): string => {
    const type = setting.type.toLowerCase()
    if (type === 'secret') return t('adminSettingsTab.maskedValue')
    if (type === 'boolean') {
      return setting.value.toLowerCase() === 'true'
        ? t('adminSettingsTab.booleanEnabled')
        : t('adminSettingsTab.booleanDisabled')
    }
    if (type === 'json') return t('adminSettingsTab.structuredValue')
    return setting.value
  }

  const columns = [
    {
      key: 'setting',
      header: t('adminSettingsTab.setting'),
      width: '46%',
      render: (row: AdminSetting) => {
        return (
          <div className="admin-setting-identity">
            <strong>{getOperatorSettingName(row, settingLabels)}</strong>
          </div>
        )
      },
    },
    {
      key: 'value',
      header: t('adminSettingsTab.value'),
      width: '30%',
      render: (row: AdminSetting) => (
        <span className="admin-setting-value">
          {displayValue(row)}
        </span>
      ),
    },
    {
      key: 'updatedAt',
      header: t('common.updatedAt'),
      width: '24%',
      responsivePriority: 3,
      render: (row: AdminSetting) => formatISODate(row.updatedAt),
    },
  ]

  return (
    <div className="admin-settings-tab">
      {!isLoading && !error ? <div className="admin-settings-tab__toolbar">
        <p>{t('adminSettingsTab.description')}</p>
        <details className="admin-settings-maintenance">
          <summary>{t('adminSettingsTab.maintenance')}</summary>
          <div className="admin-settings-maintenance__actions">
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => refreshMutation.mutate()}
              disabled={refreshMutation.isPending}
              title={t('settingsPage.help.refreshCache')}
            >
              {refreshMutation.isPending ? <LoadingSpinner size="sm" /> : t('adminSettingsTab.refreshCache')}
            </button>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => reloadSlackPromptsMutation.mutate()}
              disabled={reloadSlackPromptsMutation.isPending}
              title={t('adminSettingsTab.reloadSlackPromptsTitle')}
              aria-label={t('adminSettingsTab.reloadSlackPromptsTitle')}
            >
              {reloadSlackPromptsMutation.isPending ? <LoadingSpinner size="sm" /> : t('adminSettingsTab.reloadSlackPrompts')}
            </button>
          </div>
        </details>
      </div> : null}

      {error ? (
        <WorkspaceUnavailable
          title={t('adminSettingsTab.unavailableTitle')}
          description={t('adminSettingsTab.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={refetch}
          isRetrying={isFetching}
          secondaryAction={{ label: t('adminSettingsTab.openHealth'), to: '/health' }}
          guide={{
            title: t('adminSettingsTab.recoveryGuideTitle'),
            steps: [
              t('adminSettingsTab.recoveryCheckAccount'),
              t('adminSettingsTab.recoveryCheckStatus'),
              t('adminSettingsTab.recoveryRetry'),
            ],
            technicalLabel: t('adminSettingsTab.technicalError'),
            technicalDetail: getErrorMessage(error),
          }}
        />
      ) : (
        <>
          <div className="form-group" style={{ marginBottom: 'var(--space-4)' }}>
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={t('adminSettingsTab.searchPlaceholder')}
              aria-label={t('adminSettingsTab.searchLabel')}
            />
          </div>

          {isLoading ? (
            <TableSkeleton />
          ) : filtered.length === 0 ? (
            <section className="admin-settings-empty">
              <h3>{search ? t('adminSettingsTab.emptySearch') : t('adminSettingsTab.empty')}</h3>
              <p>{search ? t('adminSettingsTab.emptySearchDescription') : t('adminSettingsTab.emptyDescription')}</p>
              {search ? (
                <button className="btn btn-secondary btn-sm" type="button" onClick={() => setSearch('')}>
                  {t('adminSettingsTab.clearSearch')}
                </button>
              ) : null}
            </section>
          ) : (
            <DataTable
              columns={columns}
              data={filtered}
              keyFn={row => row.key}
              onRowClick={setSelectedSetting}
              selectedKey={selectedSetting?.key ?? null}
              tableId="runtime-settings"
              urlStateKey="runtime-settings"
            />
          )}

          <SideDrawer
            open={!!selectedSetting}
            title={selectedSetting ? getOperatorSettingName(selectedSetting, settingLabels) : ''}
            onClose={() => setSelectedSetting(null)}
          >
            {selectedSetting ? (
              <div className="admin-setting-drawer">
                <p className="admin-setting-drawer__description">
                  {t('adminSettingsTab.detailDescription')}
                </p>
                <dl className="admin-setting-drawer__facts">
                  <dt>{t('adminSettingsTab.value')}</dt>
                  <dd>{displayValue(selectedSetting)}</dd>
                  <dt>{t('common.updatedAt')}</dt>
                  <dd>{formatISODate(selectedSetting.updatedAt)}</dd>
                </dl>
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={() => setEditingSetting(selectedSetting)}
                >
                  {t('common.edit')}
                </button>
                <details className="admin-setting-drawer__maintenance">
                  <summary>{t('adminSettingsTab.maintenance')}</summary>
                  <p>{t('adminSettingsTab.deleteDescription')}</p>
                  <button
                    className="btn btn-danger btn-sm"
                    type="button"
                    onClick={() => setDeletingKey(selectedSetting.key)}
                  >
                    {t('common.delete')}
                  </button>
                </details>
                <details className="admin-setting-drawer__technical">
                  <summary>{t('adminSettingsTab.developerDetails')}</summary>
                  <code>{selectedSetting.key}</code>
                </details>
              </div>
            ) : null}
          </SideDrawer>

          {editingSetting && (
            <SettingEditModal
              setting={editingSetting}
              isPending={updateMutation.isPending}
              onSave={value => updateMutation.mutate({ key: editingSetting.key, value })}
              onClose={() => setEditingSetting(null)}
            />
          )}

          {deletingKey && (
            <ConfirmDialog
              title={t('adminSettingsTab.confirmDelete')}
              message={t('adminSettingsTab.confirmDeleteMsg', { key: deletingKey })}
              onConfirm={() => deleteMutation.mutate(deletingKey)}
              onCancel={() => setDeletingKey(null)}
              danger
              confirmText={deletingKey}
              confirmTextLabel={t('adminSettingsTab.typeKeyToConfirm')}
            />
          )}
        </>
      )}
    </div>
  )
}

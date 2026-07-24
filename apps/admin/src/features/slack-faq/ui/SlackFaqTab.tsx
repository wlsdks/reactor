import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { SideDrawer } from '../../../shared/ui/SideDrawer'
import { SectionErrorBoundary } from '../../../shared/ui/SectionErrorBoundary'
import { SkeletonText } from '../../../shared/ui/Skeleton'
import { useToastStore } from '../../../shared/store/toast.store'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { useUrlState } from '../../../shared/lib/useUrlState'

import {
  createFaqChannel,
  getFaqChannel,
  getFaqOrgStats,
  updateFaqChannel,
} from '../api'
import type {
  CreateFaqChannelFormValues,
  UpdateFaqChannelFormValues,
} from '../schema'

import { FaqChannelDetailPane } from './FaqChannelDetailPane'
import { FaqChannelForm } from './FaqChannelForm'
import { FaqChannelList } from './FaqChannelList'
import { FaqSchedulerHealthBar } from './FaqSchedulerHealthBar'
import './slack-faq.css'

type FaqWorkspaceView = 'overview' | 'test' | 'activity' | 'manage'

export function SlackFaqTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)

  const [urlState, setUrlState] = useUrlState({
    faqChannel: undefined as string | undefined,
    faqView: undefined as FaqWorkspaceView | undefined,
  })
  const selectedChannelId = urlState.faqChannel ?? null
  const workspaceView = urlState.faqView ?? 'overview'

  const [createOpen, setCreateOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [editError, setEditError] = useState<string | null>(null)

  const orgStatsQuery = useQuery({
    queryKey: queryKeys.slackFaq.orgStats(),
    queryFn: getFaqOrgStats,
  })

  // Edit modal needs the latest channel snapshot for default values.
  const editChannelQuery = useQuery({
    queryKey: queryKeys.slackFaq.channel(selectedChannelId ?? '__none__'),
    queryFn: () => getFaqChannel(selectedChannelId as string),
    enabled: !!selectedChannelId && editOpen,
  })

  const createMutation = useMutation({
    mutationFn: (values: CreateFaqChannelFormValues) => createFaqChannel(values),
    onSuccess: (channel) => {
      addToast({ type: 'success', message: t('slackFaq.tab.created') })
      queryClient.invalidateQueries({ queryKey: queryKeys.slackFaq.channelsRoot() })
      queryClient.invalidateQueries({ queryKey: queryKeys.slackFaq.orgStats() })
      setCreateOpen(false)
      setCreateError(null)
      setUrlState({ faqChannel: channel.channelId, faqView: 'overview' })
    },
    onError: (error: unknown) => {
      setCreateError(getErrorMessage(error))
    },
  })

  const updateMutation = useMutation({
    mutationFn: (values: UpdateFaqChannelFormValues) =>
      updateFaqChannel(selectedChannelId as string, values),
    onSuccess: () => {
      addToast({ type: 'success', message: t('slackFaq.tab.updated') })
      queryClient.invalidateQueries({ queryKey: queryKeys.slackFaq.channelsRoot() })
      queryClient.invalidateQueries({
        queryKey: queryKeys.slackFaq.channel(selectedChannelId as string),
      })
      setEditOpen(false)
      setEditError(null)
    },
    onError: (error: unknown) => {
      setEditError(getErrorMessage(error))
    },
  })

  const handleSelect = (id: string | null) => {
    setUrlState({ faqChannel: id ?? undefined, faqView: id ? 'overview' : undefined })
  }

  const handleChannelDeleted = () => {
    setUrlState({ faqChannel: undefined, faqView: undefined })
    queryClient.invalidateQueries({ queryKey: queryKeys.slackFaq.orgStats() })
  }

  return (
    <SectionErrorBoundary name="slack-faq-tab">
      <div className="slack-faq-tab" data-testid="slack-faq-tab">
        <FaqSchedulerHealthBar />
        <header className="slack-faq-tab__header">
          <div>
            <h2>{t('slackFaq.tab.title')}</h2>
            <p>{t('slackFaq.tab.description')}</p>
          </div>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => {
              setCreateError(null)
              setCreateOpen(true)
            }}
            data-testid="faq-add-channel-btn"
          >
            {t('slackFaq.list.addChannel')}
          </button>
        </header>
        <div className="slack-faq-tab__summary" aria-label={t('slackFaq.tab.summaryAria')}>
          <span><strong>{orgStatsQuery.data?.totalChannels ?? 0}</strong>{t('slackFaq.tab.statTotalChannels')}</span>
          <span><strong>{orgStatsQuery.data?.totalQueries7d ?? 0}</strong>{t('slackFaq.tab.statTotalQueries7d')}</span>
          <span><strong>{Math.round((orgStatsQuery.data?.avgHitRate7d ?? 0) * 100)}%</strong>{t('slackFaq.tab.statAvgHitRate7d')}</span>
        </div>
        <div className="slack-faq-tab__layout">
          <FaqChannelList
            selectedId={selectedChannelId}
            onSelect={handleSelect}
          />
          <div className="slack-faq-tab__main">
            {selectedChannelId ? (
              <FaqChannelDetailPane
                channelId={selectedChannelId}
                view={workspaceView}
                onViewChange={(view) => setUrlState({ faqView: view })}
                onChannelDeleted={handleChannelDeleted}
                onRequestEdit={() => {
                  setEditError(null)
                  setEditOpen(true)
                }}
              />
            ) : (
              <FaqOrgOverview
                isLoading={orgStatsQuery.isLoading}
              />
            )}
          </div>
        </div>

        <SideDrawer
          open={createOpen}
          title={t('slackFaq.tab.createModalTitle')}
          onClose={() => setCreateOpen(false)}
          size="wide"
        >
          <FaqChannelForm
            mode="create"
            onSubmit={async (values) => {
              await createMutation.mutateAsync(values)
            }}
            onCancel={() => setCreateOpen(false)}
            isPending={createMutation.isPending}
            rootError={createError}
          />
        </SideDrawer>

        {selectedChannelId && editOpen && editChannelQuery.data && (
          <SideDrawer
            open={editOpen}
            title={t('slackFaq.tab.editModalTitle')}
            onClose={() => setEditOpen(false)}
            size="wide"
          >
            <FaqChannelForm
              mode="edit"
              initialValues={editChannelQuery.data}
              onSubmit={async (values) => {
                await updateMutation.mutateAsync(values)
              }}
              onCancel={() => setEditOpen(false)}
              isPending={updateMutation.isPending}
              rootError={editError}
            />
          </SideDrawer>
        )}
      </div>
    </SectionErrorBoundary>
  )
}

interface OrgOverviewProps {
  isLoading: boolean
}

function FaqOrgOverview({ isLoading }: OrgOverviewProps) {
  const { t } = useTranslation()
  if (isLoading) {
    return (
      <div className="slack-faq-tab__org-overview">
        <SkeletonText lines={4} />
      </div>
    )
  }
  return (
    <div
      className="slack-faq-tab__org-overview"
      data-testid="slack-faq-org-overview"
    >
      <span className="slack-faq-tab__org-eyebrow">{t('slackFaq.tab.orgEyebrow')}</span>
      <h3>{t('slackFaq.tab.orgTitle')}</h3>
      <p className="slack-faq-tab__org-hint">{t('slackFaq.tab.selectHint')}</p>
    </div>
  )
}

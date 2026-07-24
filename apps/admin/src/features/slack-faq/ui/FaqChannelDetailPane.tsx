import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { queryKeys } from '../../../shared/lib/queryKeys'
import { SectionErrorBoundary } from '../../../shared/ui/SectionErrorBoundary'
import { getFaqChannel } from '../api'

import { FaqDanger } from './FaqDanger'
import { FaqDryRun } from './FaqDryRun'
import { FaqEvents } from './FaqEvents'
import { FaqFeedback } from './FaqFeedback'
import { FaqOverview } from './FaqOverview'
import { FaqProbe } from './FaqProbe'
import { FaqReindex } from './FaqReindex'

export type FaqWorkspaceView = 'overview' | 'test' | 'activity' | 'manage'

interface Props {
  channelId: string
  view: FaqWorkspaceView
  onViewChange: (view: FaqWorkspaceView) => void
  onChannelDeleted: () => void
  onRequestEdit: () => void
}

const VIEWS: FaqWorkspaceView[] = ['overview', 'test', 'activity', 'manage']

export function FaqChannelDetailPane({
  channelId,
  view,
  onViewChange,
  onChannelDeleted,
  onRequestEdit,
}: Props) {
  const { t } = useTranslation()
  const channelQuery = useQuery({
    queryKey: queryKeys.slackFaq.channel(channelId),
    queryFn: () => getFaqChannel(channelId),
  })
  const channel = channelQuery.data

  return (
    <SectionErrorBoundary name="slack-faq-detail">
      <section className="faq-detail-pane" data-testid="faq-detail-pane">
        <header className="faq-detail-pane__header">
          <div>
            <span className={`faq-channel-row__dot ${channel?.enabled ? 'enabled' : 'disabled'}`} aria-hidden="true" />
            <div>
              <h3>{channel?.channelName ?? channelId}</h3>
              <p>{t('slackFaq.detail.description')}</p>
            </div>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onRequestEdit}>
            {t('slackFaq.detail.edit')}
          </button>
        </header>

        <nav className="faq-detail-pane__nav" aria-label={t('slackFaq.detail.navAria')}>
          {VIEWS.map((item) => (
            <button
              key={item}
              type="button"
              className={view === item ? 'is-active' : ''}
              aria-current={view === item ? 'page' : undefined}
              onClick={() => onViewChange(item)}
            >
              {t(`slackFaq.detail.views.${item}`)}
            </button>
          ))}
        </nav>

        <div className="faq-detail-pane__content">
          {view === 'overview' && <FaqOverview channelId={channelId} onRequestEdit={onRequestEdit} />}
          {view === 'test' && (
            <div className="faq-detail-pane__test-grid">
              <section><FaqProbe channelId={channelId} /></section>
              <section><FaqDryRun channelId={channelId} /></section>
            </div>
          )}
          {view === 'activity' && (
            <div className="faq-detail-pane__activity">
              <FaqEvents channelId={channelId} />
              <FaqFeedback channelId={channelId} />
            </div>
          )}
          {view === 'manage' && (
            <div className="faq-detail-pane__manage">
              <section><FaqReindex channelId={channelId} /></section>
              <details>
                <summary>{t('slackFaq.detail.deleteAndMaintenance')}</summary>
                <FaqDanger channelId={channelId} onChannelDeleted={onChannelDeleted} />
              </details>
            </div>
          )}
        </div>
      </section>
    </SectionErrorBoundary>
  )
}

import { useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, MoreHorizontal } from 'lucide-react'
import type { SessionDetailData, SessionExportFormat } from '../../types'
import { TimestampWithZone, Tooltip } from '../../../../shared/ui'
import { useEscapeClose } from '../../../../shared/lib/useEscapeClose'
import { ChannelIcon } from '../shared/ChannelIcon'
import { formatSessionUser } from '../shared/formatSessionUser'

interface SessionInfoBarProps {
  session: SessionDetailData
  onExport: (format: SessionExportFormat) => void
  onDelete: () => void
  onOpenInspector: () => void
  onFlag: () => void
}

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  if (hours > 0) return `${hours}h ${minutes % 60}m`
  if (minutes > 0) return `${minutes}m ${seconds % 60}s`
  return `${seconds}s`
}

export function SessionInfoBar({ session, onExport, onDelete, onOpenInspector, onFlag }: SessionInfoBarProps) {
  const { t } = useTranslation()
  const [showExportMenu, setShowExportMenu] = useState(false)
  const exportMenuId = useId()
  const exportContainerRef = useRef<HTMLDivElement | null>(null)
  const exportTriggerRef = useRef<HTMLButtonElement | null>(null)

  // Outside-click closes the dropdown so it stays out of the way once the
  // user moves on. Mirrors the pattern used by SavedViewsControl.
  useEffect(() => {
    if (!showExportMenu) return
    function handleDocClick(event: MouseEvent) {
      const target = event.target as Node | null
      if (
        exportContainerRef.current &&
        target &&
        !exportContainerRef.current.contains(target)
      ) {
        setShowExportMenu(false)
      }
    }
    document.addEventListener('mousedown', handleDocClick)
    return () => document.removeEventListener('mousedown', handleDocClick)
  }, [showExportMenu])

  // Escape closes the menu and returns focus to the trigger so keyboard users
  // can resume from where they were.
  useEscapeClose(
    () => {
      setShowExportMenu(false)
      exportTriggerRef.current?.focus()
    },
    { active: showExportMenu },
  )

  function handleExportSelect(format: SessionExportFormat) {
    onExport(format)
    setShowExportMenu(false)
    exportTriggerRef.current?.focus()
  }

  function sessionStatusLabel(status: string): string {
    const normalized = status.toLowerCase()
    const supported = ['completed', 'running', 'pending', 'failed', 'cancelled']
    return supported.includes(normalized) ? t(`conversations.status.${normalized}`) : t('conversations.status.unknown')
  }

  return (
    <div className="session-info-bar">
      <div className="session-info-bar-meta">
        <span>{formatSessionUser(t, session.userId, session.email)}</span>
        <ChannelIcon channel={session.channel} />
        {session.ipAddress && (
          <Tooltip content={t('conversations.detail.ipAddress')}>
            <span>{session.ipAddress}</span>
          </Tooltip>
        )}
        {session.status && <span className="session-status-text">{sessionStatusLabel(session.status)}</span>}
        <span>{t('conversations.detail.messages', { count: session.messages.length })}</span>
        {session.duration != null && <span>{formatDuration(session.duration)}</span>}
        {(session.createdAt ?? session.startedAt) != null && (
          <TimestampWithZone value={session.createdAt ?? session.startedAt ?? 0} />
        )}
      </div>
      <div className="session-info-bar-actions">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={onOpenInspector}
          title={t('conversations.detail.actions.openInspectorHint')}
        >
          {t('conversations.detail.openInspector')}
        </button>
        <details className="session-info-bar__actions">
          <summary aria-label={t('conversations.detail.actions.moreAria')}>
            <span>{t('conversations.detail.actions.more')}</span>
            <MoreHorizontal aria-hidden="true" className="session-info-bar__action-icon" strokeWidth={1.8} />
          </summary>
          <div className="session-info-bar__actions-menu">
            <button type="button" className="btn btn-secondary" onClick={onFlag}>
              {t('conversations.detail.flag')}
            </button>
            <div className="export-dropdown" ref={exportContainerRef}>
              <button
                ref={exportTriggerRef}
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowExportMenu((prev) => !prev)}
                aria-haspopup="menu"
                aria-expanded={showExportMenu}
                aria-controls={exportMenuId}
                title={t('conversations.detail.actions.exportHint')}
              >
                <span>{t('conversations.detail.export')}</span>
                <ChevronDown
                  className={`session-info-bar__export-chevron${showExportMenu ? ' is-open' : ''}`}
                  aria-hidden="true"
                  strokeWidth={1.8}
                />
              </button>
              {showExportMenu && (
                <div
                  id={exportMenuId}
                  className="export-dropdown-menu"
                  role="menu"
                  aria-label={t('conversations.detail.actions.exportMenuAria')}
                >
                  <button
                    type="button"
                    role="menuitem"
                    className="export-dropdown-item"
                    onClick={() => handleExportSelect('json')}
                  >
                    {t('conversations.detail.exportJson')}
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    className="export-dropdown-item"
                    onClick={() => handleExportSelect('markdown')}
                  >
                    {t('conversations.detail.exportMarkdown')}
                  </button>
                </div>
              )}
            </div>
            <button
              type="button"
              className="btn btn-danger"
              onClick={onDelete}
              title={t('conversations.detail.actions.deleteHint')}
            >
              {t('conversations.detail.delete')}
            </button>
          </div>
        </details>
      </div>
    </div>
  )
}

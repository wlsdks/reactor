import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { EmptyState, DetailModal, OperationButton } from '../../../shared/ui'
import { formatDateTime } from '../../../shared/lib/formatters'
import type { TemplateDetailResponse, VersionResponse } from '../types'

interface VersionsTabProps {
  template: TemplateDetailResponse
  onCreateVersion: (data: { content: string; changeLog: string }) => void
  onActivate: (version: VersionResponse) => void
  onArchive: (version: VersionResponse) => void
  saving?: boolean
}

export function VersionsTab({
  template,
  onCreateVersion,
  onActivate,
  onArchive,
  saving,
}: VersionsTabProps) {
  const { t } = useTranslation()
  const [showModal, setShowModal] = useState(false)
  const [content, setContent] = useState('')
  const [changeLog, setChangeLog] = useState('')
  const versions = template.activeVersion && !template.versions.some((version) => version.id === template.activeVersion?.id)
    ? [template.activeVersion, ...template.versions]
    : template.versions

  const versionState = (status: VersionResponse['status']) => {
    if (status === 'ACTIVE') return t('promptStudio.versionStatus.active')
    if (status === 'DRAFT') return t('promptStudio.versionStatus.draft')
    if (status === 'ARCHIVED') return t('promptStudio.versionStatus.archived')
    return t('promptStudio.versionStatus.unknown')
  }

  const openModal = () => {
    const activeContent = template.activeVersion?.content ?? ''
    setContent(activeContent)
    setChangeLog('')
    setShowModal(true)
  }

  const handleSubmit = () => {
    if (saving) return
    onCreateVersion({ content, changeLog })
    setShowModal(false)
  }

  return (
    <>
      <div className="detail-section">
        <div className="detail-section-header">
          <h3>{t('promptStudio.tabs.versions')}</h3>
          <button className="btn btn-primary btn-sm" onClick={openModal}>
            {t('prompts.newVersion')}
          </button>
        </div>
        <p className="detail-note" style={{ marginTop: 0 }}>
          {t('promptStudio.versionsGuide')}
        </p>

        {versions.length === 0 ? (
          <EmptyState message={t('prompts.noVersions')} />
        ) : (
          <div className="version-list">
            {versions.map((v) => (
              <div
                key={v.id}
                className={`version-item${v.status === 'ACTIVE' ? ' version-active' : ''}`}
              >
                <div className="version-header">
                  <strong>{t('promptStudio.versionLabel', { version: v.version })}</strong>
                  <span
                    className={`version-state version-state--${v.status.toLowerCase()}`}
                    aria-label={versionState(v.status)}
                    title={versionState(v.status)}
                  >
                    <span aria-hidden="true" />
                    {versionState(v.status)}
                  </span>
                  <span className="version-date">
                    {formatDateTime(v.createdAt)}
                  </span>
                </div>
                {v.changeLog && (
                  <div className="version-changelog">{v.changeLog}</div>
                )}
                <p className="version-content">
                  {v.content.slice(0, 300)}
                  {v.content.length > 300 ? '\u2026' : ''}
                </p>
                <div className="version-item__actions">
                  {(v.status === 'DRAFT' || v.status === 'ARCHIVED') && (
                    <OperationButton onClick={() => onActivate(v)}>
                      {t('prompts.activate')}
                    </OperationButton>
                  )}
                  {v.status === 'ACTIVE' && (
                    <OperationButton variant="secondary" onClick={() => onArchive(v)}>
                      {t('prompts.archive')}
                    </OperationButton>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <DetailModal
        open={showModal}
        title={t('prompts.newVersion')}
        onClose={() => setShowModal(false)}
      >
        <p className="detail-note">{t('prompts.newVersionHelp')}</p>
        <div className="form-group">
          <label htmlFor="version-content">{t('prompts.content')}</label>
          <textarea
            id="version-content"
            name="content"
            rows={12}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={t('prompts.contentPlaceholder')}
          />
        </div>
        <div className="form-group">
          <label htmlFor="version-changelog">
            {t('prompts.changeLog')}
          </label>
          <input
            id="version-changelog"
            name="changeLog"
            placeholder={t('prompts.changeLogPlaceholder')}
            value={changeLog}
            onChange={(e) => setChangeLog(e.target.value)}
          />
        </div>
        <div className="modal-actions">
          <OperationButton variant="secondary" onClick={() => setShowModal(false)}>
            {t('common.cancel')}
          </OperationButton>
          <OperationButton onClick={handleSubmit} isOperating={saving}>{t('common.save')}</OperationButton>
        </div>
      </DetailModal>
    </>
  )
}

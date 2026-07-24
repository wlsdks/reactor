import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ConfirmDialog, CopyButton } from '../../../shared/ui'
import { formatDateTime } from '../../../shared/lib/formatters'
import type { TemplateDetailResponse } from '../types'

export interface SettingsTabProps {
  template: TemplateDetailResponse
  onUpdate: (data: { name: string; description: string }) => void
  onDelete: () => void
  saving?: boolean
  experimentCount?: number
}

export function SettingsTab({
  template,
  onUpdate,
  onDelete,
  saving = false,
  experimentCount = 0,
}: SettingsTabProps) {
  const { t } = useTranslation()

  const [editingName, setEditingName] = useState(false)
  const [editingDescription, setEditingDescription] = useState(false)
  const [nameValue, setNameValue] = useState(template.name)
  const [descriptionValue, setDescriptionValue] = useState(template.description)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)

  function handleNameKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      setEditingName(false)
      onUpdate({ name: nameValue, description: template.description })
    } else if (e.key === 'Escape') {
      setNameValue(template.name)
      setEditingName(false)
    }
  }

  function handleDescriptionKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      setEditingDescription(false)
      onUpdate({ name: template.name, description: descriptionValue })
    } else if (e.key === 'Escape') {
      setDescriptionValue(template.description)
      setEditingDescription(false)
    }
  }

  function handleDeleteConfirm() {
    setShowDeleteDialog(false)
    onDelete()
  }

  function activateName() {
    setNameValue(template.name)
    setEditingName(true)
  }

  function activateDescription() {
    setDescriptionValue(template.description)
    setEditingDescription(true)
  }

  function handleEditableKeyDown(e: React.KeyboardEvent<HTMLSpanElement>, activate: () => void) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      activate()
    }
  }

  const deleteMessage = experimentCount > 0
    ? `${t('prompts.deleteConfirm', { name: template.name })} ${t('promptStudio.deleteTemplateWarning', { count: experimentCount })}`
    : t('prompts.deleteConfirm', { name: template.name })

  return (
    <div className="detail-section">
      <div className="form-group">
        <label>{t('common.name')}</label>
        {editingName ? (
          <input
            type="text"
            value={nameValue}
            onChange={(e) => setNameValue(e.target.value)}
            onKeyDown={handleNameKeyDown}
            onBlur={() => {
              setNameValue(template.name)
              setEditingName(false)
            }}
            autoFocus
            disabled={saving}
          />
        ) : (
          <span
            className="detail-editable"
            onClick={activateName}
            onKeyDown={(e) => handleEditableKeyDown(e, activateName)}
            role="button"
            tabIndex={0}
            aria-label={t('common.edit') + ' ' + t('common.name')}
            data-testid="editable-name"
          >
            {template.name}
          </span>
        )}
      </div>

      <div className="form-group">
        <label>{t('common.description')}</label>
        {editingDescription ? (
          <input
            type="text"
            value={descriptionValue}
            onChange={(e) => setDescriptionValue(e.target.value)}
            onKeyDown={handleDescriptionKeyDown}
            onBlur={() => {
              setDescriptionValue(template.description)
              setEditingDescription(false)
            }}
            autoFocus
            disabled={saving}
          />
        ) : (
          <span
            className="detail-editable"
            onClick={activateDescription}
            onKeyDown={(e) => handleEditableKeyDown(e, activateDescription)}
            role="button"
            tabIndex={0}
            aria-label={t('common.edit') + ' ' + t('common.description')}
            data-testid="editable-description"
          >
            {template.description || t('common.noData')}
          </span>
        )}
      </div>

      <div className="meta-grid">
        <span>{t('common.createdAt')}: {formatDateTime(template.createdAt)}</span>
        <span>{t('common.updatedAt')}: {formatDateTime(template.updatedAt)}</span>
      </div>

      <details className="prompt-technical-details">
        <summary>{t('promptStudio.technicalDetails')}</summary>
        <div className="detail-value-row">
          <code>{template.id}</code>
          <CopyButton value={template.id} label={t('promptStudio.templateId')} />
        </div>
      </details>

      <div className="detail-actions" style={{ marginTop: 'var(--space-6)' }}>
        <button
          className="btn btn-danger"
          onClick={() => setShowDeleteDialog(true)}
        >
          {t('common.delete')}
        </button>
      </div>

      {showDeleteDialog && (
        <ConfirmDialog
          title={t('prompts.deleteTitle')}
          message={deleteMessage}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setShowDeleteDialog(false)}
          danger
        />
      )}
    </div>
  )
}

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import type { SessionTag, TrustStatus } from '../../types'

interface SessionTagsProps {
  tags: SessionTag[]
  trust?: TrustStatus
  onAddTag: (label: string, comment?: string) => void
  onRemoveTag: (tagId: string) => void
  showForm?: boolean
  onFormToggle?: (show: boolean) => void
}

export function SessionTags({ tags, trust, onAddTag, onRemoveTag, showForm: controlledShowForm, onFormToggle }: SessionTagsProps) {
  const { t } = useTranslation()
  const [internalShowForm, setInternalShowForm] = useState(false)
  const [newLabel, setNewLabel] = useState('')
  const [newComment, setNewComment] = useState('')

  // Support both controlled (via props) and uncontrolled (internal) form visibility
  const showForm = controlledShowForm ?? internalShowForm
  const setShowForm = (val: boolean) => {
    if (onFormToggle) {
      onFormToggle(val)
    } else {
      setInternalShowForm(val)
    }
  }

  function handleSave() {
    if (!newLabel.trim()) return
    onAddTag(newLabel.trim(), newComment.trim() || undefined)
    setNewLabel('')
    setNewComment('')
    setShowForm(false)
  }

  return (
    <div className="session-tags">
      {/* System trust tag - not removable */}
      {trust && (
        <span className="session-trust-text">
          {t(`conversations.trust.${trust}`)}
        </span>
      )}

      {/* Manual tags - removable */}
      {tags.map((tag) => (
        <span key={tag.id} className="session-tag session-tag--manual">
          {tag.label}
          <button
            className="session-tag-remove"
            onClick={() => onRemoveTag(tag.id)}
            aria-label={`Remove tag ${tag.label}`}
          >
            <X size={14} aria-hidden="true" />
          </button>
        </span>
      ))}

      {/* Add tag button/form */}
      {showForm ? (
        <div className="session-tag-form">
          <input
            placeholder={t('conversations.tags.tagLabel')}
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
          />
          <input
            placeholder={t('conversations.tags.comment')}
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
          />
          <button className="btn btn-secondary btn-sm" onClick={handleSave}>
            {t('conversations.tags.save')}
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => setShowForm(false)}>
            {t('conversations.tags.cancel')}
          </button>
        </div>
      ) : null}
    </div>
  )
}

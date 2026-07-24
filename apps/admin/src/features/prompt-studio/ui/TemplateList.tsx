import { useTranslation } from 'react-i18next'
import { EmptyState } from '../../../shared/ui'
import type { TemplateResponse, VersionStatus } from '../types'

interface TemplateListProps {
  templates: TemplateResponse[]
  selectedId: string | null
  onSelect: (id: string) => void
  onCreateNew: () => void
  activeVersions?: Record<string, { version: number; status: VersionStatus }>
}

export function TemplateList({ templates, selectedId, onSelect, onCreateNew, activeVersions }: TemplateListProps) {
  const { t } = useTranslation()

  if (templates.length === 0) {
    return (
      <EmptyState
        message={t('prompts.empty')}
        actionLabel={t('prompts.createTemplate')}
        onAction={onCreateNew}
      />
    )
  }

  return (
    <section aria-label={t('promptStudio.templateListLabel')}>
      <div className="template-list-header">
        <span>{t('promptStudio.templateListLabel')}</span>
        <span>{t('promptStudio.templateCount', { count: templates.length })}</span>
      </div>
      {templates.map(tpl => (
        <button
          type="button"
          key={tpl.id}
          className={`template-list-item${selectedId === tpl.id ? ' selected' : ''}`}
          onClick={() => onSelect(tpl.id)}
          aria-pressed={selectedId === tpl.id}
        >
          <span className="template-name">{tpl.name}</span>
          {activeVersions?.[tpl.id] && (
            <span className="template-version-label">
              {t('promptStudio.versionLabel', { version: activeVersions[tpl.id].version })}
            </span>
          )}
        </button>
      ))}
      <button
        className="btn btn-secondary btn-full template-list-create-btn"
        onClick={onCreateNew}
      >
        {t('prompts.createTemplate')}
      </button>
    </section>
  )
}

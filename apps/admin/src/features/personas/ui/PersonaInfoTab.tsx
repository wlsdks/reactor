import { useTranslation } from 'react-i18next'
import { OperationButton } from '../../../shared/ui'
import type { PersonaResponse } from '../types'

interface Props {
  persona: PersonaResponse
  onEdit: () => void
  onDelete: () => void
}

export function PersonaInfoTab({ persona, onEdit, onDelete }: Props) {
  const { t } = useTranslation()

  return (
    <div className="persona-info-tab">
      <dl className="persona-detail-facts">
        <div><dt>{t('personas.default')}</dt><dd>{persona.isDefault ? t('common.yes') : t('common.no')}</dd></div>
        <div><dt>{t('common.status')}</dt><dd>{persona.isActive ? t('personas.active') : t('personas.inactive')}</dd></div>
      </dl>

      <div className="detail-actions persona-info-tab__actions">
        <OperationButton variant="secondary" onClick={onEdit}>{t('common.edit')}</OperationButton>
        <OperationButton
          variant="danger"
          disabled={persona.isDefault}
          disabledReason={persona.isDefault ? t('personas.cannotDeleteDefault') : undefined}
          onClick={onDelete}
        >
          {t('common.delete')}
        </OperationButton>
      </div>

      <section className="persona-info-tab__section" aria-labelledby="persona-instructions-title">
        <h3 id="persona-instructions-title">{t('personas.systemPrompt')}</h3>
        <p className="persona-info-tab__content">{persona.systemPrompt}</p>
      </section>

      {persona.description ? (
        <section className="persona-info-tab__section" aria-labelledby="persona-purpose-title">
          <h3 id="persona-purpose-title">{t('personas.purposeNote')}</h3>
          <p className="persona-info-tab__content">{persona.description}</p>
        </section>
      ) : null}

      {persona.responseGuideline ? (
        <section className="persona-info-tab__section" aria-labelledby="persona-guideline-title">
          <h3 id="persona-guideline-title">{t('personas.responseGuideline')}</h3>
          <p className="persona-info-tab__content">{persona.responseGuideline}</p>
        </section>
      ) : null}

      {persona.welcomeMessage ? (
        <section className="persona-info-tab__section" aria-labelledby="persona-welcome-title">
          <h3 id="persona-welcome-title">{t('personas.welcomeMessage')}</h3>
          <p className="persona-info-tab__content">{persona.welcomeMessage}</p>
        </section>
      ) : null}

      <details className="persona-technical-details">
        <summary>{t('personas.technicalPersona')}</summary>
        <dl>
          <div><dt>{t('personas.personaIdentifier')}</dt><dd><code>{persona.id}</code></dd></div>
          <div><dt>{t('personas.linkedTemplateIdentifier')}</dt><dd><code>{persona.promptTemplateId ?? '-'}</code></dd></div>
        </dl>
      </details>
    </div>
  )
}

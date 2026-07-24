import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { HelpHint, SideDrawer } from '../../../shared/ui'
import { formatLocaleNumber } from '../../../shared/lib/intl'
import type { AlertRule } from '../../platform-admin/types'
import { estimateMonthlyCost } from '../pricing'
import type { ModelEntry } from '../types'
import './model-registry.css'

interface ModelDetailDrawerProps {
  model: ModelEntry | null
  alerts?: AlertRule[]
  onClose: () => void
}

const MONO: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 'var(--text-xxs)',
}

function findAlertsForModel(model: ModelEntry, alerts: AlertRule[] | undefined): AlertRule[] {
  if (!alerts || alerts.length === 0) return []
  const needle = model.name.toLowerCase()
  return alerts.filter(rule => {
    const haystack = [rule.name, rule.description ?? '', rule.metric].join(' ').toLowerCase()
    return haystack.includes(needle)
  })
}

function displayProvider(value: string, t: (key: string) => string): string {
  switch (value.trim().toLowerCase()) {
    case 'ollama':
      return t('modelsPage.providerSmoke.providerLabels.local')
    case 'openai':
      return t('modelsPage.providerSmoke.providerLabels.openai')
    case 'anthropic':
      return t('modelsPage.providerSmoke.providerLabels.anthropic')
    default:
      return t('modelsPage.providerSmoke.providerLabels.unknown')
  }
}

function displayCapability(value: string, t: (key: string) => string): string {
  const key = value.trim().toLowerCase().replace(/[_.:-]+/g, '')
  if (key === 'tools' || key === 'toolcalling') return t('modelsPage.drawer.capabilityLabels.tools')
  if (key === 'vision' || key === 'image') return t('modelsPage.drawer.capabilityLabels.vision')
  if (key === 'json' || key === 'structuredoutput') return t('modelsPage.drawer.capabilityLabels.structuredOutput')
  if (key === 'stream' || key === 'streaming') return t('modelsPage.drawer.capabilityLabels.streaming')
  return t('modelsPage.drawer.capabilityLabels.unknown')
}

function displayAlertSeverity(value: string | null | undefined, t: (key: string) => string): { label: string; tone: string } {
  switch (value?.trim().toLowerCase()) {
    case 'critical':
    case 'error':
      return { label: t('modelsPage.drawer.severityLabels.critical'), tone: 'critical' }
    case 'warning':
    case 'warn':
      return { label: t('modelsPage.drawer.severityLabels.warning'), tone: 'warning' }
    case 'info':
      return { label: t('modelsPage.drawer.severityLabels.info'), tone: 'info' }
    default:
      return { label: t('modelsPage.drawer.severityLabels.unknown'), tone: 'unknown' }
  }
}

export function ModelDetailDrawer({ model, alerts, onClose }: ModelDetailDrawerProps) {
  const { t } = useTranslation()
  const [inputTokensStr, setInputTokensStr] = useState('1000000')
  const [outputTokensStr, setOutputTokensStr] = useState('1000000')

  const inputTokens = Number.parseFloat(inputTokensStr.replace(/[,_\s]/g, ''))
  const outputTokens = Number.parseFloat(outputTokensStr.replace(/[,_\s]/g, ''))

  const estimate = model
    ? estimateMonthlyCost(
      inputTokens,
      outputTokens,
      model.inputPricePerMillionTokens,
      model.outputPricePerMillionTokens,
    )
    : 0

  const relatedAlerts = model ? findAlertsForModel(model, alerts) : []

  return (
    <SideDrawer
      open={!!model}
      title={t('modelsPage.drawer.title')}
      onClose={onClose}
    >
      {model && (
        <div className="model-detail-drawer">
          <div className="model-detail-drawer__header">
            <span className="model-detail-drawer__name" style={MONO}>{model.name}</span>
            <span className="model-detail-drawer__actions">
              {model.isDefault && (
                <span className="model-detail-drawer__default">{t('modelsPage.default')}</span>
              )}
              {model.provider && (
                <span className="model-detail-drawer__provider">{displayProvider(model.provider, t)}</span>
              )}
            </span>
          </div>

          <section className="model-detail-drawer__section">
            <h3 className="model-detail-drawer__section-title">
              {t('modelsPage.drawer.pricingSection')}
            </h3>
            <dl className="model-detail-drawer__pricing">
              <dt>{t('modelsPage.inputPrice')}</dt>
              <dd style={MONO}>${model.inputPricePerMillionTokens.toFixed(2)}</dd>
              <dt>{t('modelsPage.outputPrice')}</dt>
              <dd style={MONO}>${model.outputPricePerMillionTokens.toFixed(2)}</dd>
            </dl>

            <div className="model-detail-drawer__estimator">
              <h4 className="model-detail-drawer__subtitle">
                {t('modelsPage.drawer.monthlyEstimator')}
              </h4>
              <div className="form-row">
                <div className="form-group">
                  <div className="form-label-row">
                    <label htmlFor="model-detail-input-tokens">
                      {t('modelsPage.drawer.expectedInputTokens')}
                    </label>
                    <HelpHint
                      title={t('modelsPage.drawer.expectedInputTokens')}
                      label={t('modelsPage.drawer.expectedTokensHelp')}
                    />
                  </div>
                  <input
                    id="model-detail-input-tokens"
                    type="number"
                    min={0}
                    step={100000}
                    value={inputTokensStr}
                    onChange={e => setInputTokensStr(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <div className="form-label-row">
                    <label htmlFor="model-detail-output-tokens">
                      {t('modelsPage.drawer.expectedOutputTokens')}
                    </label>
                    <HelpHint
                      title={t('modelsPage.drawer.expectedOutputTokens')}
                      label={t('modelsPage.drawer.expectedTokensHelp')}
                    />
                  </div>
                  <input
                    id="model-detail-output-tokens"
                    type="number"
                    min={0}
                    step={100000}
                    value={outputTokensStr}
                    onChange={e => setOutputTokensStr(e.target.value)}
                  />
                </div>
              </div>
              <div className="model-detail-drawer__estimate">
                <span>{t('modelsPage.drawer.estimatedMonthlyCost')}</span>
                <strong style={MONO} data-testid="model-monthly-estimate">
                  ${estimate.toFixed(2)}
                </strong>
              </div>
            </div>
          </section>

          <section className="model-detail-drawer__section">
            <h3 className="model-detail-drawer__section-title">
              {t('modelsPage.drawer.capabilitiesSection')}
            </h3>
            {model.capabilities && model.capabilities.length > 0 ? (
              <div className="model-detail-drawer__chip-row">
                {model.capabilities.map(cap => (
                  <span key={cap} className="model-detail-drawer__capability" data-testid="model-capability-chip">
                    {displayCapability(cap, t)}
                  </span>
                ))}
              </div>
            ) : (
              <p className="model-detail-drawer__muted">
                {t('modelsPage.drawer.noCapabilities')}
              </p>
            )}
          </section>

          <section className="model-detail-drawer__section">
            <h3 className="model-detail-drawer__section-title">
              {t('modelsPage.drawer.contextSection')}
            </h3>
            <dl className="model-detail-drawer__pricing">
              <dt>{t('modelsPage.contextLength')}</dt>
              <dd style={MONO}>{formatLocaleNumber(model.contextLength)}</dd>
              <dt>{t('modelsPage.maxTokens')}</dt>
              <dd style={MONO}>{formatLocaleNumber(model.maxTokens)}</dd>
            </dl>
          </section>

          <section className="model-detail-drawer__section">
            <h3 className="model-detail-drawer__section-title">
              {t('modelsPage.drawer.alertsSection')}
            </h3>
            {relatedAlerts.length > 0 ? (
              <ul className="model-detail-drawer__alerts">
                {relatedAlerts.map(rule => {
                  const severity = displayAlertSeverity(rule.severity, t)
                  return (
                    <li key={rule.id ?? rule.name}>
                      <span className={`model-detail-drawer__alert-severity is-${severity.tone}`}>{severity.label}</span>
                      <span className="model-detail-drawer__alert-name">{rule.name}</span>
                      <details className="model-detail-drawer__alert-technical">
                        <summary>{t('modelsPage.drawer.technicalDetails')}</summary>
                        <code style={MONO}>{rule.metric}</code>
                      </details>
                    </li>
                  )
                })}
              </ul>
            ) : (
              <p className="model-detail-drawer__muted">
                {t('modelsPage.drawer.noAlerts')}
              </p>
            )}
          </section>
        </div>
      )}
    </SideDrawer>
  )
}

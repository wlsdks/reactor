import './PlatformPricingAlertsTab.css'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DataTable, EmptyState, LoadingSpinner, Tooltip } from '../../../shared/ui'
import { formatISODate } from '../../../shared/lib/formatters'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import type { AlertInstance, AlertRule, AlertSeverity, AlertType, ModelPricing } from '../types'

interface PricingForm {
  provider: string
  model: string
  promptPricePer1m: string
  completionPricePer1m: string
  cachedInputPricePer1m: string
  reasoningPricePer1m: string
  batchPromptPricePer1m: string
  batchCompletionPricePer1m: string
}

interface AlertRuleForm {
  name: string
  description: string
  metric: string
  threshold: string
  windowMinutes: string
  type: AlertType
  severity: AlertSeverity
  tenantId: string
  enabled: boolean
  platformOnly: boolean
}

export type PricingAlertsSection = 'pricing' | 'alerts'

interface PlatformPricingAlertsTabProps {
  pricing: ModelPricing[]
  alertRules: AlertRule[]
  activeAlerts: AlertInstance[]
  saving: boolean
  pricingForm: PricingForm
  ruleForm: AlertRuleForm
  onPricingFormChange: (form: PricingForm) => void
  onRuleFormChange: (form: AlertRuleForm) => void
  onUpsertPricing: () => void
  onSaveAlertRule: () => void
  onDeleteRule: (id: string) => void
  onResolveAlert: (id: string) => void
  section?: PricingAlertsSection
  defaultModelName?: string | null
  pricingError?: unknown
  alertRulesError?: unknown
  activeAlertsError?: unknown
  onRetry?: () => void
}

const TYPE_LABELS: Record<AlertType, string> = {
  STATIC_THRESHOLD: '고정 임계값',
  BASELINE_ANOMALY: '기준선 이상 탐지',
  ERROR_BUDGET_BURN_RATE: '오류 예산 소진율',
}

const SEVERITY_LABELS: Record<AlertSeverity, string> = {
  INFO: '정보',
  WARNING: '주의',
  CRITICAL: '긴급',
}

function severityLabel(value: AlertSeverity | undefined): string {
  return SEVERITY_LABELS[value ?? 'WARNING']
}

export function PlatformPricingAlertsTab({
  pricing,
  alertRules,
  activeAlerts,
  saving,
  pricingForm,
  ruleForm,
  onPricingFormChange,
  onRuleFormChange,
  onUpsertPricing,
  onSaveAlertRule,
  onDeleteRule,
  onResolveAlert,
  section,
  defaultModelName,
  pricingError,
  alertRulesError,
  activeAlertsError,
  onRetry,
}: PlatformPricingAlertsTabProps) {
  const { t } = useTranslation()
  const [editingPricing, setEditingPricing] = useState(false)
  const [editingRule, setEditingRule] = useState(false)
  const showPricing = section === undefined || section === 'pricing'
  const showAlerts = section === undefined || section === 'alerts'

  const pricingColumns = [
    { key: 'provider', header: t('platformAdminPage.provider'), responsivePriority: 1, render: (row: ModelPricing) => row.provider },
    {
      key: 'model', header: t('platformAdminPage.model'), responsivePriority: 1, render: (row: ModelPricing) => (
        <span>{row.model}{row.model.toLowerCase() === defaultModelName?.toLowerCase() && <span className="model-default-label">{t('modelsPage.default')}</span>}</span>
      ),
    },
    { key: 'prompt', header: t('platformAdminPage.promptPer1m'), responsivePriority: 1, render: (row: ModelPricing) => <span className="data-mono">${row.promptPricePer1m}</span> },
    { key: 'completion', header: t('platformAdminPage.completionPer1m'), responsivePriority: 1, render: (row: ModelPricing) => <span className="data-mono">${row.completionPricePer1m}</span> },
    { key: 'effectiveFrom', header: t('platformAdminPage.effective'), responsivePriority: 2, render: (row: ModelPricing) => formatISODate(row.effectiveFrom) },
  ]

  const alertRuleColumns = [
    { key: 'name', header: t('platformAdminPage.rule'), responsivePriority: 1, render: (row: AlertRule) => <strong className="alert-rule-name">{row.name}</strong> },
    { key: 'type', header: t('platformAdminPage.type'), responsivePriority: 2, render: (row: AlertRule) => TYPE_LABELS[row.type] },
    { key: 'severity', header: t('platformAdminPage.severity'), responsivePriority: 1, render: (row: AlertRule) => <span className={`alert-severity is-${(row.severity ?? 'WARNING').toLowerCase()}`}><span aria-hidden="true" />{severityLabel(row.severity)}</span> },
    { key: 'metric', header: t('platformAdminPage.metric'), responsivePriority: 1, render: (row: AlertRule) => <span className="data-mono">{row.metric}</span> },
    { key: 'threshold', header: t('platformAdminPage.threshold'), responsivePriority: 1, render: (row: AlertRule) => <span className="data-mono">{row.threshold}</span> },
    { key: 'windowMinutes', header: t('platformAdminPage.windowMinutes'), responsivePriority: 3, render: (row: AlertRule) => `${row.windowMinutes ?? 15}분` },
    { key: 'actions', header: '', responsivePriority: 1, render: (row: AlertRule) => <button className="btn btn-ghost btn-sm" type="button" onClick={(event) => { event.stopPropagation(); if (row.id) onDeleteRule(row.id) }}>{t('common.delete')}</button> },
  ]

  const activeAlertColumns = [
    { key: 'severity', header: t('platformAdminPage.severity'), responsivePriority: 1, render: (row: AlertInstance) => <span className={`alert-severity is-${row.severity.toLowerCase()}`}><span aria-hidden="true" />{severityLabel(row.severity)}</span> },
    {
      key: 'message', header: t('platformAdminPage.message'), responsivePriority: 1, render: (row: AlertInstance) => (
        <Tooltip content={row.message}><span className="text-truncate">{row.message}</span></Tooltip>
      ),
    },
    { key: 'metricValue', header: t('modelsPage.observedAndThreshold'), responsivePriority: 1, render: (row: AlertInstance) => <span className="data-mono">{row.metricValue} / {row.threshold}</span> },
    { key: 'firedAt', header: t('platformAdminPage.fired'), responsivePriority: 2, render: (row: AlertInstance) => formatISODate(new Date(row.firedAt).toISOString()) },
    { key: 'actions', header: '', responsivePriority: 1, render: (row: AlertInstance) => <button className="btn btn-secondary btn-sm" type="button" onClick={() => onResolveAlert(row.id)}>{t('platformAdminPage.resolve')}</button> },
  ]

  return (
    <div className="pricing-alerts-workspace">
      {showPricing && (
        <section className="pricing-operations" aria-labelledby="pricing-operations-title">
          <div className="pricing-operations__heading">
            <div><h2 id="pricing-operations-title">{t('modelsPage.pricingTitle')}</h2><p>{t('modelsPage.pricingDescription')}</p></div>
            <button className="btn btn-primary btn-sm" type="button" onClick={() => setEditingPricing((value) => !value)}>{editingPricing ? t('common.cancel') : t('platformAdminPage.upsertPricing')}</button>
          </div>
          {editingPricing && (
            <form className="pricing-form" onSubmit={(event) => { event.preventDefault(); onUpsertPricing() }}>
              <div className="form-group"><label htmlFor="pricing-provider">{t('platformAdminPage.provider')}</label><input id="pricing-provider" value={pricingForm.provider} onChange={(event) => onPricingFormChange({ ...pricingForm, provider: event.target.value })} /></div>
              <div className="form-group"><label htmlFor="pricing-model">{t('platformAdminPage.model')}</label><input id="pricing-model" value={pricingForm.model} onChange={(event) => onPricingFormChange({ ...pricingForm, model: event.target.value })} /></div>
              <div className="form-group"><label htmlFor="pricing-prompt-per1m">{t('platformAdminPage.promptPer1m')}</label><input id="pricing-prompt-per1m" inputMode="decimal" value={pricingForm.promptPricePer1m} onChange={(event) => onPricingFormChange({ ...pricingForm, promptPricePer1m: event.target.value })} /></div>
              <div className="form-group"><label htmlFor="pricing-completion-per1m">{t('platformAdminPage.completionPer1m')}</label><input id="pricing-completion-per1m" inputMode="decimal" value={pricingForm.completionPricePer1m} onChange={(event) => onPricingFormChange({ ...pricingForm, completionPricePer1m: event.target.value })} /></div>
              <button className="btn btn-primary" type="submit" disabled={saving}>{saving ? <LoadingSpinner size="sm" /> : t('platformAdminPage.savePricing')}</button>
            </form>
          )}
          {pricingError ? <EmptyState message={t('modelsPage.pricingLoadError')} description={getErrorMessage(pricingError)} actionLabel={t('common.retry')} onAction={onRetry} /> : pricing.length === 0 ? <EmptyState message={t('platformAdminPage.noPricing')} description={t('modelsPage.pricingEmptyDescription')} actionLabel={t('platformAdminPage.upsertPricing')} onAction={() => setEditingPricing(true)} /> : <DataTable columns={pricingColumns} data={pricing} keyFn={(row) => row.id} tableId="model-pricing" urlStateKey="model-pricing" />}
        </section>
      )}

      {showAlerts && (
        <>
          <section className="alert-rules-operations" aria-labelledby="alert-rules-title">
            <div className="pricing-operations__heading">
              <div><h2 id="alert-rules-title">{t('platformAdminPage.alertRules')}</h2><p>{t('modelsPage.alertRulesDescription')}</p></div>
              <button className="btn btn-primary btn-sm" type="button" onClick={() => setEditingRule((value) => !value)}>{editingRule ? t('common.cancel') : t('modelsPage.createAlertRule')}</button>
            </div>
            {editingRule && (
              <form className="alert-rule-form" onSubmit={(event) => { event.preventDefault(); onSaveAlertRule() }}>
                <label><span>{t('common.name')}</span><input value={ruleForm.name} onChange={(event) => onRuleFormChange({ ...ruleForm, name: event.target.value })} /></label>
                <label className="is-wide"><span>{t('common.description')}</span><input value={ruleForm.description} onChange={(event) => onRuleFormChange({ ...ruleForm, description: event.target.value })} /></label>
                <label><span>{t('platformAdminPage.metric')}</span><input className="data-mono" value={ruleForm.metric} onChange={(event) => onRuleFormChange({ ...ruleForm, metric: event.target.value })} /></label>
                <label><span>{t('platformAdminPage.threshold')}</span><input inputMode="decimal" value={ruleForm.threshold} onChange={(event) => onRuleFormChange({ ...ruleForm, threshold: event.target.value })} /></label>
                <label><span>{t('platformAdminPage.windowMinutes')}</span><input inputMode="numeric" value={ruleForm.windowMinutes} onChange={(event) => onRuleFormChange({ ...ruleForm, windowMinutes: event.target.value })} /></label>
                <label><span>{t('platformAdminPage.type')}</span><select value={ruleForm.type} onChange={(event) => onRuleFormChange({ ...ruleForm, type: event.target.value as AlertType })}>{Object.entries(TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label><span>{t('platformAdminPage.severity')}</span><select value={ruleForm.severity} onChange={(event) => onRuleFormChange({ ...ruleForm, severity: event.target.value as AlertSeverity })}>{Object.entries(SEVERITY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label><span>{t('platformAdminPage.tenantIdOptional')}</span><input className="data-mono" value={ruleForm.tenantId} onChange={(event) => onRuleFormChange({ ...ruleForm, tenantId: event.target.value })} /></label>
                <div className="alert-rule-form__checks"><label><input type="checkbox" checked={ruleForm.enabled} onChange={(event) => onRuleFormChange({ ...ruleForm, enabled: event.target.checked })} />{t('platformAdminPage.enabled')}</label><label><input type="checkbox" checked={ruleForm.platformOnly} onChange={(event) => onRuleFormChange({ ...ruleForm, platformOnly: event.target.checked })} />{t('platformAdminPage.platformOnly')}</label></div>
                <button className="btn btn-primary" type="submit" disabled={saving}>{saving ? <LoadingSpinner size="sm" /> : t('platformAdminPage.saveRule')}</button>
              </form>
            )}
            {alertRulesError ? <EmptyState message={t('modelsPage.alertRulesLoadError')} description={getErrorMessage(alertRulesError)} actionLabel={t('common.retry')} onAction={onRetry} /> : alertRules.length === 0 ? <EmptyState message={t('platformAdminPage.noAlertRules')} description={t('modelsPage.alertRulesEmptyDescription')} actionLabel={t('modelsPage.createAlertRule')} onAction={() => setEditingRule(true)} /> : <DataTable columns={alertRuleColumns} data={alertRules} keyFn={(row) => row.id ?? row.name} tableId="alert-rules" urlStateKey="alert-rules" />}
          </section>

          <section className="active-alerts" aria-labelledby="active-alerts-title">
            <div className="pricing-operations__heading"><div><h2 id="active-alerts-title">{t('platformAdminPage.activeAlertsTitle')}</h2><p>{t('modelsPage.activeAlertsDescription')}</p></div></div>
            {activeAlertsError ? <EmptyState message={t('modelsPage.activeAlertsLoadError')} description={getErrorMessage(activeAlertsError)} actionLabel={t('common.retry')} onAction={onRetry} /> : activeAlerts.length === 0 ? <EmptyState message={t('platformAdminPage.noActiveAlerts')} description={t('modelsPage.activeAlertsEmptyDescription')} /> : <DataTable columns={activeAlertColumns} data={activeAlerts} keyFn={(row) => row.id} tableId="active-alerts" urlStateKey="active-alerts" />}
          </section>
        </>
      )}
    </div>
  )
}

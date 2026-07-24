import './input-guard.css'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  PageHeader,
  ReleaseWorkflowBacklink,
  SkeletonCard,
  PipelineFlow,
  SideDrawer,
  Tabs,
  WorkspaceUnavailable,
  type TabDefinition,
  type PipelineStage,
} from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { usePageHelp } from '../../../shared/lib/usePageHelp'
import { useToastStore } from '../../../shared/store/toast.store'
import * as inputGuardApi from '../api'
import type { GuardStageConfig } from '../types'
import { InputGuardAuditTab } from './InputGuardAuditTab'
import { InputGuardStatsTab } from './InputGuardStatsTab'
import { InputGuardSimulateTab } from './InputGuardSimulateTab'
import { InputGuardRulesTab } from './InputGuardRulesTab'
import { StageConfigPanel } from './StageConfigPanel'
import { PipelineReorderModal } from './PipelineReorderModal'

type TabKey = 'pipeline' | 'rules' | 'stats' | 'simulate' | 'audit'

const STAGE_I18N_KEYS: Record<string, string> = {
  'rate-limit': 'RateLimit',
  'unicode-normalization': 'UnicodeNormalization',
  'injection-detection': 'InjectionDetection',
  'input-validation': 'InputValidation',
  'input-credential-masking': 'InputCredentialMasking',
  'rule-classification': 'RuleClassification',
  'llm-classification': 'LlmClassification',
  classification: 'Classification',
  'topic-drift': 'TopicDrift',
  permission: 'Permission',
}

function toDisplayStages(
  stages: GuardStageConfig[],
  t: (key: string) => string,
): PipelineStage[] {
  return stages.map((s) => {
    const translationKey = STAGE_I18N_KEYS[s.name] ?? s.name
    const nameKey = `inputGuard.stages.${translationKey}`
    const legacyNameKey = `inputGuard.stages.${s.name}`
    const descriptionKey = `inputGuard.stageDescriptions.${translationKey}`
    const legacyDescriptionKey = `inputGuard.stageDescriptions.${s.name}`
    const translatedName = t(nameKey)
    const legacyName = translatedName === nameKey ? t(legacyNameKey) : translatedName
    const translatedDescription = t(descriptionKey)
    const legacyDescription = translatedDescription === descriptionKey ? t(legacyDescriptionKey) : translatedDescription
    return {
      id: s.name,
      name: legacyName === legacyNameKey ? s.name.replaceAll('-', ' ') : legacyName,
      description: legacyDescription === legacyDescriptionKey ? undefined : legacyDescription,
      enabled: s.enabled,
      order: s.order,
      status: s.enabled ? 'active' : 'disabled',
    }
  })
}

function InputStageState({ enabled, t }: { enabled: boolean; t: (key: string) => string }) {
  return (
    <span className={`safety-policy-state is-${enabled ? 'ready' : 'muted'}`}>
      <span aria-hidden="true" />
      {enabled ? t('common.enabled') : t('common.inactive')}
    </span>
  )
}

export function InputGuardManager({ embedded = false }: { embedded?: boolean } = {}) {
  const { t } = useTranslation()
  usePageHelp({ helpKey: 'inputGuard.help' })
  const queryClient = useQueryClient()

  const [selectedStageId, setSelectedStageId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabKey>('pipeline')
  const [showReorder, setShowReorder] = useState(false)

  const {
    data: pipelineConfig,
    isLoading: pipelineLoading,
    isFetching: pipelineFetching,
    error: pipelineError,
  } = useQuery({
    queryKey: queryKeys.inputGuard.pipeline(),
    queryFn: inputGuardApi.getPipelineConfig,
  })

  const toggleStageMutation = useMutation({
    mutationFn: (params: { stageName: string; enabled: boolean }) =>
      inputGuardApi.updateGuardSettings({
        [`guard.stage.${params.stageName}.enabled`]: String(params.enabled),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.inputGuard.all() })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
    },
  })

  const stages = pipelineConfig?.stages ?? []
  const displayStages = toDisplayStages(stages, t)
  const selectedStage = stages.find((s) => s.name === selectedStageId) ?? null

  function handleStageClick(stage: PipelineStage) {
    setSelectedStageId(stage.id === selectedStageId ? null : stage.id)
  }

  function handleToggle(stageId: string, enabled: boolean) {
    const stage = stages.find((s) => s.name === stageId)
    if (!stage) return
    toggleStageMutation.mutate({ stageName: stage.name, enabled })
  }

  const errorMsg = pipelineError ? getErrorMessage(pipelineError) : null

  const pipelinePanel = pipelineLoading && pipelineConfig == null ? (
    <SkeletonCard height={140} />
  ) : errorMsg && pipelineConfig == null ? (
    <WorkspaceUnavailable
      title={t('inputGuard.unavailableTitle')}
      description={t('inputGuard.unavailableDescription')}
      retryLabel={t('common.retry')}
      retryingLabel={t('common.loading')}
      onRetry={() => queryClient.invalidateQueries({ queryKey: queryKeys.inputGuard.pipeline() })}
      isRetrying={pipelineFetching}
      secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
      guide={{
        title: t('inputGuard.recoveryTitle'),
        steps: [t('inputGuard.recoveryAccount'), t('inputGuard.recoveryConnection')],
        technicalLabel: t('common.technicalDetails'),
        technicalDetail: errorMsg,
      }}
    />
  ) : (
    <div className="input-guard-pipeline-section">
      <div className="input-guard-section-head">
        <div>
          <h2 className="section-title">{t('inputGuard.pipelineTitle')}</h2>
          {!pipelineLoading && (
            <p className="input-guard-section-summary">
              {t('inputGuard.stageCount', {
                count: stages.length,
                enabled: stages.filter((stage) => stage.enabled).length,
              })}
            </p>
          )}
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => setShowReorder(true)}
          disabled={stages.length === 0}
        >
          {t('inputGuard.reorderButton')}
        </button>
      </div>
      <PipelineFlow
        stages={displayStages}
        selectedStageId={selectedStageId}
        onStageClick={handleStageClick}
        onToggle={handleToggle}
      />
    </div>
  )

  const tabs: TabDefinition[] = [
    { value: 'pipeline', label: t('inputGuard.tabPipeline'), panel: pipelinePanel },
    { value: 'rules', label: t('inputGuard.tabRules'), panel: <InputGuardRulesTab /> },
    { value: 'stats', label: t('inputGuard.tabStats'), panel: <InputGuardStatsTab /> },
    { value: 'simulate', label: t('inputGuard.tabSimulate'), panel: <InputGuardSimulateTab /> },
    { value: 'audit', label: t('inputGuard.tabAudit'), panel: <InputGuardAuditTab /> },
  ]

  return (
    <div className={embedded ? 'safety-workspace__section' : 'page'}>
      {!embedded && (
        <PageHeader
          title={t('inputGuard.title')}
          description={t('inputGuard.subtitle')}
          actions={<ReleaseWorkflowBacklink stepId="cockpit" />}
          updateDocumentTitle
        />
      )}

      <Tabs
        tabs={tabs}
        value={activeTab}
        onChange={(v) => setActiveTab(v as TabKey)}
        ariaLabel={t('inputGuard.title')}
      />

      {showReorder && (
        <PipelineReorderModal
          open={showReorder}
          initialOrder={stages.map((s) => s.name)}
          onClose={() => setShowReorder(false)}
        />
      )}

      <SideDrawer
        open={!!selectedStage}
        title={
          selectedStage
            ? t(`inputGuard.stages.${selectedStage.name}`) || selectedStage.name
            : ''
        }
        onClose={() => setSelectedStageId(null)}
      >
        {selectedStage && (
          <div className="input-guard-drawer-content">
            <div className="input-guard-drawer-status">
              <InputStageState enabled={selectedStage.enabled} t={t} />
            </div>

            <details className="input-guard-technical-details">
              <summary>{t('inputGuard.technicalDetails')}</summary>
              <dl className="input-guard-drawer-details">
                <dt>{t('inputGuard.className')}</dt>
                <dd><code className="ig-stage-name">{selectedStage.className}</code></dd>
                <dt>{t('inputGuard.runtimeOverride')}</dt>
                <dd>{selectedStage.runtimeOverride ? t('common.yes') : t('common.no')}</dd>
              </dl>
            </details>

            <h3 className="input-guard-drawer-subtitle">
              {t('inputGuard.stageConfig.title')}
            </h3>
            <StageConfigPanel stageName={selectedStage.name} />
          </div>
        )}
      </SideDrawer>
    </div>
  )
}

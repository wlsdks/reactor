import { useTranslation } from 'react-i18next'
import { useRelativeTime } from '../lib/useRelativeTime'
import { ToggleSwitch } from './ToggleSwitch'

export interface PipelineStage {
  id: string
  name: string
  description?: string
  enabled: boolean
  order: number
  ruleCount?: number
  lastTriggered?: number
  status?: 'active' | 'disabled' | 'error'
}

interface PipelineFlowProps {
  stages: PipelineStage[]
  selectedStageId?: string | null
  onStageClick?: (stage: PipelineStage) => void
  onToggle?: (stageId: string, enabled: boolean) => void
}

/**
 * Wrap the live relative-time hook in a leaf component so the hook is called
 * once per row at the leaf level (rules-of-hooks compliant inside the .map
 * iteration of PipelineFlow).
 */
function StageLastTriggered({ timestamp }: { timestamp: number }) {
  const value = useRelativeTime(timestamp)
  return <>{value}</>
}

export function PipelineFlow({
  stages,
  selectedStageId,
  onStageClick,
  onToggle,
}: PipelineFlowProps) {
  const { t } = useTranslation()

  const sorted = [...stages].sort((a, b) => a.order - b.order)

  return (
    <ol className="pipeline-flow" aria-label={t('common.pipeline')}>
      {sorted.map((stage, index) => {
        const isSelected = selectedStageId === stage.id
        const isError = stage.status === 'error'

        return (
          <li
            key={stage.id}
            className={[
              'pipeline-card',
              isSelected ? 'pipeline-card--selected' : '',
              !stage.enabled ? 'pipeline-card--disabled' : '',
              isError ? 'pipeline-card--error' : '',
            ].filter(Boolean).join(' ')}
            onClick={onStageClick ? () => onStageClick(stage) : undefined}
            onKeyDown={onStageClick ? (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onStageClick(stage)
                }
            } : undefined}
            tabIndex={onStageClick ? 0 : undefined}
            aria-label={`${stage.name} ${t(stage.enabled ? 'common.enabled' : 'common.inactive')}`}
          >
            <span className="pipeline-card-order" aria-hidden="true">
              {String(index + 1).padStart(2, '0')}
            </span>
            <div className="pipeline-card-content">
              <span className="pipeline-card-name">{stage.name}</span>
              {stage.description && (
                <p className="pipeline-card-description">{stage.description}</p>
              )}
              <div className="pipeline-card-meta">
                {stage.ruleCount != null && (
                  <span>{t('common.rulesCount', { count: stage.ruleCount })}</span>
                )}
                {stage.lastTriggered != null && (
                  <span className="pipeline-card-time">
                    <StageLastTriggered timestamp={stage.lastTriggered} />
                  </span>
                )}
              </div>
            </div>
            {onToggle && (
              <div
                className="pipeline-card-control"
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => e.stopPropagation()}
              >
                <ToggleSwitch
                  checked={stage.enabled}
                  onChange={(checked) => onToggle(stage.id, checked)}
                  label={`${t('common.toggle')} ${stage.name}`}
                />
              </div>
            )}
          </li>
        )
      })}
    </ol>
  )
}

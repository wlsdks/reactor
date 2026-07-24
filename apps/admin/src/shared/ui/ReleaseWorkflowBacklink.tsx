import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import {
  RELEASE_WORKFLOW_ANCHOR_PATH,
  RELEASE_WORKFLOW_STEPS,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
  type ReleaseWorkflowStepId,
} from '../releaseWorkflow'

export interface ReleaseWorkflowBacklinkProps {
  stepId?: ReleaseWorkflowStepId
  stepNumber?: number
  showAdjacentSteps?: boolean
}

export function ReleaseWorkflowBacklink({
  stepId,
  stepNumber,
  showAdjacentSteps = false,
}: ReleaseWorkflowBacklinkProps) {
  const { t } = useTranslation()
  const resolvedStepNumber = stepId ? RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID[stepId] : stepNumber
  const accessibleLabel = resolvedStepNumber !== undefined
    ? t('common.releaseWorkflowBacklinkStep', { step: resolvedStepNumber })
    : undefined
  const currentStepIndex = stepId
    ? RELEASE_WORKFLOW_STEPS.findIndex((step) => step.id === stepId)
    : -1
  const previousStep = showAdjacentSteps && currentStepIndex > 0
    ? RELEASE_WORKFLOW_STEPS[currentStepIndex - 1]
    : undefined
  const nextStep = showAdjacentSteps && currentStepIndex >= 0
    ? RELEASE_WORKFLOW_STEPS[currentStepIndex + 1]
    : undefined

  const workflowLink = (
    <Link
      className="btn btn-secondary release-workflow-backlink"
      to={RELEASE_WORKFLOW_ANCHOR_PATH}
      aria-label={accessibleLabel}
    >
      {resolvedStepNumber !== undefined && (
        <span className="release-workflow-backlink__step" aria-hidden="true">
          {resolvedStepNumber}
        </span>
      )}
      {resolvedStepNumber !== undefined
        ? t('common.releaseWorkflowBacklinkStepShort', { step: resolvedStepNumber })
        : t('common.releaseWorkflowBacklink')}
    </Link>
  )

  if (!showAdjacentSteps || !stepId) return workflowLink

  const previousLabel = previousStep
    ? t('common.releaseWorkflowPreviousStep', {
        step: previousStep.stepNumber,
        title: t(previousStep.titleKey),
      })
    : undefined
  const nextLabel = nextStep
    ? t('common.releaseWorkflowNextStep', {
        step: nextStep.stepNumber,
        title: t(nextStep.titleKey),
      })
    : undefined

  return (
    <nav
      className="release-workflow-step-nav"
      aria-label={t('common.releaseWorkflowStepNavigation')}
    >
      {previousStep && previousLabel ? (
        <Link
          className="btn btn-secondary btn-sm release-workflow-step-nav__adjacent"
          to={previousStep.path}
          aria-label={previousLabel}
          title={previousLabel}
        >
          <ChevronLeft size={14} aria-hidden="true" />
          {t('common.releaseWorkflowPreviousStepShort', { step: previousStep.stepNumber })}
        </Link>
      ) : null}
      {workflowLink}
      {nextStep && nextLabel ? (
        <Link
          className="btn btn-secondary btn-sm release-workflow-step-nav__adjacent"
          to={nextStep.path}
          aria-label={nextLabel}
          title={nextLabel}
        >
          {t('common.releaseWorkflowNextStepShort', { step: nextStep.stepNumber })}
          <ChevronRight size={14} aria-hidden="true" />
        </Link>
      ) : null}
    </nav>
  )
}

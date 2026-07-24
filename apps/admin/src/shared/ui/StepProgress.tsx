import './StepProgress.css'

export interface StepDefinition {
  id: string
  label: string
}

export interface StepProgressProps {
  steps: StepDefinition[]
  currentId: string
  /**
   * Optional set of step ids the user has already visited. Used to enable
   * back-navigation. If omitted, only the current and previous steps are
   * clickable. The current step is always clickable.
   */
  visited?: Set<string>
  /**
   * Click handler. If provided, completed/visited steps are interactive;
   * if omitted, the indicator is purely visual.
   */
  onStep?: (id: string) => void
  ariaLabel?: string
}

/**
 * StepProgress — accessible wizard step indicator.
 *
 * Renders an ordered list with done / active / pending states. Used by the
 * Chat Inspector wizard (Configure → Execute → Inspect) and reusable for any
 * 3-step UX where progress communication matters more than tab affordance.
 */
export function StepProgress({
  steps,
  currentId,
  visited,
  onStep,
  ariaLabel = 'Steps',
}: StepProgressProps) {
  const currentIndex = Math.max(
    0,
    steps.findIndex((s) => s.id === currentId),
  )

  return (
    <ol className="step-progress" aria-label={ariaLabel}>
      {steps.map((step, idx) => {
        const isActive = idx === currentIndex
        const isDone = idx < currentIndex
        const visitedFlag = visited?.has(step.id) ?? false
        // A step is clickable when:
        //  - onStep handler is provided AND
        //  - it is the active step, OR a previous step (done), OR explicitly visited
        const clickable = !!onStep && (isActive || isDone || visitedFlag)
        const stateClass = isActive
          ? 'step-progress__item--active'
          : isDone
            ? 'step-progress__item--done'
            : 'step-progress__item--pending'

        return (
          <li
            key={step.id}
            className={`step-progress__item ${stateClass}`}
            aria-current={isActive ? 'step' : undefined}
          >
            <button
              type="button"
              className="step-progress__btn"
              data-testid={`step-progress-${step.id}`}
              onClick={() => clickable && onStep?.(step.id)}
              disabled={!clickable}
              aria-label={`Step ${idx + 1}: ${step.label}`}
            >
              <span className="step-progress__index" aria-hidden="true">
                {idx + 1}
              </span>
              <span className="step-progress__label">{step.label}</span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}

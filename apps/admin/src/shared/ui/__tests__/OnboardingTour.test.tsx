import { render, screen, fireEvent, act } from '../../../test/utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useTranslation } from 'react-i18next'
import { OnboardingTour, type TourStep } from '../OnboardingTour'

const STORAGE_KEY = 'reactor-admin-onboarding-completed-test'

function buildSteps(t: (key: string, opts?: Record<string, unknown>) => string): TourStep[] {
  return [
    {
      id: 'step-1',
      selector: '.spotlight-1',
      title: t('onboarding.tour.step1Title'),
      description: t('onboarding.tour.step1Description'),
      position: 'bottom',
    },
    {
      id: 'step-2',
      selector: '.spotlight-2',
      title: t('onboarding.tour.step2Title'),
      description: t('onboarding.tour.step2Description'),
      position: 'bottom',
    },
    {
      id: 'step-3',
      selector: '.spotlight-3',
      title: t('onboarding.tour.step3Title'),
      description: t('onboarding.tour.step3Description'),
      position: 'right',
    },
    {
      id: 'step-4',
      selector: '.spotlight-4',
      title: t('onboarding.tour.step4Title'),
      description: t('onboarding.tour.step4Description'),
      position: 'bottom',
    },
  ]
}

interface HarnessProps {
  storageKey?: string
  onComplete?: () => void
  onSkip?: () => void
}

function Harness({ storageKey = STORAGE_KEY, onComplete, onSkip }: HarnessProps) {
  const { t } = useTranslation()
  const steps = buildSteps(t)
  return (
    <>
      {/* Targets the tour will spotlight. */}
      <div className="spotlight-1">target one</div>
      <div className="spotlight-2">target two</div>
      <div className="spotlight-3">target three</div>
      <div className="spotlight-4">target four</div>
      <OnboardingTour
        steps={steps}
        storageKey={storageKey}
        onComplete={onComplete}
        onSkip={onSkip}
      />
    </>
  )
}

function clickByTestId(testId: string) {
  const el = screen.getByTestId(testId)
  fireEvent.click(el)
}

describe('OnboardingTour', () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.body
      .querySelectorAll('[data-testid="onboarding-tour"]')
      .forEach((n) => n.remove())
  })

  it('renders the backdrop and popover on first mount', () => {
    render(<Harness />)
    expect(screen.getByTestId('onboarding-tour')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('릴리즈 운영 흐름')).toBeInTheDocument()
    expect(screen.getByTestId('onboarding-tour-counter')).toHaveTextContent('1/4')
  })

  it('disables Previous on the first step', () => {
    render(<Harness />)
    const prev = screen.getByTestId('onboarding-tour-previous') as HTMLButtonElement
    expect(prev.disabled).toBe(true)
  })

  it('advances to the next step on Next click', () => {
    render(<Harness />)
    expect(screen.getByText('릴리즈 운영 흐름')).toBeInTheDocument()
    clickByTestId('onboarding-tour-next')
    expect(screen.getByText('Cmd+K 릴리즈 검색')).toBeInTheDocument()
    expect(screen.getByTestId('onboarding-tour-counter')).toHaveTextContent('2/4')
  })

  it('moves back via Previous after advancing', () => {
    render(<Harness />)
    clickByTestId('onboarding-tour-next')
    expect(screen.getByTestId('onboarding-tour-counter')).toHaveTextContent('2/4')
    clickByTestId('onboarding-tour-previous')
    expect(screen.getByTestId('onboarding-tour-counter')).toHaveTextContent('1/4')
  })

  it('shows the Complete label on the final step and writes storage on completion', () => {
    const onComplete = vi.fn()
    render(<Harness onComplete={onComplete} />)
    clickByTestId('onboarding-tour-next') // → step 2
    clickByTestId('onboarding-tour-next') // → step 3
    clickByTestId('onboarding-tour-next') // → step 4
    expect(screen.getByTestId('onboarding-tour-counter')).toHaveTextContent('4/4')
    const finalBtn = screen.getByTestId('onboarding-tour-next')
    expect(finalBtn).toHaveTextContent('완료')
    fireEvent.click(finalBtn)
    expect(onComplete).toHaveBeenCalledTimes(1)
    expect(window.localStorage.getItem(STORAGE_KEY)).not.toBeNull()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('dismisses on ESC and writes the skip marker to storage', () => {
    const onSkip = vi.fn()
    render(<Harness onSkip={onSkip} />)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(onSkip).toHaveBeenCalledTimes(1)
    expect(window.localStorage.getItem(STORAGE_KEY)).not.toBeNull()
  })

  it('dismisses on Skip click', () => {
    const onSkip = vi.fn()
    render(<Harness onSkip={onSkip} />)
    clickByTestId('onboarding-tour-skip')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(onSkip).toHaveBeenCalledTimes(1)
    expect(window.localStorage.getItem(STORAGE_KEY)).not.toBeNull()
  })

  it('renders nothing on a second mount once storage is set', () => {
    window.localStorage.setItem(STORAGE_KEY, '2026-04-24T00:00:00.000Z')
    const { container } = render(<Harness />)
    expect(container.querySelector('[data-testid="onboarding-tour"]')).toBeNull()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('clicking the backdrop dismisses the tour', () => {
    render(<Harness />)
    // Spotlight rect lookup happens in an effect; flush microtasks so the
    // shade panels render before the click.
    act(() => {})
    const shades = document.querySelectorAll('.onboarding-tour__shade')
    expect(shades.length).toBeGreaterThan(0)
    fireEvent.click(shades[0])
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(window.localStorage.getItem(STORAGE_KEY)).not.toBeNull()
  })

  it('renders nothing when no steps are provided', () => {
    const { container } = render(
      <OnboardingTour steps={[]} storageKey={`${STORAGE_KEY}-empty`} />,
    )
    expect(container.querySelector('[data-testid="onboarding-tour"]')).toBeNull()
  })

  it('falls back to a single full-screen shade when the target selector matches no element', () => {
    const tStub = (key: string) => key
    const steps: TourStep[] = [
      {
        id: 'missing',
        selector: '.does-not-exist',
        title: tStub('onboarding.tour.step1Title'),
        description: tStub('onboarding.tour.step1Description'),
      },
    ]
    render(<OnboardingTour steps={steps} storageKey={`${STORAGE_KEY}-missing`} />)
    // No cutout when the target is missing.
    expect(document.querySelector('.onboarding-tour__cutout')).toBeNull()
    // But the popover (dialog) still renders so the user isn't stuck.
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})

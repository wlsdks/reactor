import { describe, it, expect } from 'vitest'
import { render, screen } from '../../../test/utils'
import { PageSuspense } from '../PageSuspense'

describe('PageSuspense', () => {
  it('renders children when they do not suspend', () => {
    render(
      <PageSuspense>
        <div>Child content</div>
      </PageSuspense>,
    )
    expect(screen.getByText('Child content')).toBeInTheDocument()
  })

  it('wraps children in a Suspense boundary', () => {
    // The component itself wraps in Suspense. When children render
    // synchronously, no fallback is shown.
    const { container } = render(
      <PageSuspense>
        <span data-testid="inner">Hello</span>
      </PageSuspense>,
    )
    expect(screen.getByTestId('inner')).toBeInTheDocument()
    // Verify no loading spinner is shown for sync children
    expect(container.querySelector('.spinner')).not.toBeInTheDocument()
  })

  it('renders the loading spinner fallback when children suspend', async () => {
    // Simulate a component that suspends
    let resolve: (() => void) | undefined
    const promise = new Promise<void>((r) => {
      resolve = r
    })

    function SuspendingChild() {
      if (resolve) {
        throw promise
      }
      return <div>Loaded</div>
    }

    render(
      <PageSuspense>
        <SuspendingChild />
      </PageSuspense>,
    )

    // While suspended, the loading spinner should be visible
    expect(screen.getByLabelText('Loading')).toBeInTheDocument()

    // Clean up: resolve the promise so React can finish
    resolve?.()
  })

  it('applies the loading-fullscreen class on the fallback wrapper', () => {
    let resolve: (() => void) | undefined
    const promise = new Promise<void>((r) => {
      resolve = r
    })

    function SuspendingChild() {
      if (resolve) {
        throw promise
      }
      return <div>Done</div>
    }

    const { container } = render(
      <PageSuspense>
        <SuspendingChild />
      </PageSuspense>,
    )

    expect(container.querySelector('.loading-fullscreen')).toBeInTheDocument()

    resolve?.()
  })
})

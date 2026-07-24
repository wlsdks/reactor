import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, i18n } from '../../../test/utils'
import userEvent from '@testing-library/user-event'
import { InvalidateCacheModal } from '../ui/InvalidateCacheModal'
import type { CacheStats } from '../types'

function buildStats(overrides: Partial<CacheStats> = {}): CacheStats {
  return {
    enabled: true,
    semanticEnabled: true,
    totalExactHits: 100,
    totalSemanticHits: 50,
    totalMisses: 10,
    hitRate: 0.753,
    config: {
      ttlMinutes: 60,
      maxSize: 1000,
      similarityThreshold: 0.85,
      maxCandidates: 10,
      cacheableTemperature: 0.3,
    },
    ...overrides,
  }
}

describe('InvalidateCacheModal', () => {
  beforeEach(() => {
    i18n.addResourceBundle(
      'en',
      'translation',
      {
        'ragCachePage.invalidate.title': 'Invalidate All Cache',
        'ragCachePage.invalidate.currentHitRate': 'Current hit rate',
        'ragCachePage.invalidate.willReset': 'will reset to 0%',
        'ragCachePage.invalidate.totalCachedResponses': 'Recent cache hits',
        'ragCachePage.invalidate.expectedImpact': 'Expected impact',
        'ragCachePage.invalidate.expectedImpactDesc': 'Cost and latency increase.',
        'ragCachePage.invalidate.irreversible': 'This action cannot be undone',
        'ragCachePage.invalidate.tipTitle': 'Need to clear specific entries?',
        'ragCachePage.invalidate.tipDesc': 'Per-key API coming soon.',
        'ragCachePage.invalidate.cancel': 'Cancel',
        'ragCachePage.invalidate.execute': 'Invalidate All',
        'common.close': 'Close',
        'common.typeToConfirm': 'Type the following exactly to confirm:',
        'common.typeToConfirmHelp': 'This action is irreversible.',
      },
      true,
      true,
    )
  })

  it('does not render when isOpen is false', () => {
    render(
      <InvalidateCacheModal
        cacheStats={buildStats()}
        isOpen={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        isPending={false}
      />,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders modal with title and current hit rate', () => {
    render(
      <InvalidateCacheModal
        cacheStats={buildStats()}
        isOpen={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        isPending={false}
      />,
    )
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    // Title (in header and execute button). Header has id
    expect(screen.getByText('Current hit rate')).toBeInTheDocument()
    expect(screen.getByText('75.3%')).toBeInTheDocument()
    expect(screen.getByText('Recent cache hits')).toBeInTheDocument()
    // totalExactHits + totalSemanticHits = 100 + 50 = 150
    expect(screen.getByText('150')).toBeInTheDocument()
    expect(screen.getByText('This action cannot be undone')).toBeInTheDocument()
    expect(screen.getByText('Need to clear specific entries?')).toBeInTheDocument()
  })

  it('keeps execute button disabled until INVALIDATE is typed exactly', async () => {
    const onConfirm = vi.fn()
    const user = userEvent.setup()
    render(
      <InvalidateCacheModal
        cacheStats={buildStats()}
        isOpen={true}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
        isPending={false}
      />,
    )
    const executeBtn = screen.getByRole('button', { name: 'Invalidate All' })
    expect(executeBtn).toBeDisabled()

    const input = screen.getByRole('textbox')
    await user.type(input, 'invalidate') // wrong case
    expect(executeBtn).toBeDisabled()
    await user.clear(input)
    await user.type(input, 'INVALIDATE')
    expect(executeBtn).not.toBeDisabled()
  })

  it('calls onConfirm when execute button clicked after typing INVALIDATE', async () => {
    const onConfirm = vi.fn()
    const user = userEvent.setup()
    render(
      <InvalidateCacheModal
        cacheStats={buildStats()}
        isOpen={true}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
        isPending={false}
      />,
    )
    await user.type(screen.getByRole('textbox'), 'INVALIDATE')
    await user.click(screen.getByRole('button', { name: 'Invalidate All' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('calls onCancel when cancel button clicked', async () => {
    const onCancel = vi.fn()
    const user = userEvent.setup()
    render(
      <InvalidateCacheModal
        cacheStats={buildStats()}
        isOpen={true}
        onConfirm={vi.fn()}
        onCancel={onCancel}
        isPending={false}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('disables buttons while isPending', () => {
    render(
      <InvalidateCacheModal
        cacheStats={buildStats()}
        isOpen={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        isPending={true}
      />,
    )
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    // execute button contains spinner when pending, text is absent — find by role + disabled
    const buttons = screen.getAllByRole('button')
    const executeBtn = buttons.find(b => b.className.includes('btn-danger'))
    expect(executeBtn).toBeDisabled()
  })

  it('uses OperationButton (aria-busy + spinner) for the danger execute action while pending', () => {
    render(
      <InvalidateCacheModal
        cacheStats={buildStats()}
        isOpen={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        isPending={true}
      />,
    )
    const buttons = screen.getAllByRole('button')
    const executeBtn = buttons.find(b => b.className.includes('btn-danger'))
    expect(executeBtn).toBeDefined()
    // OperationButton contract: while operating, button is aria-busy, has the
    // btn--operating class, and renders a <LoadingSpinner /> child.
    expect(executeBtn).toHaveAttribute('aria-busy', 'true')
    expect(executeBtn).toHaveClass('btn--operating')
    expect(executeBtn?.querySelector('.spinner')).not.toBeNull()
  })

  it('handles null cacheStats gracefully', () => {
    render(
      <InvalidateCacheModal
        cacheStats={null}
        isOpen={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        isPending={false}
      />,
    )
    expect(screen.getByText('0.0%')).toBeInTheDocument()
    expect(screen.getByText('0')).toBeInTheDocument()
  })
})

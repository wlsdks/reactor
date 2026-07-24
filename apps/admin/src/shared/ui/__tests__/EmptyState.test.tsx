import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '../../../test/utils'
import { EmptyState } from '../EmptyState'

describe('EmptyState', () => {
  it('renders the message', () => {
    render(<EmptyState message="No items found" />)
    expect(screen.getByText('No items found')).toBeInTheDocument()
  })

  it('renders description when provided', () => {
    render(<EmptyState message="Empty" description="Try adding some items." />)
    expect(screen.getByText('Try adding some items.')).toBeInTheDocument()
  })

  it('does not render description when not provided', () => {
    const { container } = render(<EmptyState message="Empty" />)
    expect(container.querySelector('.empty-state-description')).not.toBeInTheDocument()
  })

  it('renders action button when actionLabel and onAction provided', () => {
    const onAction = vi.fn()
    render(<EmptyState message="Empty" actionLabel="Refresh" onAction={onAction} />)
    expect(screen.getByRole('button')).toBeInTheDocument()
  })

  it('calls onAction when button is clicked', () => {
    const onAction = vi.fn()
    render(<EmptyState message="Empty" actionLabel="Reload" onAction={onAction} />)
    fireEvent.click(screen.getByRole('button'))
    expect(onAction).toHaveBeenCalledOnce()
  })

  it('does not render button when only actionLabel provided without onAction', () => {
    render(<EmptyState message="Empty" actionLabel="Refresh" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('uses a quiet text-only default state without a decorative icon', () => {
    const { container } = render(<EmptyState message="Empty" />)
    expect(container.querySelector('svg')).not.toBeInTheDocument()
    expect(container.querySelector('.empty-state-icon')).not.toBeInTheDocument()
    expect(container.querySelector('.empty-state-title')).toHaveTextContent('Empty')
  })

  it('renders example panel when example is provided', () => {
    const { container } = render(
      <EmptyState message="Empty" example={<code>0 9 * * 1-5</code>} />
    )
    const panel = container.querySelector('.empty-state-example')
    expect(panel).toBeInTheDocument()
    expect(panel?.textContent).toContain('0 9 * * 1-5')
  })

  it('does not render example panel when example is not provided', () => {
    const { container } = render(<EmptyState message="Empty" />)
    expect(container.querySelector('.empty-state-example')).not.toBeInTheDocument()
  })

  it('renders helpHref as an external link with target=_blank', () => {
    render(<EmptyState message="Empty" helpHref="https://docs.example.com/empty" />)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', 'https://docs.example.com/empty')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('uses helpLabel override when provided', () => {
    render(
      <EmptyState
        message="Empty"
        helpHref="https://docs.example.com/empty"
        helpLabel="Custom help label"
      />
    )
    expect(screen.getByRole('link', { name: 'Custom help label' })).toBeInTheDocument()
  })

  it('does not render help link when helpHref is not provided', () => {
    render(<EmptyState message="Empty" helpLabel="Ignored" />)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  describe('filtered variant', () => {
    it('renders the filtered modifier class and plain-language context', () => {
      const { container } = render(<EmptyState filtered />)
      const root = container.querySelector('.empty-state')
      expect(root).toHaveClass('empty-state--filtered')
      expect(container.querySelector('svg')).not.toBeInTheDocument()
      expect(container.querySelector('.empty-state-context')).toBeInTheDocument()
    })

    it('falls back to filteredTitle when no message is provided', () => {
      render(<EmptyState filtered />)
      expect(screen.getByText('No items match the filters')).toBeInTheDocument()
      expect(screen.getByText('Adjust the filters or try again')).toBeInTheDocument()
    })

    it('respects an explicit message override on the filtered variant', () => {
      render(<EmptyState filtered message="Custom filtered title" />)
      expect(screen.getByText('Custom filtered title')).toBeInTheDocument()
    })

    it('renders the filterSummary chip when provided', () => {
      const { container } = render(
        <EmptyState filtered filterSummary="상태: 대기 중 · 평점: THUMBS_DOWN" />,
      )
      const chip = container.querySelector('.empty-state-filter-summary')
      expect(chip).toBeInTheDocument()
      expect(chip?.textContent).toBe('상태: 대기 중 · 평점: THUMBS_DOWN')
    })

    it('does not render the filterSummary chip when filtered is false', () => {
      const { container } = render(<EmptyState message="Empty" filterSummary="x" />)
      expect(container.querySelector('.empty-state-filter-summary')).not.toBeInTheDocument()
    })

    it('renders the clear filters button when onClearFilters is provided', () => {
      const onClearFilters = vi.fn()
      render(<EmptyState filtered onClearFilters={onClearFilters} />)
      const button = screen.getByRole('button', { name: 'Clear filters' })
      expect(button).toBeInTheDocument()
      fireEvent.click(button)
      expect(onClearFilters).toHaveBeenCalledOnce()
    })

    it('does not render the clear filters button when onClearFilters is omitted', () => {
      render(<EmptyState filtered />)
      expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument()
    })

    it('prioritises the explicit action over the clear filters button', () => {
      const onAction = vi.fn()
      const onClearFilters = vi.fn()
      render(
        <EmptyState
          filtered
          actionLabel="Refresh"
          onAction={onAction}
          onClearFilters={onClearFilters}
        />,
      )
      // Only the explicit action should render — the clear filters fallback is suppressed.
      expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument()
    })
  })

  describe('forbidden variant', () => {
    it('renders the forbidden modifier class and plain-language context', () => {
      const { container } = render(<EmptyState forbidden />)
      const root = container.querySelector('.empty-state')
      expect(root).toHaveClass('empty-state--forbidden')
      expect(container.querySelector('svg')).not.toBeInTheDocument()
      expect(container.querySelector('.empty-state-context--warning')).toBeInTheDocument()
    })

    it('falls back to forbiddenTitle and forbiddenHint when no overrides are provided', () => {
      render(<EmptyState forbidden />)
      expect(screen.getByText('접근 권한이 없어요')).toBeInTheDocument()
      expect(
        screen.getByText('이 영역은 ADMIN 또는 ADMIN_DEVELOPER 역할이 필요합니다'),
      ).toBeInTheDocument()
    })

    it('uses forbiddenContext as the description when provided', () => {
      render(
        <EmptyState
          forbidden
          forbiddenContext="이 페이지는 ADMIN 권한이 필요합니다"
        />,
      )
      expect(
        screen.getByText('이 페이지는 ADMIN 권한이 필요합니다'),
      ).toBeInTheDocument()
      // The default hint should be replaced, not appended.
      expect(
        screen.queryByText(
          '이 영역은 ADMIN 또는 ADMIN_DEVELOPER 역할이 필요합니다',
        ),
      ).not.toBeInTheDocument()
    })

    it('renders a default mailto contact link with "관리자 문의" label', () => {
      render(<EmptyState forbidden />)
      const link = screen.getByRole('link', { name: '관리자 문의' })
      expect(link).toHaveAttribute('href', 'mailto:admin@example.com')
      // mailto links must NOT carry target=_blank — opens the user's mail
      // client in-place rather than spawning a blank tab.
      expect(link).not.toHaveAttribute('target')
    })

    it('uses contactHref override and opens external links in a new tab', () => {
      render(
        <EmptyState
          forbidden
          contactHref="https://chat.example.com/admin"
        />,
      )
      const link = screen.getByRole('link', { name: '관리자 문의' })
      expect(link).toHaveAttribute('href', 'https://chat.example.com/admin')
      expect(link).toHaveAttribute('target', '_blank')
      expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    })

    it('prioritises an explicit action over the contact link', () => {
      const onAction = vi.fn()
      render(
        <EmptyState
          forbidden
          actionLabel="Open ticket"
          onAction={onAction}
          contactHref="mailto:admin@example.com"
        />,
      )
      expect(
        screen.getByRole('button', { name: 'Open ticket' }),
      ).toBeInTheDocument()
      expect(
        screen.queryByRole('link', { name: '관리자 문의' }),
      ).not.toBeInTheDocument()
    })

    it('forbidden takes precedence over filtered (no filter chip / clear-filters button)', () => {
      const onClearFilters = vi.fn()
      const { container } = render(
        <EmptyState
          forbidden
          filtered
          filterSummary="상태: 거부됨"
          onClearFilters={onClearFilters}
        />,
      )
      const root = container.querySelector('.empty-state')
      expect(root).toHaveClass('empty-state--forbidden')
      expect(root).not.toHaveClass('empty-state--filtered')
      expect(
        container.querySelector('.empty-state-filter-summary'),
      ).not.toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: 'Clear filters' }),
      ).not.toBeInTheDocument()
    })
  })
})

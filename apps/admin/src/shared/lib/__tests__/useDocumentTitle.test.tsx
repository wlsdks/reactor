import { describe, it, expect, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { useDocumentTitle } from '../useDocumentTitle'

function Probe({ title }: { title: string | undefined | null }) {
  useDocumentTitle(title)
  return null
}

describe('useDocumentTitle', () => {
  beforeEach(() => {
    document.title = 'Reactor Admin'
  })

  it('sets the document title with the page-specific prefix and brand suffix', () => {
    render(<Probe title="대시보드" />)
    expect(document.title).toBe('대시보드 · Reactor Admin')
  })

  it('falls back to the brand-only title when pageTitle is undefined', () => {
    render(<Probe title={undefined} />)
    expect(document.title).toBe('Reactor Admin')
  })

  it('falls back to the brand-only title when pageTitle is null', () => {
    render(<Probe title={null} />)
    expect(document.title).toBe('Reactor Admin')
  })

  it('treats whitespace-only titles as empty', () => {
    render(<Probe title="   " />)
    expect(document.title).toBe('Reactor Admin')
  })

  it('trims surrounding whitespace from a non-empty title', () => {
    render(<Probe title="  대시보드  " />)
    expect(document.title).toBe('대시보드 · Reactor Admin')
  })

  it('restores the previous title on unmount', () => {
    document.title = 'Previous'
    const { unmount } = render(<Probe title="대시보드" />)
    expect(document.title).toBe('대시보드 · Reactor Admin')
    unmount()
    expect(document.title).toBe('Previous')
  })

  it('updates the document title when the prop changes', () => {
    const { rerender } = render(<Probe title="A" />)
    expect(document.title).toBe('A · Reactor Admin')
    rerender(<Probe title="B" />)
    expect(document.title).toBe('B · Reactor Admin')
  })
})

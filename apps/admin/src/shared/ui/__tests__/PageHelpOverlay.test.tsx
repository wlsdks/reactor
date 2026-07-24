import { render, screen, fireEvent, act } from '../../../test/utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { PageHelpOverlay } from '../PageHelpOverlay'
import { usePageHelpStore } from '../../lib/usePageHelp'
import { i18n } from '../../../test/utils'

// Register a sample help array via the test i18n instance. The flat-string
// resource map in `test/utils` cannot express arrays, so we patch the
// resource bundle directly.
i18n.addResource('en', 'translation', 'testPage.help', [
  '이 페이지는 테스트용입니다.',
  '두 번째 줄.',
  '세 번째 줄.',
])

function pressKey(key: string, init: KeyboardEventInit = {}) {
  fireEvent.keyDown(document, { key, ...init })
}

function resetStore() {
  act(() => {
    usePageHelpStore.setState({ helpKey: null, isOpen: false })
  })
}

describe('PageHelpOverlay', () => {
  beforeEach(() => {
    resetStore()
    // Testing Library auto-unmounts between tests, but if the overlay was
    // open at that point its portal stays in document.body. Clear any
    // straggler nodes so .querySelectorAll counts are accurate.
    document.body.querySelectorAll('.page-help-overlay').forEach((n) => n.remove())
  })

  it('renders nothing when closed', () => {
    const { container } = render(<PageHelpOverlay />)
    expect(container.innerHTML).toBe('')
  })

  it('opens on "?" key', () => {
    render(<PageHelpOverlay />)
    pressKey('?')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('opens on "h" key', () => {
    render(<PageHelpOverlay />)
    pressKey('h')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('closes on Escape', () => {
    render(<PageHelpOverlay />)
    pressKey('?')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    pressKey('Escape')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('toggles closed on a second "?" key while open', () => {
    render(<PageHelpOverlay />)
    pressKey('?')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    pressKey('?')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('does not open while typing inside an <input>', () => {
    render(
      <>
        <input data-testid="text-input" />
        <PageHelpOverlay />
      </>,
    )
    const input = screen.getByTestId('text-input')
    input.focus()
    fireEvent.keyDown(input, { key: '?' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.keyDown(input, { key: 'h' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('does not open while typing inside a <textarea>', () => {
    render(
      <>
        <textarea data-testid="text-area" />
        <PageHelpOverlay />
      </>,
    )
    const area = screen.getByTestId('text-area')
    area.focus()
    fireEvent.keyDown(area, { key: '?' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders the static shortcut list', () => {
    render(<PageHelpOverlay />)
    pressKey('?')
    // Each shortcut renders its description. Match a few canonical labels.
    expect(screen.getByText('명령 팔레트 열기')).toBeInTheDocument()
    expect(screen.getByText('이 도움말 열기')).toBeInTheDocument()
    expect(screen.getByText('모달/오버레이 닫기')).toBeInTheDocument()
    expect(screen.getByText('포커스 이동')).toBeInTheDocument()
  })

  it('renders kbd chips for shortcut keys', () => {
    render(<PageHelpOverlay />)
    pressKey('?')
    // Overlay portals into document.body, so query from there.
    const kbds = document.querySelectorAll('.page-help__kbd')
    // 6 shortcut rows, 8 individual key chips: Cmd+K (2) + ? + Esc + ↑↓ (2) + Enter + Tab
    expect(kbds.length).toBeGreaterThanOrEqual(8)
  })

  it('renders empty state when no helpKey is registered', () => {
    render(<PageHelpOverlay />)
    pressKey('?')
    expect(screen.getByText('No help registered')).toBeInTheDocument()
  })

  it('renders dynamic page lines when helpKey is registered', () => {
    act(() => {
      usePageHelpStore.setState({ helpKey: 'testPage.help' })
    })
    render(<PageHelpOverlay />)
    pressKey('?')
    expect(screen.getByText('이 페이지는 테스트용입니다.')).toBeInTheDocument()
    expect(screen.getByText('두 번째 줄.')).toBeInTheDocument()
    expect(screen.getByText('세 번째 줄.')).toBeInTheDocument()
  })

  it('uses aria-labelledby pointing to the title', () => {
    render(<PageHelpOverlay />)
    pressKey('?')
    const dialog = screen.getByRole('dialog')
    const labelId = dialog.getAttribute('aria-labelledby')
    expect(labelId).toBeTruthy()
    const title = document.getElementById(labelId!)
    expect(title?.textContent).toBe('도움말 / 단축키')
  })

  it('closes when clicking the backdrop', () => {
    render(<PageHelpOverlay />)
    pressKey('?')
    const overlay = screen.getByTestId('page-help-overlay')
    fireEvent.click(overlay)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('does not open when another dialog is already mounted', () => {
    render(
      <>
        <div role="dialog" aria-modal="true">
          existing modal
        </div>
        <PageHelpOverlay />
      </>,
    )
    pressKey('?')
    // Only the pre-existing dialog should be present (no PageHelpOverlay).
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    expect(screen.queryByText('도움말 / 단축키')).not.toBeInTheDocument()
  })

  it('ignores ?/h with modifier keys', () => {
    render(<PageHelpOverlay />)
    pressKey('?', { metaKey: true })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    pressKey('h', { ctrlKey: true })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

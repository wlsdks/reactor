import './PageHelpOverlay.css'
import { useEffect, useId, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { useEscapeClose } from '../lib/useEscapeClose'
import { useFocusTrap } from '../lib/useFocusTrap'
import { usePageHelpStore } from '../lib/usePageHelp'
import { OverlayCloseButton } from './OverlayCloseButton'

interface ShortcutEntry {
  /** Stable React key + analytics identifier. */
  id: string
  /** Discrete kbd tokens rendered inside `<kbd>` chips. */
  keys: string[]
  /** Translated description shown to the right. */
  descriptionKey: string
}

const SHORTCUTS: ShortcutEntry[] = [
  { id: 'cmd-k', keys: ['Cmd', 'K'], descriptionKey: 'pageHelp.shortcuts.cmdK' },
  { id: 'help', keys: ['?'], descriptionKey: 'pageHelp.shortcuts.help' },
  { id: 'esc', keys: ['Esc'], descriptionKey: 'pageHelp.shortcuts.esc' },
  { id: 'arrows', keys: ['↑', '↓'], descriptionKey: 'pageHelp.shortcuts.arrows' },
  { id: 'enter', keys: ['Enter'], descriptionKey: 'pageHelp.shortcuts.enter' },
  { id: 'tab', keys: ['Tab'], descriptionKey: 'pageHelp.shortcuts.tab' },
]

/**
 * Returns true when the user is currently typing into an editable surface
 * (input, textarea, contentEditable). Used to suppress the global `?` / `h`
 * key listener so it does not steal keystrokes from forms.
 */
function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (target.isContentEditable) return true
  return false
}

/**
 * Renders the dynamic page-specific help section. The active page registers
 * an i18n key whose value is a string array (KO lines). Falls back to a
 * gentle empty-state message when no key is registered.
 */
function PageSection({ helpKey }: { helpKey: string | null }) {
  const { t } = useTranslation()

  if (!helpKey) {
    return <p className="page-help__empty">{t('pageHelp.noPageContent')}</p>
  }

  // i18next returns an array when the resource is a string[]. Tell TS so
  // we can render each line as its own list item.
  const lines = t(helpKey, { returnObjects: true, defaultValue: [] }) as unknown
  const items = Array.isArray(lines) ? (lines as string[]) : []

  if (items.length === 0) {
    return <p className="page-help__empty">{t('pageHelp.noPageContent')}</p>
  }

  return (
    <ul className="page-help__list">
      {items.map((line, index) => (
        <li key={`${helpKey}:${index}`} className="page-help__list-item">
          {line}
        </li>
      ))}
    </ul>
  )
}

/**
 * Page-level help overlay. Mounted once in `AdminLayout`, opened by the
 * global `?` / `h` keypress (when no input is focused) and closed via
 * Escape, the close button, or backdrop click. Uses
 * {@link useFocusTrap} so Tab cycles inside the dialog.
 */
export function PageHelpOverlay() {
  const { t } = useTranslation()
  const isOpen = usePageHelpStore((s) => s.isOpen)
  const open = usePageHelpStore((s) => s.open)
  const close = usePageHelpStore((s) => s.close)
  const helpKey = usePageHelpStore((s) => s.helpKey)
  const dialogRef = useRef<HTMLDivElement>(null)
  const titleId = useId()

  useEscapeClose(close, { active: isOpen })
  useFocusTrap(dialogRef, isOpen)

  // Global "?" / "h" listener — opens the overlay unless the user is
  // typing into a form control or already inside another overlay's input.
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key !== '?' && event.key !== 'h') return
      if (isEditableTarget(event.target)) return
      // Ignore when an overlay (modal/drawer/command palette) is already
      // listening for keystrokes — these wrappers always render a dialog
      // role.
      if (!isOpen && document.querySelector('[role="dialog"]')) return
      event.preventDefault()
      if (isOpen) close()
      else open()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, open, close])

  if (!isOpen) return null

  return createPortal(
    <div
      className="page-help-overlay"
      onClick={close}
      data-testid="page-help-overlay"
    >
      <div
        ref={dialogRef}
        className="page-help"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        <OverlayCloseButton onClick={close} label={t('common.aria.close')} />
        <h2 id={titleId} className="page-help__title">
          {t('pageHelp.title')}
        </h2>

        <section className="page-help__section">
          <h3 className="page-help__section-title">
            {t('pageHelp.sections.thisPage')}
          </h3>
          <PageSection helpKey={helpKey} />
        </section>

        <section className="page-help__section">
          <h3 className="page-help__section-title">
            {t('pageHelp.sections.shortcuts')}
          </h3>
          <ul className="page-help__shortcut-list">
            {SHORTCUTS.map((shortcut) => (
              <li key={shortcut.id} className="page-help__shortcut">
                <span className="page-help__shortcut-keys">
                  {shortcut.keys.map((key, index) => (
                    <kbd key={index} className="page-help__kbd">
                      {key}
                    </kbd>
                  ))}
                </span>
                <span className="page-help__shortcut-desc">
                  {t(shortcut.descriptionKey)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>,
    document.body,
  )
}

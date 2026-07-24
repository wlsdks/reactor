import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown } from 'lucide-react'
import { useSavedViewsStore } from '../store/savedViews.store'
import { useEscapeClose } from '../lib/useEscapeClose'
import { formatDateTimeCompact } from '../lib/formatters'
import { EmptyState } from './EmptyState'
import './SavedViewsControl.css'

interface SavedViewsControlProps {
  /**
   * Scope identifier — typically the same string passed to a DataTable's
   * `urlStateKey` so the dropdown only surfaces views relevant to this table.
   */
  scope: string
  /**
   * Snapshot of the current URL search params filtered down to this scope.
   * The "save current" action stores this object verbatim.
   */
  currentParams: Record<string, string>
  /**
   * Invoked with the saved params when the user picks a view. Callers should
   * merge these into their `useSearchParams` setter, replacing existing
   * scope-prefixed keys.
   */
  onApply: (params: Record<string, string>) => void
}

/**
 * Renders a "saved views" inline control: a dropdown of named filter
 * snapshots plus an inline "save current filter" form.
 *
 * - Click the trigger to open / close the panel.
 * - Each row shows the view name and creation timestamp; hitting "Apply"
 *   passes the stored params back to the caller, "Remove" deletes the row
 *   after confirmation.
 * - "Save current" reveals an input; Enter saves, Escape cancels.
 * - The whole panel closes on Escape and on outside clicks.
 *
 * Styling lives in `SavedViewsControl.css`. Only locale text is rendered —
 * never hard-coded user-facing strings.
 */
export function SavedViewsControl({ scope, currentParams, onApply }: SavedViewsControlProps) {
  const { t } = useTranslation()
  // Subscribe to the full views array so list() recomputes on every change.
  // Reading getState().list directly inside render avoids a stale closure
  // without forcing the caller to filter manually.
  const allViews = useSavedViewsStore((state) => state.views)
  const addView = useSavedViewsStore((state) => state.add)
  const removeView = useSavedViewsStore((state) => state.remove)
  const views = allViews.filter((v) => v.scope === scope)

  const [open, setOpen] = useState(false)
  const [showSaveForm, setShowSaveForm] = useState(false)
  const [name, setName] = useState('')
  const [pendingRemove, setPendingRemove] = useState<string | null>(null)

  const containerRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)

  // Outside click closes the panel — keeps the dropdown out of the way once
  // the user moves on to another control.
  useEffect(() => {
    if (!open) return
    function handleDocClick(event: MouseEvent) {
      const target = event.target as Node | null
      if (containerRef.current && target && !containerRef.current.contains(target)) {
        setOpen(false)
        setShowSaveForm(false)
        setPendingRemove(null)
      }
    }
    document.addEventListener('mousedown', handleDocClick)
    return () => document.removeEventListener('mousedown', handleDocClick)
  }, [open])

  // Auto-focus the name input when the inline save form appears so users can
  // start typing immediately without an extra click.
  useEffect(() => {
    if (showSaveForm) {
      inputRef.current?.focus()
    }
  }, [showSaveForm])

  useEscapeClose(
    () => {
      if (showSaveForm) {
        setShowSaveForm(false)
        setName('')
      } else {
        setOpen(false)
        setPendingRemove(null)
      }
    },
    { active: open },
  )

  function handleSave() {
    const trimmed = name.trim()
    if (!trimmed) return
    addView(scope, trimmed, currentParams)
    setName('')
    setShowSaveForm(false)
  }

  function handleSaveKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault()
      handleSave()
    } else if (event.key === 'Escape') {
      event.preventDefault()
      setShowSaveForm(false)
      setName('')
    }
  }

  function handleApply(params: Record<string, string>) {
    onApply(params)
    setOpen(false)
  }

  function handleRemove(id: string) {
    if (pendingRemove === id) {
      removeView(id)
      setPendingRemove(null)
    } else {
      setPendingRemove(id)
    }
  }

  const triggerText = views.length > 0
    ? t('common.savedViews.viewCount', { count: views.length })
    : t('common.savedViews.emptyTrigger')

  return (
    <div className="saved-views" ref={containerRef}>
      <span className="saved-views__label">
        {t('common.savedViews.dropdownLabel')}
      </span>
      <button
        type="button"
        className="btn btn-secondary btn-sm saved-views__trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span>{triggerText}</span>
        <ChevronDown
          className={`saved-views__chevron${open ? ' is-open' : ''}`}
          aria-hidden="true"
          size={14}
          strokeWidth={1.8}
        />
      </button>

      {open && (
        <div
          className="saved-views__panel"
          role="menu"
          aria-label={t('common.savedViews.dropdownLabel')}
        >
          <div className="saved-views__list">
            {views.length === 0 ? (
              <div className="saved-views__empty">
                {/* No saved views exist for this scope yet — plain empty state.
                 *  When the dropdown later grows a search filter, switch to the
                 *  `filtered` variant when that filter narrows views to 0. */}
                <EmptyState message={t('common.savedViews.emptyState')} />
              </div>
            ) : (
              views.map((view) => (
                <div className="saved-views__row" key={view.id} role="menuitem">
                  <div className="saved-views__row-main">
                    <span className="saved-views__row-name" title={view.name}>
                      {view.name}
                    </span>
                    <span className="saved-views__row-time">
                      {formatDateTimeCompact(view.createdAt)}
                    </span>
                  </div>
                  <div className="saved-views__row-actions">
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => handleApply(view.params)}
                    >
                      {t('common.savedViews.applyAction')}
                    </button>
                    <button
                      type="button"
                      className={`btn ${pendingRemove === view.id ? 'btn-danger' : 'btn-ghost'} btn-sm`}
                      onClick={() => handleRemove(view.id)}
                    >
                      {pendingRemove === view.id
                        ? t('common.savedViews.removeConfirm')
                        : t('common.savedViews.removeAction')}
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>

          <hr className="saved-views__divider" />

          {showSaveForm ? (
            <div className="saved-views__form">
              <input
                ref={inputRef}
                type="text"
                value={name}
                placeholder={t('common.savedViews.namePlaceholder')}
                aria-label={t('common.savedViews.namePlaceholder')}
                maxLength={80}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={handleSaveKeyDown}
              />
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={handleSave}
                disabled={!name.trim()}
              >
                {t('common.savedViews.saveAction')}
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setShowSaveForm(true)}
            >
              {t('common.savedViews.saveCurrent')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

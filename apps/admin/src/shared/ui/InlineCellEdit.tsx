import { useEffect, useId, useRef } from 'react'
import type { CSSProperties, KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useInlineEdit } from '../lib/useInlineEdit'
import type { FieldStatus } from './FieldStatusIndicator'
import { FieldStatusIndicator } from './FieldStatusIndicator'

export type InlineCellEditType = 'text' | 'number' | 'select'

export interface InlineCellEditOption<T> {
  value: T
  label: string
}

export interface InlineCellEditProps<T> {
  /** Current committed value. Used both for display and as the editor seed. */
  value: T
  /** Editor flavour. `text` uses an `<input type="text">`, `number` uses
   *  `<input type="number">`, `select` uses a `<select>` populated from `options`. */
  type?: InlineCellEditType
  /** Required when `type === 'select'`; ignored otherwise. */
  options?: InlineCellEditOption<T>[]
  /** Synchronous validator — see `useInlineEdit` docs. */
  validate?: (next: T) => string | null
  /** Persist handler — may be async. */
  onCommit: (next: T) => Promise<void> | void
  /** Wrapper class name for the cell shell. */
  className?: string
  /** Display formatter for the idle state. Falls back to `String(value)`. */
  format?: (value: T) => string
  /**
   * When true (default), clicks outside the editor commit the draft. Set to
   * false when the host wants outside-clicks to cancel instead — e.g. inside a
   * modal where draft loss should require an explicit confirmation.
   */
  commitOnBlur?: boolean
  /**
   * Optional accessible label for the editor. Defaults to a generic
   * "Edit value" string from i18n.
   */
  ariaLabel?: string
  /** Disable inline editing; the cell renders plain text. */
  disabled?: boolean
}

function defaultFormat<T>(value: T): string {
  if (value === null || value === undefined) return ''
  return String(value)
}

function statusToFieldStatus(status: 'idle' | 'editing' | 'submitting' | 'error'): FieldStatus {
  switch (status) {
    case 'submitting':
      return 'validating'
    case 'error':
      return 'error'
    case 'editing':
    case 'idle':
    default:
      return 'idle'
  }
}

/**
 * In-place editor for a single value displayed inside a `DataTable` cell or
 * any other read-only surface that should become editable on click. Supports
 * text / number / select editors, sync + async commits, validation, an inline
 * status indicator and an inline error message.
 *
 * Keyboard:
 *   - Enter inside the editor commits.
 *   - Escape cancels and restores the original value.
 *   - Tab / outside-click commits when `commitOnBlur` is true (default).
 */
export function InlineCellEdit<T>({
  value,
  type = 'text',
  options,
  validate,
  onCommit,
  className,
  format,
  commitOnBlur = true,
  ariaLabel,
  disabled,
}: InlineCellEditProps<T>) {
  const { t } = useTranslation()
  const editor = useInlineEdit<T>({
    initial: value,
    validate,
    onCommit,
  })
  const wrapperRef = useRef<HTMLSpanElement | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const selectRef = useRef<HTMLSelectElement | null>(null)
  const errorId = useId()

  // Outside-click → commit (or cancel when commitOnBlur is opted out). We
  // attach the listener only while editing to keep the global event surface
  // narrow and avoid leaking handlers for read-only cells.
  useEffect(() => {
    if (!editor.isEditing) return
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node | null
      if (!wrapperRef.current || !target) return
      if (wrapperRef.current.contains(target)) return
      if (commitOnBlur) {
        // Fire-and-forget — `commit` swallows its own errors via local state.
        void editor.commit()
      } else {
        editor.cancel()
      }
    }
    document.addEventListener('mousedown', handlePointerDown)
    return () => document.removeEventListener('mousedown', handlePointerDown)
  }, [commitOnBlur, editor])

  // Autofocus the active editor when entering edit mode. We use refs+effect
  // (not the `autoFocus` attribute) so the focus survives re-renders that
  // happen between `start()` firing and the editor mounting.
  useEffect(() => {
    if (!editor.isEditing) return
    if (type === 'select') {
      selectRef.current?.focus()
    } else {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [editor.isEditing, type])

  const startEditing = () => {
    if (disabled) return
    editor.start()
  }

  const handleEditorKeyDown = (event: KeyboardEvent<HTMLInputElement | HTMLSelectElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      void editor.commit()
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      editor.cancel()
    }
  }

  const fieldStatus = statusToFieldStatus(editor.status)
  const wrapperClass = ['inline-cell-edit', className].filter(Boolean).join(' ')

  if (!editor.isEditing) {
    const display = format ? format(value) : defaultFormat(value)
    const idleClasses = [wrapperClass, disabled ? 'inline-cell-edit--disabled' : 'inline-cell-edit--idle']
      .filter(Boolean)
      .join(' ')
    return (
      <span
        ref={wrapperRef}
        className={idleClasses}
        role={disabled ? undefined : 'button'}
        tabIndex={disabled ? undefined : 0}
        aria-label={
          disabled
            ? undefined
            : ariaLabel ?? t('common.inlineEdit.activate', { defaultValue: 'Edit value' })
        }
        onClick={(event) => {
          if (disabled) return
          // Stop the click from bubbling to the row's `onRowClick`. Otherwise
          // a single click on an editable cell would both start the editor
          // and open the row detail, which is jarring.
          event.stopPropagation()
          startEditing()
        }}
        onKeyDown={(event) => {
          if (disabled) return
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            event.stopPropagation()
            startEditing()
          }
        }}
      >
        {display}
      </span>
    )
  }

  const editorAriaLabel = ariaLabel ?? t('common.inlineEdit.editor', { defaultValue: 'Edit value' })
  const isSubmitting = editor.status === 'submitting'

  const editorWrapperStyle: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    flexWrap: 'wrap',
  }

  return (
    <span
      ref={wrapperRef}
      className={`${wrapperClass} inline-cell-edit--editing`}
      style={editorWrapperStyle}
      // Stop click bubbling so the host row's onRowClick does not fire when
      // the user clicks inside the editor surface.
      onClick={(event) => event.stopPropagation()}
    >
      {type === 'select' ? (
        <select
          ref={selectRef}
          className="inline-cell-edit__input"
          aria-label={editorAriaLabel}
          aria-invalid={editor.status === 'error'}
          aria-describedby={editor.error ? errorId : undefined}
          value={String(editor.value)}
          disabled={isSubmitting}
          onChange={(event) => {
            const raw = event.target.value
            const match = options?.find((opt) => String(opt.value) === raw)
            if (match) editor.setValue(match.value)
          }}
          onKeyDown={handleEditorKeyDown}
        >
          {options?.map((opt) => (
            <option key={String(opt.value)} value={String(opt.value)}>
              {opt.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          ref={inputRef}
          className="inline-cell-edit__input"
          type={type === 'number' ? 'number' : 'text'}
          aria-label={editorAriaLabel}
          aria-invalid={editor.status === 'error'}
          aria-describedby={editor.error ? errorId : undefined}
          value={editor.value === null || editor.value === undefined ? '' : String(editor.value)}
          disabled={isSubmitting}
          onChange={(event) => {
            const raw = event.target.value
            if (type === 'number') {
              if (raw === '') {
                editor.setValue('' as unknown as T)
              } else {
                const parsed = Number(raw)
                editor.setValue((Number.isFinite(parsed) ? parsed : raw) as unknown as T)
              }
            } else {
              editor.setValue(raw as unknown as T)
            }
          }}
          onKeyDown={handleEditorKeyDown}
        />
      )}
      <FieldStatusIndicator status={fieldStatus} />
      {editor.error && (
        <span
          id={errorId}
          role="alert"
          className="inline-cell-edit__error"
          style={{ color: 'var(--color-error)', fontSize: 'var(--text-xs)' }}
        >
          {editor.error}
        </span>
      )}
    </span>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  useForm,
  useFieldArray,
  FormProvider,
  useFormContext,
  type FieldArrayWithId,
} from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { DataTable, type Column } from '../../../shared/ui/DataTable'
import { DetailModal } from '../../../shared/ui/DetailModal'
import { OperationButton } from '../../../shared/ui/OperationButton'
import { Tabs } from '../../../shared/ui/Tabs'
import { useAnnouncer } from '../../../shared/ui/LiveAnnouncer'
import { useDebouncedValue } from '../../../shared/lib/useDebouncedValue'
import { useToastStore } from '../../../shared/store/toast.store'
import { getErrorMessage } from '../../../shared/lib'
import { queryKeys } from '../../../shared/lib/queryKeys'

import { seedPolicyDocuments } from '../api'
import { bulkSeedSchema, type BulkSeedFormValues } from '../schema'
import type { PolicySeedEntry } from '../types'

const MANUAL_CAP = 20

interface BulkSeedModalProps {
  open: boolean
  onClose: () => void
}

type ParsedResult =
  | { ok: true; entries: PolicySeedEntry[] }
  | { ok: false; reason: 'empty' }
  | { ok: false; reason: 'json'; error: string }
  | { ok: false; reason: 'schema'; error: string }

/**
 * Parse the paste-tab textarea into a list of `PolicySeedEntry`s validated
 * against the BE contract. Returns a discriminated result so the UI can
 * differentiate "not yet typed", "JSON parse error", and "schema violation".
 */
function parsePasteInput(raw: string): ParsedResult {
  if (!raw.trim()) return { ok: false, reason: 'empty' }

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch (err) {
    return {
      ok: false,
      reason: 'json',
      error: err instanceof Error ? err.message : 'JSON parse error',
    }
  }

  const result = bulkSeedSchema.safeParse({ entries: parsed })
  if (!result.success) {
    const firstIssue = result.error.issues[0]
    return {
      ok: false,
      reason: 'schema',
      error: firstIssue?.message ?? 'Invalid',
    }
  }
  return { ok: true, entries: result.data.entries }
}

/**
 * Bulk-seed policy documents into the RAG knowledge base.
 *
 * Two input modes:
 *  - Paste JSON (default) — primary fast path for >5 entries.
 *  - Manual fieldarray (cap 20) — fallback for ad-hoc edits.
 *
 * The BE swallows individual entry failures, so the only delta we can surface
 * is `keys.length` vs the requested entry count. Aggregate-success closes the
 * modal; partial-success keeps it open with a `role="status"` announcement so
 * the operator can investigate logs and retry.
 */
export function BulkSeedModal({ open, onClose }: BulkSeedModalProps) {
  const { t } = useTranslation()
  const announcer = useAnnouncer()
  const addToast = useToastStore((s) => s.addToast)
  const queryClient = useQueryClient()

  const [tab, setTab] = useState<'paste' | 'manual'>('paste')
  const [pasteRaw, setPasteRaw] = useState('')
  const debouncedRaw = useDebouncedValue(pasteRaw, 250)
  const parsed = useMemo(() => parsePasteInput(debouncedRaw), [debouncedRaw])

  const form = useForm<BulkSeedFormValues>({
    resolver: zodResolver(bulkSeedSchema),
    defaultValues: { entries: [] },
    mode: 'onBlur',
  })
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'entries',
  })

  // Focus management: when a new manual entry is appended, focus its key input.
  const lastAppendedIndexRef = useRef<number | null>(null)
  useEffect(() => {
    if (lastAppendedIndexRef.current === null) return
    const id = `bulk-seed-manual-${lastAppendedIndexRef.current}-key`
    const el = document.getElementById(id)
    el?.focus()
    lastAppendedIndexRef.current = null
  }, [fields.length])

  const mutation = useMutation({
    mutationFn: seedPolicyDocuments,
    onSuccess: (response, requestedEntries) => {
      const seeded = response.keys.length
      const total = requestedEntries.length
      // Even on partial success at least one entry was written, so refresh the
      // policy preview + the documents list so operators see updated counts
      // before retrying the failed remainder.
      if (seeded > 0) {
        queryClient.invalidateQueries({ queryKey: queryKeys.documents.policy() })
        queryClient.invalidateQueries({ queryKey: queryKeys.documents.list() })
      }
      if (seeded === total) {
        const message = t('documentsPage.bulkSeed.successAll', {
          seeded,
          chunks: response.chunkCount,
          ms: response.durationMs,
        })
        announcer.announce(message)
        addToast({ type: 'success', message })
        // Reset state so the next open is clean.
        setPasteRaw('')
        form.reset({ entries: [] })
        onClose()
      } else {
        const message = t('documentsPage.bulkSeed.successPartial', { seeded, total })
        announcer.announce(message)
        addToast({ type: 'error', message })
        // Keep modal open so operators can copy-edit and retry.
      }
    },
    onError: (err) => {
      addToast({ type: 'error', message: getErrorMessage(err) })
    },
  })

  /**
   * Submit dispatcher — paste-tab uses the parsed payload; manual-tab pulls
   * validated entries from the form (after a `trigger()` to surface errors).
   */
  const handleSubmit = async () => {
    if (mutation.isPending) return
    if (tab === 'paste') {
      if (!parsed.ok) return
      mutation.mutate(parsed.entries)
      return
    }
    const valid = await form.trigger()
    if (!valid) return
    const values = form.getValues().entries
    if (values.length === 0) return
    mutation.mutate(values)
  }

  const manualCount = fields.length
  const submitCount = tab === 'paste' && parsed.ok ? parsed.entries.length : manualCount
  const canSubmit =
    !mutation.isPending &&
    (tab === 'paste' ? parsed.ok : manualCount > 0 && manualCount <= MANUAL_CAP)

  const handleAddManual = () => {
    if (fields.length >= MANUAL_CAP) return
    const nextIndex = fields.length
    lastAppendedIndexRef.current = nextIndex
    append({ key: '', title: '', content: '' })
    announcer.announce(
      t('documentsPage.bulkSeed.entryAddedAnnouncement', {
        n: nextIndex + 1,
        total: MANUAL_CAP,
      }),
    )
  }

  const handleRemoveManual = (index: number) => {
    remove(index)
    announcer.announce(t('documentsPage.bulkSeed.entryRemovedAnnouncement'))
  }

  const handleClose = () => {
    if (mutation.isPending) return
    onClose()
  }

  if (!open) return null

  const previewColumns: Column<PolicySeedEntry>[] = [
    {
      key: 'key',
      header: t('documentsPage.bulkSeed.fields.key'),
      render: (row) => row.key,
    },
    {
      key: 'title',
      header: t('documentsPage.bulkSeed.fields.title'),
      render: (row) => row.title,
    },
    {
      key: 'category',
      header: t('documentsPage.bulkSeed.fields.category'),
      render: (row) => row.category ?? '-',
    },
  ]

  const submitLabel =
    submitCount > 0
      ? t('documentsPage.bulkSeed.submitLabel', { n: submitCount })
      : t('documentsPage.bulkSeed.submitLabelEmpty')

  return (
    <DetailModal
      open={open}
      onClose={handleClose}
      title={t('documentsPage.bulkSeed.modalTitle')}
      closeOnBackdrop={!mutation.isPending}
    >
      <p className="modal-description">{t('documentsPage.bulkSeed.intro')}</p>

      <Tabs
        ariaLabel={t('documentsPage.bulkSeed.modalTitle')}
        value={tab}
        onChange={(next) => setTab(next as 'paste' | 'manual')}
        tabs={[
          {
            value: 'paste',
            label: t('documentsPage.bulkSeed.pasteTab'),
            panel: (
              <PastePanel
                raw={pasteRaw}
                onChange={setPasteRaw}
                parsed={parsed}
                columns={previewColumns}
              />
            ),
          },
          {
            value: 'manual',
            label: t('documentsPage.bulkSeed.manualTab'),
            panel: (
              <FormProvider {...form}>
                <ManualPanel
                  fields={fields}
                  onAdd={handleAddManual}
                  onRemove={handleRemoveManual}
                />
              </FormProvider>
            ),
          },
        ]}
      />

      {mutation.isPending && (
        <p role="status" className="bulk-seed-progress">
          {t('documentsPage.bulkSeed.progressMessage', { n: submitCount })}
        </p>
      )}

      <div
        className="modal-actions"
        style={{
          display: 'flex',
          gap: 'var(--space-2)',
          marginTop: 'var(--space-3)',
          justifyContent: 'flex-end',
        }}
      >
        <button
          type="button"
          className="btn btn-ghost"
          onClick={handleClose}
          disabled={mutation.isPending}
        >
          {t('documentsPage.bulkSeed.cancelLabel')}
        </button>
        <OperationButton
          variant="primary"
          isOperating={mutation.isPending}
          disabled={!canSubmit}
          onClick={handleSubmit}
        >
          {submitLabel}
        </OperationButton>
      </div>
    </DetailModal>
  )
}

interface PastePanelProps {
  raw: string
  onChange: (next: string) => void
  parsed: ParsedResult
  columns: Column<PolicySeedEntry>[]
}

function PastePanel({ raw, onChange, parsed, columns }: PastePanelProps) {
  const { t } = useTranslation()
  const errorId = 'bulk-seed-paste-error'
  const showError = !parsed.ok && parsed.reason !== 'empty' && raw.length > 0
  const errorMessage =
    !parsed.ok && (parsed.reason === 'json' || parsed.reason === 'schema')
      ? t('documentsPage.bulkSeed.previewInvalid', { message: parsed.error })
      : null

  return (
    <div className="bulk-seed-paste-panel">
      <label htmlFor="bulk-seed-paste">{t('documentsPage.bulkSeed.pasteLabel')}</label>
      <textarea
        id="bulk-seed-paste"
        rows={10}
        value={raw}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t('documentsPage.bulkSeed.pastePlaceholder')}
        aria-invalid={showError}
        aria-describedby={showError ? errorId : undefined}
        spellCheck={false}
        className="bulk-seed-textarea"
      />
      {showError && errorMessage && (
        <div id={errorId} role="alert" className="bulk-seed-error">
          {errorMessage}
        </div>
      )}

      <h3 className="bulk-seed-preview-heading">
        {t('documentsPage.bulkSeed.previewTitle')}
      </h3>
      {parsed.ok ? (
        <DataTable columns={columns} data={parsed.entries} keyFn={(row) => row.key} />
      ) : (
        <p className="bulk-seed-preview-empty">
          {t('documentsPage.bulkSeed.previewEmpty')}
        </p>
      )}
    </div>
  )
}

interface ManualPanelProps {
  fields: FieldArrayWithId<BulkSeedFormValues, 'entries', 'id'>[]
  onAdd: () => void
  onRemove: (index: number) => void
}

function ManualPanel({ fields, onAdd, onRemove }: ManualPanelProps) {
  const { t } = useTranslation()
  const { register, formState } = useFormContext<BulkSeedFormValues>()
  const reachedCap = fields.length >= MANUAL_CAP

  return (
    <div className="bulk-seed-manual-panel">
      {reachedCap && (
        <p role="alert" className="bulk-seed-error">
          {t('documentsPage.bulkSeed.error.manualMaxEntries')}
        </p>
      )}

      {fields.length === 0 ? (
        <p className="bulk-seed-manual-empty">
          {t('documentsPage.bulkSeed.manualEmpty')}
        </p>
      ) : (
        fields.map((field, index) => {
          const keyId = `bulk-seed-manual-${index}-key`
          const titleId = `bulk-seed-manual-${index}-title`
          const contentId = `bulk-seed-manual-${index}-content`
          const fieldErrors = formState.errors.entries?.[index]
          return (
            <fieldset
              key={field.id}
              aria-label={t('documentsPage.bulkSeed.entryGroupAriaLabel', { n: index + 1 })}
              className="bulk-seed-fieldset"
            >
              <legend>
                {t('documentsPage.bulkSeed.entryLegend', { n: index + 1 })}
              </legend>

              <label htmlFor={keyId}>
                {t('documentsPage.bulkSeed.fields.key')}
              </label>
              <input
                id={keyId}
                {...register(`entries.${index}.key` as const)}
                aria-invalid={!!fieldErrors?.key}
                aria-describedby={fieldErrors?.key ? `${keyId}-error` : undefined}
              />
              {fieldErrors?.key?.message && (
                <div id={`${keyId}-error`} role="alert" className="bulk-seed-error">
                  {String(fieldErrors.key.message)}
                </div>
              )}

              <label htmlFor={titleId}>
                {t('documentsPage.bulkSeed.fields.title')}
              </label>
              <input
                id={titleId}
                {...register(`entries.${index}.title` as const)}
                aria-invalid={!!fieldErrors?.title}
                aria-describedby={fieldErrors?.title ? `${titleId}-error` : undefined}
              />
              {fieldErrors?.title?.message && (
                <div id={`${titleId}-error`} role="alert" className="bulk-seed-error">
                  {String(fieldErrors.title.message)}
                </div>
              )}

              <label htmlFor={contentId}>
                {t('documentsPage.bulkSeed.fields.content')}
              </label>
              <textarea
                id={contentId}
                rows={4}
                {...register(`entries.${index}.content` as const)}
                aria-invalid={!!fieldErrors?.content}
                aria-describedby={fieldErrors?.content ? `${contentId}-error` : undefined}
              />
              {fieldErrors?.content?.message && (
                <div id={`${contentId}-error`} role="alert" className="bulk-seed-error">
                  {String(fieldErrors.content.message)}
                </div>
              )}

              <button
                type="button"
                aria-label={t('documentsPage.bulkSeed.removeEntry', { n: index + 1 })}
                onClick={() => onRemove(index)}
                className="btn btn-ghost btn-sm bulk-seed-remove"
              >
                ✕
              </button>
            </fieldset>
          )
        })
      )}

      <button
        type="button"
        onClick={onAdd}
        disabled={reachedCap}
        className="btn btn-secondary"
      >
        {t('documentsPage.bulkSeed.addManualButton')}
      </button>
    </div>
  )
}

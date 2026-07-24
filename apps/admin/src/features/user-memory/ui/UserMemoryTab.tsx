import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { useToastStore } from '../../../shared/store/toast.store'
import { ConfirmDialog, EmptyState, SkeletonCard, SkeletonText } from '../../../shared/ui'
import { getUserMemory, updateUserFacts, updateUserPreferences, deleteUserMemory } from '../api'

interface UserMemoryTabProps {
  userId: string
}

function KeyValueSection({
  title,
  entries,
  isEditing,
  editValues,
  onEditValuesChange,
  onEdit,
  onSave,
  onCancel,
  isSaving,
  noEntriesLabel,
  keyLabel,
  valueLabel,
}: {
  title: string
  entries: Record<string, string>
  isEditing: boolean
  editValues: Record<string, string>
  onEditValuesChange: (values: Record<string, string>) => void
  onEdit: () => void
  onSave: () => void
  onCancel: () => void
  isSaving: boolean
  noEntriesLabel: string
  keyLabel: string
  valueLabel: string
}) {
  const { t } = useTranslation()
  const keys = Object.keys(entries)

  return (
    <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-3)' }}>
        <h3 style={{ margin: 0, color: 'var(--text-primary)', fontSize: 'var(--text-lg)', fontWeight: 'var(--font-weight-strong)' }}>{title}</h3>
        {keys.length > 0 && !isEditing && (
          <button className="btn btn-secondary" onClick={onEdit}>
            {t('common.edit')}
          </button>
        )}
        {isEditing && (
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <button className="btn btn-secondary" onClick={onCancel} disabled={isSaving}>
              {t('common.cancel')}
            </button>
            <button className="btn btn-primary" onClick={onSave} disabled={isSaving}>
              {isSaving ? t('common.saving') : t('common.save')}
            </button>
          </div>
        )}
      </div>

      {keys.length === 0 ? (
        <p style={{ color: 'var(--text-muted)', margin: 0 }}>{noEntriesLabel}</p>
      ) : (
        <table className="data-table" style={{ width: '100%' }}>
          <thead>
            <tr>
              <th scope="col" style={{ width: '30%', textTransform: 'uppercase' }}>{keyLabel}</th>
              <th scope="col" style={{ textTransform: 'uppercase' }}>{valueLabel}</th>
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => (
              <tr key={key}>
                <td>
                  <code style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                    {key}
                  </code>
                </td>
                <td>
                  {isEditing ? (
                    <input
                      type="text"
                      className="form-input"
                      value={editValues[key] ?? ''}
                      onChange={(e) =>
                        onEditValuesChange({ ...editValues, [key]: e.target.value })
                      }
                      style={{ width: '100%' }}
                    />
                  ) : (
                    <span style={{ color: 'var(--text-primary)' }}>{entries[key]}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export function UserMemoryTab({ userId }: UserMemoryTabProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)

  const [editingFacts, setEditingFacts] = useState(false)
  const [editingPrefs, setEditingPrefs] = useState(false)
  const [factsValues, setFactsValues] = useState<Record<string, string>>({})
  const [prefsValues, setPrefsValues] = useState<Record<string, string>>({})
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.userMemory.detail(userId),
    queryFn: () => getUserMemory(userId),
  })

  const factsMutation = useMutation({
    mutationFn: (facts: Record<string, string>) => updateUserFacts(userId, facts),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.userMemory.detail(userId) })
      addToast({ type: 'success', message: t('userMemoryTab.factsSaved') })
      setEditingFacts(false)
    },
  })

  const prefsMutation = useMutation({
    mutationFn: (prefs: Record<string, string>) => updateUserPreferences(userId, prefs),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.userMemory.detail(userId) })
      addToast({ type: 'success', message: t('userMemoryTab.preferencesSaved') })
      setEditingPrefs(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteUserMemory(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.userMemory.all() })
      addToast({ type: 'success', message: t('userMemoryTab.memoryDeleted') })
      setShowDeleteConfirm(false)
    },
  })

  if (isLoading) {
    // Mirror the two stacked KeyValueSection cards (Facts + Preferences) with
    // a header line + body block so the panel doesn't snap when data lands.
    return (
      <div>
        <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
          <SkeletonText width="40%" />
          <div style={{ marginTop: 'var(--space-3)' }}>
            <SkeletonCard height={120} />
          </div>
        </div>
        <div className="card">
          <SkeletonText width="40%" />
          <div style={{ marginTop: 'var(--space-3)' }}>
            <SkeletonCard height={120} />
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card" role="alert" style={{ color: 'var(--red)' }}>
        {getErrorMessage(error)}
      </div>
    )
  }

  if (!data || (Object.keys(data.facts).length === 0 && Object.keys(data.preferences).length === 0)) {
    return <EmptyState message={t('userMemoryTab.noMemory')} />
  }

  return (
    <div>
      <KeyValueSection
        title={t('userMemoryTab.facts')}
        entries={data.facts}
        isEditing={editingFacts}
        editValues={factsValues}
        onEditValuesChange={setFactsValues}
        onEdit={() => {
          setFactsValues({ ...data.facts })
          setEditingFacts(true)
        }}
        onSave={() => factsMutation.mutate(factsValues)}
        onCancel={() => setEditingFacts(false)}
        isSaving={factsMutation.isPending}
        noEntriesLabel={t('userMemoryTab.noEntries')}
        keyLabel={t('userMemoryTab.key')}
        valueLabel={t('userMemoryTab.value')}
      />

      <KeyValueSection
        title={t('userMemoryTab.preferences')}
        entries={data.preferences}
        isEditing={editingPrefs}
        editValues={prefsValues}
        onEditValuesChange={setPrefsValues}
        onEdit={() => {
          setPrefsValues({ ...data.preferences })
          setEditingPrefs(true)
        }}
        onSave={() => prefsMutation.mutate(prefsValues)}
        onCancel={() => setEditingPrefs(false)}
        isSaving={prefsMutation.isPending}
        noEntriesLabel={t('userMemoryTab.noEntries')}
        keyLabel={t('userMemoryTab.key')}
        valueLabel={t('userMemoryTab.value')}
      />

      <div className="card" style={{ borderColor: 'var(--red)', borderWidth: 1, borderStyle: 'solid' }}>
        <h3 style={{ margin: '0 0 var(--space-2)', color: 'var(--red)', fontSize: 'var(--text-lg)', fontWeight: 'var(--font-weight-strong)' }}>
          {t('userMemoryTab.dangerZone')}
        </h3>
        <p style={{ color: 'var(--text-muted)', marginBottom: 'var(--space-3)' }}>
          {t('userMemoryTab.deleteWarning')}
        </p>
        <button
          className="btn btn-danger"
          onClick={() => setShowDeleteConfirm(true)}
          disabled={deleteMutation.isPending}
        >
          {t('userMemoryTab.deleteAll')}
        </button>
      </div>

      {showDeleteConfirm && (
        <ConfirmDialog
          title={t('userMemoryTab.confirmDeleteTitle')}
          message={t('userMemoryTab.confirmDeleteMsg')}
          danger
          onConfirm={() => deleteMutation.mutate()}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      )}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { DetailModal, SectionErrorBoundary } from '../../../shared/ui'
import { useToastStore } from '../../../shared/store/toast.store'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { mcpServerSchema, type McpServerFormValues } from '../schema'
import { registerMcpServer, updateMcpServer } from '../api'
import { useTagStore } from '../tags'
import {
  buildMcpServerDraft,
  formatDraftConfig,
  KNOWN_MCP_SERVER_PRESETS,
  type KnownMcpServerKind,
} from '../presets'
import { RegisterServerStep1 } from './RegisterServerStep1'
import { RegisterServerStep2 } from './RegisterServerStep2'

interface EditServerData {
  name: string
  transportType: string
  config: Record<string, unknown>
}

interface RegisterServerModalProps {
  open: boolean
  onClose: () => void
  editServer?: EditServerData
}

const CREATE_DEFAULTS: McpServerFormValues = {
  name: '',
  transportType: 'STREAMABLE_HTTP',
  configRaw: '{}',
  tags: [],
}

function editServerToFormValues(server: EditServerData, tags: string[]): McpServerFormValues {
  return {
    name: server.name,
    transportType: server.transportType as McpServerFormValues['transportType'],
    configRaw: formatDraftConfig(server.config),
    tags,
  }
}

export function RegisterServerModal({ open, onClose, editServer }: RegisterServerModalProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const tagStore = useTagStore()

  const isEditMode = !!editServer

  // Wizard step state — reset when modal identity changes
  // Track the previous editServer to detect mode transitions (React-approved derived state pattern)
  const [step, setStep] = useState<1 | 2>(isEditMode ? 2 : 1)
  const [prevEditServer, setPrevEditServer] = useState(editServer)
  if (editServer !== prevEditServer) {
    setPrevEditServer(editServer)
    setStep(editServer ? 2 : 1)
  }

  // Tag input state
  const [tagInput, setTagInput] = useState('')

  const allUniqueTags = tagStore.getAllUniqueTags()

  const {
    register,
    handleSubmit,
    setError,
    setValue,
    control,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<McpServerFormValues>({
    resolver: zodResolver(mcpServerSchema),
    mode: 'onSubmit',
    defaultValues: CREATE_DEFAULTS,
  })

  const tags = useWatch({ control, name: 'tags' }) ?? []

  // Reset form when modal opens or editServer changes
  useEffect(() => {
    if (!open) return

    if (isEditMode && editServer) {
      const existingTags = tagStore.tags[editServer.name] ?? []
      reset(editServerToFormValues(editServer, existingTags))
    } else {
      reset(CREATE_DEFAULTS)
    }
  }, [open, editServer, isEditMode, reset, tagStore.tags])

  // Mutation for register/update
  const mutation = useMutation({
    mutationFn: async (values: McpServerFormValues) => {
      const config = JSON.parse(values.configRaw) as Record<string, unknown>
      if (isEditMode) {
        return updateMcpServer(values.name, {
          transportType: values.transportType,
          config,
        })
      }
      return registerMcpServer({
        name: values.name,
        transportType: values.transportType,
        config,
      })
    },
    onSuccess: (_data, values) => {
      tagStore.setTags(values.name, values.tags)
      void queryClient.invalidateQueries({ queryKey: queryKeys.mcpServers.list() })
      useToastStore.getState().addToast({ type: 'success', message: isEditMode ? t('mcpServers.toast.updated') : t('mcpServers.toast.registered') })
      handleClose()
    },
    onError: (err: Error) => {
      setError('root', { message: err.message })
    },
  })

  function applyPreset(kind: KnownMcpServerKind) {
    const draft = buildMcpServerDraft(kind)
    setValue('name', draft.name)
    setValue('transportType', draft.transportType as McpServerFormValues['transportType'])
    setValue('configRaw', formatDraftConfig(draft.config))
  }

  function onSubmit(values: McpServerFormValues) {
    mutation.mutate(values)
  }

  function handleClose() {
    setTagInput('')
    setStep(1)
    onClose()
  }

  // Determine which preset matches the current server name (for edit mode highlighting)
  const matchedPreset: KnownMcpServerKind | null = isEditMode
    ? KNOWN_MCP_SERVER_PRESETS.find((kind) => {
        const draft = buildMcpServerDraft(kind)
        return draft.name && draft.name === editServer?.name
      }) ?? null
    : null

  const title = isEditMode
    ? t('mcpServers.register.titleEdit')
    : t('mcpServers.register.titleCreate')

  const suggestedTags = allUniqueTags.filter((tag) => !tags.includes(tag))

  return (
    <DetailModal open={open} title={title} onClose={handleClose}>
      <SectionErrorBoundary name="register-server-modal">
      {/* Wizard step indicator */}
      <div className="wizard-steps">
        <div className={`wizard-step ${step >= 1 ? 'active' : ''}`}>
          <span className="wizard-step-num">1</span>
          <span className="wizard-step-label">{t('mcpServers.register.step1')}</span>
        </div>
        <div className="wizard-step-line" />
        <div className={`wizard-step ${step >= 2 ? 'active' : ''}`}>
          <span className="wizard-step-num">2</span>
          <span className="wizard-step-label">{t('mcpServers.register.step2')}</span>
        </div>
      </div>

      {errors.root && (
        <div className="alert alert-error" role="alert" style={{ marginBottom: 'var(--space-4)' }}>
          {errors.root.message}
        </div>
      )}

      <form onSubmit={(event) => void handleSubmit(onSubmit)(event)} noValidate>
        {step === 1 && (
          <RegisterServerStep1
            register={register}
            errors={errors}
            control={control}
            isEditMode={isEditMode}
            matchedPreset={matchedPreset}
            onApplyPreset={applyPreset}
            onNext={() => setStep(2)}
            onCancel={handleClose}
          />
        )}

        {step === 2 && (
          <RegisterServerStep2
            register={register}
            errors={errors}
            setValue={setValue}
            isEditMode={isEditMode}
            matchedPreset={matchedPreset}
            tags={tags}
            suggestedTags={suggestedTags}
            tagInput={tagInput}
            setTagInput={setTagInput}
            getTagColor={tagStore.getTagColor}
            isSubmitting={isSubmitting}
            isMutating={mutation.isPending}
            onBack={() => setStep(1)}
            onCancel={handleClose}
          />
        )}
      </form>
      </SectionErrorBoundary>
    </DetailModal>
  )
}

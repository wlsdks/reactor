import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { queryKeys } from '../../shared/lib/queryKeys'
import { useToastStore } from '../../shared/store/toast.store'
import { getErrorMessage } from '../../shared/lib/getErrorMessage'
import { ApiError } from '../../shared/api/errors'
import { useRoleVisibility } from '../workspace/RoleVisibilityProvider'
import * as api from './api'
import type {
  ModelPricingRequest,
  PlatformUserRole,
  TenantPlan,
} from './types'

// ── Types ──────────────────────────────────────────────────────────────────

export interface TenantForm {
  name: string
  slug: string
  plan: TenantPlan
}

export interface PricingForm {
  provider: string
  model: string
  promptPricePer1m: string
  completionPricePer1m: string
  cachedInputPricePer1m: string
  reasoningPricePer1m: string
  batchPromptPricePer1m: string
  batchCompletionPricePer1m: string
}

export interface AlertRuleForm {
  name: string
  description: string
  metric: string
  threshold: string
  windowMinutes: string
  type: 'STATIC_THRESHOLD' | 'BASELINE_ANOMALY' | 'ERROR_BUDGET_BURN_RATE'
  severity: 'INFO' | 'WARNING' | 'CRITICAL'
  tenantId: string
  enabled: boolean
  platformOnly: boolean
}

export type PlatformTab = 'admin' | 'tenant'

export interface PlatformAdminDataScope {
  tenants?: boolean
  pricing?: boolean
  alerts?: boolean
  users?: boolean
}

// ── Defaults ───────────────────────────────────────────────────────────────

const defaultTenantForm: TenantForm = { name: '', slug: '', plan: 'FREE' }
const defaultPricingForm: PricingForm = {
  provider: 'openai',
  model: 'gpt-4o-mini',
  promptPricePer1m: '0',
  completionPricePer1m: '0',
  cachedInputPricePer1m: '0',
  reasoningPricePer1m: '0',
  batchPromptPricePer1m: '0',
  batchCompletionPricePer1m: '0',
}
const defaultRuleForm: AlertRuleForm = {
  name: '',
  description: '',
  metric: 'error_rate',
  threshold: '0.1',
  windowMinutes: '15',
  type: 'STATIC_THRESHOLD',
  severity: 'WARNING',
  tenantId: '',
  enabled: true,
  platformOnly: true,
}

// ── Helpers ────────────────────────────────────────────────────────────────

function parseInitialTab(params: URLSearchParams, isManagerMode: boolean): PlatformTab {
  if (isManagerMode) return 'tenant'
  const raw = params.get('tab')
  if (raw === 'tenant') return 'tenant'
  return 'admin'
}

function parseFloatSafe(value: string): number {
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function parseIntSafe(value: string): number {
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) ? parsed : 0
}

export function buildModelPricingRequest(form: PricingForm, effectiveFrom = new Date().toISOString()): ModelPricingRequest {
  const provider = form.provider.trim()
  const model = form.model.trim()
  return {
    id: `pricing:${provider.toLowerCase()}:${model.toLowerCase()}`,
    provider,
    model,
    promptPricePer1m: parseFloatSafe(form.promptPricePer1m),
    completionPricePer1m: parseFloatSafe(form.completionPricePer1m),
    cachedInputPricePer1m: parseFloatSafe(form.cachedInputPricePer1m),
    reasoningPricePer1m: parseFloatSafe(form.reasoningPricePer1m),
    batchPromptPricePer1m: parseFloatSafe(form.batchPromptPricePer1m),
    batchCompletionPricePer1m: parseFloatSafe(form.batchCompletionPricePer1m),
    effectiveFrom,
    effectiveTo: null,
  }
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function usePlatformAdminData(
  initialSelectedTenantId?: string,
  scope: PlatformAdminDataScope = { tenants: true, pricing: true, alerts: true, users: true },
) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { effectiveRole } = useRoleVisibility()
  const isManagerMode = effectiveRole === 'ADMIN_MANAGER'
  const [searchParams] = useSearchParams()
  const [activeTab, setActiveTab] = useState<PlatformTab>(() => parseInitialTab(searchParams, isManagerMode))

  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(initialSelectedTenantId ?? null)
  const [userLookupEmail, setUserLookupEmail] = useState('')
  const [selectedUserEmail, setSelectedUserEmail] = useState<string | null>(null)
  const [selectedUserRole, setSelectedUserRole] = useState<PlatformUserRole>('USER')
  const [updatingUserRole, setUpdatingUserRole] = useState(false)

  const [tenantForm, setTenantForm] = useState<TenantForm>(defaultTenantForm)
  const [pricingForm, setPricingForm] = useState<PricingForm>(defaultPricingForm)
  const [ruleForm, setRuleForm] = useState<AlertRuleForm>(defaultRuleForm)
  const [saving, setSaving] = useState(false)

  // ── Queries ──────────────────────────────────────────────────

  const tenantsQuery = useQuery({
    queryKey: queryKeys.platformAdmin.tenants(),
    queryFn: api.listTenants,
    enabled: scope.tenants === true && !isManagerMode,
  })

  const pricingQuery = useQuery({
    queryKey: queryKeys.platformAdmin.pricing(),
    queryFn: api.listPricing,
    enabled: scope.pricing === true && !isManagerMode,
  })

  const alertRulesQuery = useQuery({
    queryKey: queryKeys.platformAdmin.alertRules(),
    queryFn: api.listAlertRules,
    enabled: scope.alerts === true && !isManagerMode,
  })

  const activeAlertsQuery = useQuery({
    queryKey: queryKeys.platformAdmin.activeAlerts(),
    queryFn: api.listActiveAlerts,
    enabled: scope.alerts === true && !isManagerMode,
  })

  const selectedTenantQuery = useQuery({
    queryKey: queryKeys.platformAdmin.tenant(selectedTenantId ?? ''),
    queryFn: () => api.getTenant(selectedTenantId!),
    enabled: scope.tenants === true && !!selectedTenantId,
  })

  const selectedUserQuery = useQuery({
    queryKey: queryKeys.platformAdmin.userByEmail(selectedUserEmail),
    queryFn: () => api.getUserByEmail(selectedUserEmail!),
    enabled: scope.users === true && !!selectedUserEmail,
    retry: (failureCount, queryError) => {
      if (queryError instanceof ApiError && queryError.status >= 400 && queryError.status < 500) return false
      return failureCount < 2
    },
  })

  const tenants = tenantsQuery.data ?? []
  const pricing = pricingQuery.data ?? []
  const alertRules = alertRulesQuery.data ?? []
  const activeAlerts = activeAlertsQuery.data ?? []
  const selectedTenant = selectedTenantQuery.data ?? null
  const selectedUser = selectedUserQuery.data ?? null
  const isLoading = tenantsQuery.isLoading

  // ── Mutations ────────────────────────────────────────────────

  const createTenantMutation = useMutation({
    mutationFn: api.createTenant,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.platformAdmin.tenants() })
      setTenantForm(defaultTenantForm)
    },
    onError: (err: Error) => setError(err.message),
    onSettled: () => setSaving(false),
  })

  const suspendMutation = useMutation({
    mutationFn: api.suspendTenant,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.platformAdmin.all() }),
    onError: (err: Error) => setError(err.message),
  })

  const activateMutation = useMutation({
    mutationFn: api.activateTenant,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.platformAdmin.all() }),
    onError: (err: Error) => setError(err.message),
  })

  const pricingMutation = useMutation({
    mutationFn: api.upsertPricing,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.platformAdmin.pricing() })
      setPricingForm(defaultPricingForm)
    },
    onError: (err: Error) => setError(err.message),
    onSettled: () => setSaving(false),
  })

  const alertRuleMutation = useMutation({
    mutationFn: api.saveAlertRule,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.platformAdmin.alertRules() })
      setRuleForm(defaultRuleForm)
    },
    onError: (err: Error) => setError(err.message),
    onSettled: () => setSaving(false),
  })

  const deleteAlertMutation = useMutation({
    mutationFn: api.deleteAlertRule,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.platformAdmin.alertRules() }),
    onError: (err: Error) => setError(err.message),
  })

  const resolveAlertMutation = useMutation({
    mutationFn: api.resolveAlert,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.platformAdmin.activeAlerts() }),
    onError: (err: Error) => setError(err.message),
  })

  // ── Handlers ─────────────────────────────────────────────────

  function handleCreateTenant() {
    if (!tenantForm.name.trim() || !tenantForm.slug.trim()) {
      setError(t('platformAdminPage.validation.nameAndSlugRequired'))
      return
    }
    setSaving(true)
    setError(null)
    createTenantMutation.mutate(tenantForm)
  }

  function handleUpsertPricing() {
    if (!pricingForm.provider.trim() || !pricingForm.model.trim()) {
      setError(t('platformAdminPage.validation.providerAndModelRequired'))
      return
    }
    setSaving(true)
    setError(null)
    pricingMutation.mutate(buildModelPricingRequest(pricingForm))
  }

  function handleSaveAlertRule() {
    if (!ruleForm.name.trim() || !ruleForm.metric.trim()) {
      setError(t('platformAdminPage.validation.ruleNameAndMetricRequired'))
      return
    }
    setSaving(true)
    setError(null)
    alertRuleMutation.mutate({
      name: ruleForm.name.trim(),
      description: ruleForm.description,
      type: ruleForm.type,
      severity: ruleForm.severity,
      metric: ruleForm.metric.trim(),
      threshold: parseFloatSafe(ruleForm.threshold),
      windowMinutes: parseIntSafe(ruleForm.windowMinutes),
      enabled: ruleForm.enabled,
      platformOnly: ruleForm.platformOnly,
      tenantId: ruleForm.tenantId.trim() || null,
    })
  }

  async function handleInvalidateCache() {
    setSaving(true)
    setError(null)
    setNotice(null)
    try {
      const result = await api.invalidateResponseCache()
      setNotice(result.message)
      void queryClient.invalidateQueries({ queryKey: queryKeys.platformAdmin.all() })
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  async function handleEvaluateAlerts() {
    setSaving(true)
    setError(null)
    setNotice(null)
    try {
      await api.evaluateAlerts()
      setNotice(t('platformAdminPage.evaluateAlertsSuccess'))
      void queryClient.invalidateQueries({ queryKey: queryKeys.platformAdmin.activeAlerts() })
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  function handleLookupUser() {
    const email = userLookupEmail.trim()
    if (!email) {
      setError(t('platformAdminPage.validation.emailRequired'))
      return
    }
    setError(null)
    setSelectedUserEmail(email)
  }

  useEffect(() => {
    if (selectedUser && !updatingUserRole) setSelectedUserRole(selectedUser.role)
  }, [selectedUser, updatingUserRole])

  async function handleUpdateUserRole() {
    if (!selectedUser) {
      setError(t('platformAdminPage.validation.lookupUserFirst'))
      return
    }
    setUpdatingUserRole(true)
    setError(null)
    try {
      await api.updateUserRole(selectedUser.id, selectedUserRole)
      void queryClient.invalidateQueries({ queryKey: queryKeys.platformAdmin.userByEmail(selectedUserEmail) })
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setUpdatingUserRole(false)
    }
  }

  function handleRefresh() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.platformAdmin.all() })
    useToastStore.getState().addToast({ type: 'success', message: t('common.toast.refreshed') })
  }

  return {
    // Mode
    isManagerMode,
    activeTab,
    setActiveTab,

    // State
    error,
    notice,
    saving,
    isLoading,
    tenantsError: tenantsQuery.error,
    pricingError: pricingQuery.error,
    alertRulesError: alertRulesQuery.error,
    activeAlertsError: activeAlertsQuery.error,
    selectedTenantError: selectedTenantQuery.error,
    selectedUserError: selectedUserQuery.error,
    userLookupLoading: selectedUserQuery.isLoading,

    // Data
    tenants,
    pricing,
    alertRules,
    activeAlerts,
    selectedTenant,
    selectedUser,

    // Tenant selection
    selectedTenantId,
    setSelectedTenantId,

    // User lookup
    userLookupEmail,
    setUserLookupEmail,
    selectedUserRole,
    setSelectedUserRole,
    updatingUserRole,

    // Forms
    tenantForm,
    setTenantForm,
    pricingForm,
    setPricingForm,
    ruleForm,
    setRuleForm,

    // Mutations
    suspendMutation,
    activateMutation,
    deleteAlertMutation,
    resolveAlertMutation,

    // Handlers
    handleCreateTenant,
    handleUpsertPricing,
    handleSaveAlertRule,
    handleInvalidateCache,
    handleEvaluateAlerts,
    handleLookupUser,
    handleUpdateUserRole,
    handleRefresh,
  }
}

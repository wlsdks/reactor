import { useState } from 'react'
import { useQueries, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useRoleVisibility } from '../workspace/RoleVisibilityProvider'
import { toEpochMs, downloadCsv } from '../../shared/lib/formatters'
import { getErrorMessage } from '../../shared/lib/getErrorMessage'
import { useToastStore } from '../../shared/store/toast.store'
import { queryKeys } from '../../shared/lib/queryKeys'
import * as api from './api'
import type { TenantQuotaResponse } from './types'

// ── Date range helpers ────────────────────────────────────────────────────

function defaultFrom(): string {
  const d = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000)
  d.setSeconds(0, 0)
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

function defaultTo(): string {
  const d = new Date()
  d.setSeconds(0, 0)
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

// ── Hook ──────────────────────────────────────────────────────────────────

export function useTenantAdminData(initialTenantId?: string) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { effectiveRole } = useRoleVisibility()
  const isManagerMode = effectiveRole === 'ADMIN_MANAGER'
  const [tenantId, setTenantId] = useState(initialTenantId ?? '')
  const [fromLocal, setFromLocal] = useState(defaultFrom())
  const [toLocal, setToLocal] = useState(defaultTo())
  const [exporting, setExporting] = useState(false)

  // Track whether the user has requested data at least once
  const [hasRequested, setHasRequested] = useState(Boolean(initialTenantId?.trim()))

  const fromMs = toEpochMs(fromLocal)
  const toMs = toEpochMs(toLocal)
  const hasTenantId = !!tenantId.trim()
  const enabled = hasTenantId && hasRequested

  const results = useQueries({
    queries: [
      {
        queryKey: queryKeys.tenantAdmin.overview(tenantId, fromMs, toMs),
        queryFn: () => api.getOverview(tenantId, { fromMs, toMs }),
        enabled,
      },
      {
        queryKey: queryKeys.tenantAdmin.usage(tenantId, fromMs, toMs),
        queryFn: () => api.getUsage(tenantId, { fromMs, toMs }),
        enabled,
      },
      {
        queryKey: queryKeys.tenantAdmin.quality(tenantId, fromMs, toMs),
        queryFn: () => api.getQuality(tenantId, { fromMs, toMs }),
        enabled,
      },
      {
        queryKey: queryKeys.tenantAdmin.tools(tenantId, fromMs, toMs),
        queryFn: () => api.getTools(tenantId, { fromMs, toMs }),
        enabled,
      },
      {
        queryKey: queryKeys.tenantAdmin.cost(tenantId, fromMs, toMs),
        queryFn: () => api.getCost(tenantId, { fromMs, toMs }),
        enabled,
      },
      {
        queryKey: queryKeys.tenantAdmin.slo(tenantId),
        queryFn: () => api.getSlo(tenantId),
        enabled,
      },
      {
        queryKey: queryKeys.tenantAdmin.alerts(tenantId),
        queryFn: () => api.getTenantAlerts(tenantId),
        enabled,
      },
      {
        queryKey: queryKeys.tenantAdmin.quota(tenantId),
        queryFn: () => api.getQuota(tenantId),
        enabled,
      },
    ],
  })

  const [overviewResult, usageResult, qualityResult, toolsResult, costResult, sloResult, alertsResult, quotaResult] = results

  const loading = results.some(r => r.isLoading && r.fetchStatus !== 'idle')
  const firstError = results.find(r => r.error)?.error ?? null
  const error = firstError ? getErrorMessage(firstError) : null

  const overview = overviewResult.data ?? null
  const usage = usageResult.data ?? null
  const quality = qualityResult.data ?? null
  const tools = toolsResult.data ?? null
  const cost = costResult.data ?? null
  const slo = sloResult.data ?? null
  const alerts = alertsResult.data ?? null
  const quota: TenantQuotaResponse | null = quotaResult.data ?? null

  function loadAll() {
    if (!tenantId.trim()) {
      useToastStore.getState().addToast({ type: 'error', message: t('tenantAdminPage.validation.tenantIdRequired') })
      return
    }
    if (!hasRequested) {
      setHasRequested(true)
    } else {
      // Refetch all queries for this tenant
      void queryClient.invalidateQueries({ queryKey: queryKeys.tenantAdmin.all() })
    }
  }

  async function handleExportExecutions() {
    if (isManagerMode) return
    if (!tenantId.trim()) return
    setExporting(true)
    try {
      const csv = await api.exportExecutionsCsv(tenantId, {
        fromMs: toEpochMs(fromLocal),
        toMs: toEpochMs(toLocal),
      })
      downloadCsv(`executions-${tenantId}.csv`, csv)
    } catch (e) {
      useToastStore.getState().addToast({ type: 'error', message: getErrorMessage(e) })
    } finally {
      setExporting(false)
    }
  }

  async function handleExportTools() {
    if (isManagerMode) return
    if (!tenantId.trim()) return
    setExporting(true)
    try {
      const csv = await api.exportToolsCsv(tenantId, {
        fromMs: toEpochMs(fromLocal),
        toMs: toEpochMs(toLocal),
      })
      downloadCsv(`tool-calls-${tenantId}.csv`, csv)
    } catch (e) {
      useToastStore.getState().addToast({ type: 'error', message: getErrorMessage(e) })
    } finally {
      setExporting(false)
    }
  }

  return {
    // Mode
    isManagerMode,

    // Filter state
    tenantId,
    setTenantId,
    fromLocal,
    setFromLocal,
    toLocal,
    setToLocal,

    // Data
    overview,
    usage,
    quality,
    tools,
    cost,
    slo,
    alerts,
    quota,

    // Status
    loading,
    error,
    exporting,
    hasRequested,

    // Actions
    loadAll,
    handleExportExecutions,
    handleExportTools,
  }
}

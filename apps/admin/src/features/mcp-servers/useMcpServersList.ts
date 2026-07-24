import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { queryKeys } from '../../shared/lib/queryKeys'
import { useToastStore } from '../../shared/store/toast.store'
import * as mcpApi from './api'
import { getMcpSecurityPolicy } from '../mcp-security'
import type { McpServerResponse } from './types'
import { useTagStore } from './tags'

// ── Types ──────────────────────────────────────────────────────────────────

export type StatusFilter = '' | 'CONNECTED' | 'DISCONNECTED' | 'FAILED' | 'ERROR' | 'PENDING'

export interface ServerRowData extends McpServerResponse {
  isAllowed: boolean
  serverTags: string[]
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useMcpServersList() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()

  // URL-persisted filters
  const searchRaw = searchParams.get('q') ?? ''
  const statusFilter = (searchParams.get('status') ?? '') as StatusFilter
  const tagFilter = searchParams.get('tag') ?? ''
  const blockedOnly = searchParams.get('blocked') === 'true'

  const PAGE_SIZE = 30
  const [page, setPage] = useState(1)

  // Local debounce state for search input
  const [searchInput, setSearchInput] = useState(searchRaw)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sorting
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc' | null>(null)

  // Confirm dialogs
  const [confirmAction, setConfirmAction] = useState<'connectAll' | 'emergencyBlock' | null>(null)

  // ── Tag store ────────────────────────────────────────────────────────────
  const tags = useTagStore((s) => s.tags)
  const getAllUniqueTags = useTagStore((s) => s.getAllUniqueTags)

  // ── Queries ──────────────────────────────────────────────────────────────

  const {
    data: servers = [],
    isLoading: serversLoading,
    isFetching: serversFetching,
    error: serversError,
  } = useQuery({
    queryKey: queryKeys.mcpServers.list(),
    queryFn: mcpApi.listMcpServers,
  })

  const {
    data: securityPolicy = null,
    isLoading: policyLoading,
    isFetching: policyFetching,
    error: policyError,
  } = useQuery({
    queryKey: queryKeys.mcpSecurity.list(),
    queryFn: getMcpSecurityPolicy,
  })

  // ── Debounced search ─────────────────────────────────────────────────────

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setPage(1)
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          if (searchInput) next.set('q', searchInput)
          else next.delete('q')
          return next
        },
        { replace: true },
      )
    }, 300)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [searchInput, setSearchParams])

  // ── Derived: allowed set ─────────────────────────────────────────────────

  // 백엔드 의미: allowedServerNames 가 빈 집합이면 "모두 허용" (allow-all).
  // 항목이 하나 이상 있으면 명시된 이름만 허용 (deny-list except listed).
  const allowedNames = securityPolicy
    ? new Set(securityPolicy.effective.allowedServerNames)
    : new Set<string>()
  const allowAll = allowedNames.size === 0

  // ── Build rows ───────────────────────────────────────────────────────────

  const lowerSearch = searchRaw.toLowerCase()

  const rows: ServerRowData[] = servers.map((server) => ({
    ...server,
    isAllowed: allowAll || allowedNames.has(server.name),
    serverTags: tags[server.name] ?? [],
  }))

  // Filter: status
  let filteredRows = statusFilter
    ? rows.filter((r) => r.status === statusFilter)
    : rows

  // Filter: blocked only (mutually exclusive with status)
  if (blockedOnly && !statusFilter) {
    filteredRows = filteredRows.filter((r) => !r.isAllowed)
  }

  // Filter: tag
  if (tagFilter) {
    filteredRows = filteredRows.filter((r) => r.serverTags.includes(tagFilter))
  }

  // Filter: search (name + tool name)
  if (lowerSearch) {
    filteredRows = filteredRows.filter(
      (r) =>
        r.name.toLowerCase().includes(lowerSearch) ||
        (r.description ?? '').toLowerCase().includes(lowerSearch),
    )
  }

  // Sort
  if (sortKey && sortDirection) {
    filteredRows = [...filteredRows].sort((a, b) => {
      let cmp = 0
      if (sortKey === 'name') cmp = a.name.localeCompare(b.name)
      else if (sortKey === 'status') cmp = a.status.localeCompare(b.status)
      else if (sortKey === 'tools') cmp = a.toolCount - b.toolCount
      return sortDirection === 'desc' ? -cmp : cmp
    })
  }

  // Check if any displayed row has tags (to conditionally show tags column)
  const anyServerHasTags = filteredRows.some((row) => row.serverTags.length > 0)

  // ── Summary counts ───────────────────────────────────────────────────────

  const totalCount = servers.length
  const connectedCount = servers.filter((s) => s.status === 'CONNECTED').length
  const failedCount = servers.filter((s) => s.status === 'FAILED' || s.status === 'ERROR').length
  const blockedCount = allowAll
    ? 0
    : servers.filter((s) => !allowedNames.has(s.name)).length

  // ── Filter helpers ───────────────────────────────────────────────────────

  function setStatusFilterParam(value: StatusFilter) {
    setPage(1)
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (value) next.set('status', value)
        else next.delete('status')
        // Status and blocked are mutually exclusive
        next.delete('blocked')
        return next
      },
      { replace: true },
    )
  }

  function setBlockedFilterParam(active: boolean) {
    setPage(1)
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (active) next.set('blocked', 'true')
        else next.delete('blocked')
        // Blocked and status are mutually exclusive
        next.delete('status')
        return next
      },
      { replace: true },
    )
  }

  function setTagFilterParam(value: string) {
    setPage(1)
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (value) next.set('tag', value)
        else next.delete('tag')
        return next
      },
      { replace: true },
    )
  }

  // ── Bulk actions ─────────────────────────────────────────────────────────

  async function handleConnectAllDisconnected() {
    const targets = servers.filter(
      (s) => s.status === 'DISCONNECTED' || s.status === 'FAILED',
    )
    if (targets.length === 0) return

    const results = await Promise.allSettled(
      targets.map((s) => mcpApi.connectMcpServer(s.name)),
    )
    const success = results.filter((r) => r.status === 'fulfilled').length
    const failed = results.length - success

    const connectMsg = t('mcpServers.toast.connectAllResult', {
        success,
        total: results.length,
        failed,
      })
    if (failed > 0) useToastStore.getState().addToast({ type: 'warning', message: connectMsg })
    else useToastStore.getState().addToast({ type: 'success', message: connectMsg })
    void queryClient.invalidateQueries({ queryKey: queryKeys.mcpServers.all() })
  }

  async function handleEmergencyBlockAll() {
    const targets = servers.filter((s) => s.status === 'CONNECTED')
    if (targets.length === 0) return

    const results = await Promise.allSettled(
      targets.map((s) => mcpApi.emergencyDenyAll(s.name)),
    )
    const success = results.filter((r) => r.status === 'fulfilled').length
    const failed = results.length - success

    const blockMsg = t('mcpServers.toast.emergencyBlockResult', {
        success,
        total: results.length,
        failed,
      })
    if (failed > 0) useToastStore.getState().addToast({ type: 'warning', message: blockMsg })
    else useToastStore.getState().addToast({ type: 'success', message: blockMsg })
    void queryClient.invalidateQueries({ queryKey: queryKeys.mcpServers.all() })
    void queryClient.invalidateQueries({ queryKey: queryKeys.mcpSecurity.all() })
  }

  // ── Sort handler ─────────────────────────────────────────────────────────

  function handleSort(key: string, direction: 'asc' | 'desc' | null) {
    setSortKey(direction ? key : null)
    setSortDirection(direction)
  }

  // ── Refresh handler ──────────────────────────────────────────────────────

  function handleRefresh() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.mcpServers.all() })
    void queryClient.invalidateQueries({ queryKey: queryKeys.mcpSecurity.all() })
  }

  // ── Loading state ────────────────────────────────────────────────────────

  const isLoading = serversLoading || policyLoading
  const isFetching = serversFetching || policyFetching

  // ── Unique tags for filter ───────────────────────────────────────────────

  const allTags = getAllUniqueTags()

  return {
    // Data
    servers,
    filteredRows,
    isLoading,
    isFetching,
    serversError,
    policyError,

    // Summary counts
    totalCount,
    connectedCount,
    failedCount,
    blockedCount,

    // Filters
    searchInput,
    setSearchInput,
    statusFilter,
    setStatusFilterParam,
    tagFilter,
    setTagFilterParam,
    blockedOnly,
    setBlockedFilterParam,
    allTags,

    anyServerHasTags,

    // Pagination
    page,
    setPage,
    PAGE_SIZE,

    // Sorting
    sortKey,
    sortDirection,
    handleSort,

    // Bulk actions
    confirmAction,
    setConfirmAction,
    handleConnectAllDisconnected,
    handleEmergencyBlockAll,

    // Refresh
    handleRefresh,
  }
}

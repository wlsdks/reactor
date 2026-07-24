import { useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { queryKeys } from '../../shared/lib/queryKeys'
import { useToastStore } from '../../shared/store/toast.store'
import { scheduleUndoableDelete } from '../../shared/lib/scheduleUndoableDelete'
import { showApiErrorToast } from '../../shared/lib/showApiErrorToast'
import { useAnnouncer } from '../../shared/ui'
import * as mcpApi from './api'
import { getMcpSecurityPolicy, updateMcpSecurityPolicy } from '../mcp-security'
import type { McpSecurityPolicyState } from '../mcp-security'
import { supportsAccessPolicy, isSwaggerServer, supportsAdminPreflight } from './serverCapabilities'
import { displayMcpServerName } from './mcpDisplay'
import { useTagStore } from './tags'

// ── Constants ───────────────────────────────────────────────────────────────

const emptyTags: string[] = []

// ── Hook ────────────────────────────────────────────────────────────────────

export function useMcpServerDetail() {
  const { name = '' } = useParams<{ name: string }>()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { announce } = useAnnouncer()

  // Local state
  const [showSensitive, setShowSensitive] = useState(false)
  const [toolFilter, setToolFilter] = useState('')
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const toggleInFlightRef = useRef(false)

  // Tag store
  const allTags = useTagStore((s) => s.tags)
  const serverTags = allTags[name] ?? emptyTags

  // ── Queries ─────────────────────────────────────────────────────────────

  const {
    data: server,
    isLoading: serverLoading,
    error: serverError,
    isFetching: serverFetching,
    refetch: refetchServer,
  } = useQuery({
    queryKey: queryKeys.mcpServers.detail(name),
    queryFn: () => mcpApi.getMcpServer(name),
    enabled: !!name,
  })

  const { data: securityPolicy = null } = useQuery({
    queryKey: queryKeys.mcpSecurity.list(),
    queryFn: getMcpSecurityPolicy,
  })

  const { data: accessPolicy } = useQuery({
    queryKey: queryKeys.mcpServers.policy(name),
    queryFn: () => mcpApi.getMcpAccessPolicy(name),
    enabled: !!server && supportsAccessPolicy(server),
  })

  const { data: preflightData, refetch: refetchPreflight, isFetching: preflightFetching } = useQuery({
    queryKey: queryKeys.mcpServers.preflight(name),
    queryFn: () => mcpApi.getMcpPreflight(name),
    enabled: false,
  })

  const { data: swaggerSources } = useQuery({
    queryKey: queryKeys.mcpServers.swaggerSources(name),
    queryFn: () => mcpApi.listSwaggerSpecSources(name),
    enabled: !!server && isSwaggerServer(server),
  })

  // ── Mutations ───────────────────────────────────────────────────────────

  const connectMutation = useMutation({
    mutationFn: mcpApi.connectMcpServer,
    onSuccess: (_data, connectedName) => {
      useToastStore.getState().addToast({ type: 'success', message: t('mcpServers.toast.connected') })
      announce(t('common.a11y.serverConnected', { name: connectedName }))
      void queryClient.invalidateQueries({ queryKey: queryKeys.mcpServers.all() })
    },
  })

  const disconnectMutation = useMutation({
    mutationFn: mcpApi.disconnectMcpServer,
    onSuccess: (_data, disconnectedName) => {
      useToastStore.getState().addToast({ type: 'success', message: t('mcpServers.toast.disconnected') })
      announce(t('common.a11y.serverDisconnected', { name: disconnectedName }))
      void queryClient.invalidateQueries({ queryKey: queryKeys.mcpServers.all() })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: mcpApi.deleteMcpServer,
    onSuccess: () => {
      // Authoritative refetch after the grace period commits the delete.
      // Optimistic UI already navigated the user back to the list.
      void queryClient.invalidateQueries({ queryKey: queryKeys.mcpServers.all() })
    },
    onError: (err) => {
      // The optimistic UI navigated away from the detail page and removed
      // the server from the cached list. We can't easily restore the user's
      // detail location once the API actually fails, so just refetch the
      // list and surface a localized error toast.
      void queryClient.invalidateQueries({ queryKey: queryKeys.mcpServers.all() })
      showApiErrorToast(err)
    },
  })

  /**
   * Trigger an undoable delete for the current server. Splits the mutation
   * up into an immediate optimistic phase (cache eviction + navigate to the
   * list) and a deferred commit phase that fires once the 5s grace window
   * elapses without an undo click.
   */
  function startUndoableDelete() {
    if (!name) return
    const targetName = name
    const listKey = queryKeys.mcpServers.list()
    const detailKey = queryKeys.mcpServers.detail(targetName)

    type ServerListEntry = { name: string; [key: string]: unknown }
    const listSnapshot = queryClient.getQueryData<ServerListEntry[]>(listKey)
    const detailSnapshot = queryClient.getQueryData(detailKey)

    scheduleUndoableDelete({
      message: t('mcpServers.deletedNamed', { name: displayMcpServerName(targetName) }),
      undoLabel: t('common.undo'),
      undoneMessage: t('common.toast.undone'),
      optimistic: () => {
        if (listSnapshot) {
          queryClient.setQueryData<ServerListEntry[]>(
            listKey,
            listSnapshot.filter((s) => s.name !== targetName),
          )
        }
        // Schedule the live-region announcement on the next macrotask so it
        // wins over any list-level row-count announce that may fire when
        // the user lands on the list page.
        setTimeout(() => void announce(t('common.a11y.deleted')), 0)
        void navigate('/mcp-servers')
      },
      restore: () => {
        if (listSnapshot) {
          queryClient.setQueryData(listKey, listSnapshot)
        } else {
          void queryClient.invalidateQueries({ queryKey: queryKeys.mcpServers.all() })
        }
        if (detailSnapshot) {
          queryClient.setQueryData(detailKey, detailSnapshot)
        }
        void navigate(`/mcp-servers/${encodeURIComponent(targetName)}`)
      },
      commit: () => deleteMutation.mutateAsync(targetName),
    })
  }

  // ── Allowed toggle (same optimistic pattern as list page) ─────────────

  const toggleAllowedMutation = useMutation({
    meta: { skipGlobalError: true },
    mutationFn: async ({ serverName, allowed }: { serverName: string; allowed: boolean }) => {
      const current = queryClient.getQueryData<McpSecurityPolicyState>(
        queryKeys.mcpSecurity.list(),
      )
      if (!current) throw new Error(t('mcpServers.policyNotLoaded'))

      const source = current.stored ?? current.effective
      const currentNames = new Set(source.allowedServerNames)
      if (allowed) currentNames.add(serverName)
      else currentNames.delete(serverName)

      return updateMcpSecurityPolicy({
        allowedServerNames: [...currentNames].sort(),
        maxToolOutputLength: source.maxToolOutputLength,
      })
    },
    onMutate: async ({ serverName, allowed }) => {
      toggleInFlightRef.current = true
      await queryClient.cancelQueries({ queryKey: queryKeys.mcpSecurity.list() })
      const previous = queryClient.getQueryData<McpSecurityPolicyState>(
        queryKeys.mcpSecurity.list(),
      )

      if (previous) {
        const source = previous.stored ?? previous.effective
        const currentNames = new Set(source.allowedServerNames)
        if (allowed) currentNames.add(serverName)
        else currentNames.delete(serverName)

        queryClient.setQueryData<McpSecurityPolicyState>(
          queryKeys.mcpSecurity.list(),
          {
            ...previous,
            effective: {
              ...previous.effective,
              allowedServerNames: [...currentNames].sort(),
            },
          },
        )
      }

      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.mcpSecurity.list(), context.previous)
      }
      useToastStore.getState().addToast({ type: 'error', message: t('mcpServers.toast.toggleFailed') })
    },
    onSuccess: (_data, { allowed }) => {
      useToastStore.getState().addToast({ type: 'success', message: allowed
          ? t('mcpServers.toast.toggleAllowed')
          : t('mcpServers.toast.toggleBlocked') })
    },
    onSettled: () => {
      toggleInFlightRef.current = false
      void queryClient.invalidateQueries({ queryKey: queryKeys.mcpSecurity.list() })
    },
  })

  // ── Derived state ─────────────────────────────────────────────────────

  const isAllowed = securityPolicy
    ? new Set(securityPolicy.effective.allowedServerNames).has(name)
    : false

  const isConnected = server?.status === 'CONNECTED'

  // ── Tools filtering ───────────────────────────────────────────────────

  const lowerFilter = toolFilter.toLowerCase()
  const filteredTools = server
    ? (lowerFilter
        ? server.tools.filter((tool) => tool.toLowerCase().includes(lowerFilter))
        : server.tools)
    : []

  // ── Capability checks ────────────────────────────────────────────────

  const hasAccessPolicy = !!server && supportsAccessPolicy(server)
  const hasSwagger = !!server && isSwaggerServer(server)
  const hasPreflight = !!server && supportsAdminPreflight(server)

  return {
    // Route params
    name,

    // Server data
    server,
    serverLoading,
    serverError,
    serverFetching,
    refetchServer,

    // Security
    securityPolicy,
    isAllowed,

    // Access policy
    accessPolicy,
    hasAccessPolicy,

    // Preflight
    preflightData,
    preflightFetching,
    refetchPreflight,
    hasPreflight,

    // Swagger
    swaggerSources,
    hasSwagger,

    // Tags
    serverTags,

    // Mutations
    connectMutation,
    disconnectMutation,
    deleteMutation,
    startUndoableDelete,
    toggleAllowedMutation,
    toggleInFlightRef,

    // Derived state
    isConnected,

    // Local state
    showSensitive,
    setShowSensitive,
    toolFilter,
    setToolFilter,
    filteredTools,
    showDeleteConfirm,
    setShowDeleteConfirm,

    // Navigation
    navigate,
  }
}

import { useQuery } from '@tanstack/react-query'
import { queryClient } from '../../shared/lib/queryClient'
import { queryKeys } from '../../shared/lib/queryKeys'
import { STALE_TIMES } from '../../shared/lib/staleTimes'
import { getCapabilityManifest, type CapabilityManifest } from './api'

/**
 * Canonical TanStack Query options for `/api/admin/capabilities`.
 *
 * All consumers (the FeatureAvailabilityProvider, dashboard topology query,
 * issue-center snapshot, integrations manager, …) must route through this
 * queryKey so the request is deduped app-wide. React Query coalesces in-flight
 * fetches and honours the configured `staleTime`, reducing the previously
 * observed 3x duplicate calls on dashboard mount to a single request.
 */
export const capabilitiesQueryOptions = {
  queryKey: queryKeys.capabilities(),
  queryFn: getCapabilityManifest,
  // Manifest is generated at backend boot; rarely changes within a session.
  staleTime: STALE_TIMES.SLOW,
} as const

/**
 * Hook for components that need the capability manifest directly.
 *
 * Returns the query result so loading / error states can be reflected in the
 * UI. Internal helpers that must await the manifest from a non-component
 * context (e.g. another `queryFn`) should call {@link fetchCapabilityManifestCached}
 * instead.
 */
export function useCapabilities() {
  return useQuery(capabilitiesQueryOptions)
}

/**
 * Imperative, dedupe-aware fetch for the capability manifest.
 *
 * Safe to call from any `queryFn`/effect — TanStack Query will reuse an
 * in-flight request or a fresh cache entry under {@link queryKeys.capabilities}
 * instead of issuing a new network call. Returns `null` on failure so callers
 * can degrade gracefully (matching the behaviour of the underlying
 * {@link getCapabilityManifest}).
 */
export function fetchCapabilityManifestCached(options?: { skipGlobalError?: boolean }): Promise<CapabilityManifest | null> {
  return queryClient.fetchQuery({
    ...capabilitiesQueryOptions,
    meta: options?.skipGlobalError ? { skipGlobalError: true } : undefined,
  })
}

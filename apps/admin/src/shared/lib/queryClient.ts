import { QueryClient, MutationCache, QueryCache } from '@tanstack/react-query'
import i18next from 'i18next'
import { useToastStore } from '../store/toast.store'
import { errorLogger } from './errorLogger'
import { ApiError, NetworkError, sanitizeErrorMessage } from '../api/errors'

/**
 * Module augmentation for TanStack Query's `meta` typing.
 *
 * - `queryMeta.skipGlobalError` — opt-out of the global error toast (the
 *   feature handles its own messaging, e.g. silent background refetch).
 * - `mutationMeta.skipGlobalError` — same semantics for mutations; already
 *   honoured by the `MutationCache.onError` handler below.
 *
 * Keeping the keys typed prevents typos and gives editor autocompletion at
 * `useQuery({ meta: { ... } })` / `useMutation({ meta: { ... } })` call sites.
 */
declare module '@tanstack/react-query' {
  interface Register {
    queryMeta: {
      skipGlobalError?: boolean
    }
    mutationMeta: {
      skipGlobalError?: boolean
    }
  }
}

/**
 * Resolve the final user-facing message for an unknown error while remaining
 * compatible with test environments where i18next has not been bootstrapped.
 * We deliberately do NOT import `../i18n/config` here to avoid side-effect
 * initialisation that would leak across unit tests.
 */
function resolveUnknownErrorMessage(): string {
  const raw = i18next.isInitialized ? i18next.t('error.unknown') : undefined
  return typeof raw === 'string' && raw && raw !== 'error.unknown'
    ? raw
    : 'An unexpected error occurred.'
}

function resolveErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.userMessage
  if (error instanceof NetworkError) return error.message
  return sanitizeErrorMessage(
    error instanceof Error ? error.message : resolveUnknownErrorMessage(),
  )
}

/**
 * Singleton QueryClient for the admin app.
 *
 * Exposed as a module-level export (not just through QueryClientProvider) so
 * non-component code paths — e.g. the dedupe helper for
 * `/api/admin/capabilities` — can call `queryClient.fetchQuery(...)` and share
 * the same cache as the React tree. TanStack Query coalesces concurrent
 * fetches against the same queryKey, eliminating duplicate network requests.
 */
export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error, query) => {
      if (query.meta?.skipGlobalError) return
      errorLogger.capture(
        error instanceof Error ? error : new Error(String(error)),
        { action: 'query', queryKey: JSON.stringify(query.queryKey) },
      )
      // Queries handle their own UI for the empty/error state, so we only
      // surface a toast when the error is actionable to the operator.
      // Currently we skip query-level toasts to avoid duplicates; the
      // capture above ensures errors are still logged centrally.
    },
  }),
  mutationCache: new MutationCache({
    onError: (error, _variables, _context, mutation) => {
      if (mutation.meta?.skipGlobalError) return
      errorLogger.capture(
        error instanceof Error ? error : new Error(String(error)),
        { action: 'mutation' },
      )
      useToastStore.getState().addToast({ type: 'error', message: resolveErrorMessage(error) })
    },
  }),
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status < 500) return false
        return failureCount < 2
      },
      // 30s default freshness — see STALE_TIMES in shared/lib/constants for
      // per-feature presets that override this.
      staleTime: 30_000,
      // Keep cached data for 5 min after the last observer unmounts so that
      // back-navigation / tab switches reuse the cache instead of refetching.
      // staleTime (30s) is the freshness window; gcTime (5m) is the eviction
      // window — they answer different questions and 5m comfortably covers
      // typical admin tab-switching while bounding memory growth.
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
      // `structuralSharing: true` is the TanStack Query default; pinning it
      // explicitly so future upstream changes don't silently regress
      // referential equality (which our React Compiler-friendly hooks rely on
      // to avoid unnecessary re-renders).
      structuralSharing: true,
      // `networkMode: 'online'` is the TanStack Query default; pinning it
      // explicitly so the admin app fails fast when the operator is offline
      // instead of queuing requests indefinitely. Pair this with the offline
      // banner / NetworkStatus indicator for UX.
      networkMode: 'online',
    },
    mutations: {
      networkMode: 'online',
    },
  },
})

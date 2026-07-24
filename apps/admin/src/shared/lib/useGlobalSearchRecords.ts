import { useCallback, useSyncExternalStore } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import type { SearchableRecord } from './searchIndex'
import { buildReleaseWorkflowSearchRecords } from '../releaseWorkflow'
import type { PersonaResponse } from '../../features/personas/types'
import type { TemplateResponse } from '../../features/prompts/types'
import type { FeedbackEntry, CursorPage } from '../../features/feedback/types'
import type { AuditLogEntry } from '../../features/audit/types'
import { createAuditLabelLocalizers } from '../../features/audit/auditLabels'
import type { SessionRow, PaginatedResponse } from '../../features/sessions/types'

/**
 * Subscribe to existing TanStack Query caches and project them into a flat
 * list of {@link SearchableRecord}s for the Command Palette data search.
 *
 * IMPORTANT: This hook does NOT trigger any network fetches. It only reads
 * whatever is currently cached for the canonical list query keys (and their
 * parameterised variants for feedback / audit / sessions). When a scope has
 * not been visited in the current session its records will simply be absent
 * from the result.
 */
export function useGlobalSearchRecords(): SearchableRecord[] {
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  // Re-render whenever any cache mutation happens. The cache fires its
  // listener synchronously from inside whichever component triggered the
  // mutation, so we defer the React notification to a microtask. Without
  // this, useSyncExternalStore would tell React to update CommandPalette
  // mid-render of the component that just wrote to the cache, producing
  // "Cannot update a component while rendering a different component".
  const subscribe = useCallback(
    (onChange: () => void) => {
      const cache = queryClient.getQueryCache()
      return cache.subscribe(() => {
        queueMicrotask(onChange)
      })
    },
    [queryClient],
  )

  // Reading getSnapshot must be cheap; we delegate the actual mapping work
  // and accept that React will only call this when subscribe fires.
  const getSnapshot = useCallback((): string => {
    // Stamp encodes how many list queries are currently cached so React's
    // referential check tells re-renders apart. The full data is read in
    // the body below using the same client.
    return cacheStamp(queryClient)
  }, [queryClient])

  // We rely on useSyncExternalStore to react to cache mutations. The actual
  // record list is computed below from the same `queryClient` snapshot.
  useSyncExternalStore(subscribe, getSnapshot, getSnapshot)

  return collectRecords(queryClient, t)
}

/**
 * Build a small stable string that changes whenever any tracked cache
 * entry's `dataUpdatedAt` advances. Used purely as the snapshot value
 * for `useSyncExternalStore`.
 */
function cacheStamp(queryClient: QueryClient): string {
  const cache = queryClient.getQueryCache()
  let stamp = ''
  for (const q of cache.getAll()) {
    const head = q.queryKey[0]
    if (
      head === 'personas' ||
      head === 'prompts' ||
      head === 'feedback' ||
      head === 'audit' ||
      head === 'sessions'
    ) {
      stamp += `${q.queryHash}:${q.state.dataUpdatedAt};`
    }
  }
  return stamp
}

function collectRecords(
  queryClient: QueryClient,
  translate: TFunction,
): SearchableRecord[] {
  const out: SearchableRecord[] = buildReleaseWorkflowSearchRecords(translate)
  collectPersonas(queryClient, out)
  collectPrompts(queryClient, out)
  collectFeedback(queryClient, out)
  collectAudit(queryClient, out, translate)
  collectSessions(queryClient, out)
  return out
}

function buildHaystack(parts: Array<string | null | undefined>): string {
  return parts.filter((p): p is string => Boolean(p)).join(' ').toLowerCase()
}

function collectPersonas(queryClient: QueryClient, out: SearchableRecord[]): void {
  const data = queryClient.getQueryData<PersonaResponse[]>(['personas', 'list'])
  if (!Array.isArray(data)) return
  for (const p of data) {
    out.push({
      id: p.id,
      scope: 'persona',
      title: p.name,
      subtitle: p.description ?? undefined,
      navigateTo: `/personas?id=${encodeURIComponent(p.id)}`,
      haystack: buildHaystack([p.name, p.description, p.systemPrompt, p.responseGuideline]),
    })
  }
}

function collectPrompts(queryClient: QueryClient, out: SearchableRecord[]): void {
  const data = queryClient.getQueryData<TemplateResponse[]>(['prompts', 'list'])
  if (!Array.isArray(data)) return
  for (const t of data) {
    out.push({
      id: t.id,
      scope: 'prompt',
      title: t.name,
      subtitle: t.description || undefined,
      navigateTo: `/prompts?id=${encodeURIComponent(t.id)}`,
      haystack: buildHaystack([t.name, t.description]),
    })
  }
}

/**
 * Feedback list keys are parameterised, so we scan all cache entries with
 * the `['feedback', 'list', ...]` prefix and merge their pages. Items are
 * deduplicated by `feedbackId` — the most recently written page wins.
 */
function collectFeedback(queryClient: QueryClient, out: SearchableRecord[]): void {
  const entries = queryClient.getQueriesData<CursorPage<FeedbackEntry>>({
    queryKey: ['feedback', 'list'],
  })
  if (entries.length === 0) return

  const seen = new Map<string, FeedbackEntry>()
  for (const [, page] of entries) {
    if (!page || !Array.isArray(page.items)) continue
    for (const item of page.items) {
      seen.set(item.feedbackId, item)
    }
  }

  for (const f of seen.values()) {
    const titleSource = f.query?.trim() || f.comment?.trim() || `Feedback ${f.feedbackId.slice(0, 8)}`
    out.push({
      id: f.feedbackId,
      scope: 'feedback',
      title: titleSource,
      subtitle: f.comment && f.comment !== titleSource ? f.comment : undefined,
      navigateTo: `/feedback?id=${encodeURIComponent(f.feedbackId)}`,
      haystack: buildHaystack([
        f.query,
        f.response,
        f.comment,
        f.intent,
        f.domain,
        f.model,
        ...(f.tags ?? []),
        ...(f.reviewTags ?? []),
      ]),
    })
  }
}

function collectAudit(queryClient: QueryClient, out: SearchableRecord[], translate: TFunction): void {
  const entries = queryClient.getQueriesData<AuditLogEntry[]>({ queryKey: ['audit', 'list'] })
  if (entries.length === 0) return

  const seen = new Map<string, AuditLogEntry>()
  for (const [, list] of entries) {
    if (!Array.isArray(list)) continue
    for (const item of list) {
      seen.set(item.id, item)
    }
  }

  const { localizeAction, localizeCategory, localizeResource } = createAuditLabelLocalizers(translate)

  for (const a of seen.values()) {
    const title = `${localizeAction(a.action)} · ${localizeCategory(a.category)}`
    out.push({
      id: a.id,
      scope: 'audit',
      title,
      subtitle: localizeResource(a),
      navigateTo: `/audit?id=${encodeURIComponent(a.id)}`,
      haystack: buildHaystack([
        a.action,
        a.category,
        a.actor,
        a.actorEmail,
        a.resourceType,
        a.resourceId,
        a.detail,
        a.targetEmail,
      ]),
    })
  }
}

function collectSessions(queryClient: QueryClient, out: SearchableRecord[]): void {
  const entries = queryClient.getQueriesData<PaginatedResponse<SessionRow>>({
    queryKey: ['sessions', 'feed'],
  })
  if (entries.length === 0) return

  const seen = new Map<string, SessionRow>()
  for (const [, page] of entries) {
    if (!page || !Array.isArray(page.items)) continue
    for (const item of page.items) {
      seen.set(item.sessionId, item)
    }
  }

  for (const s of seen.values()) {
    const title = s.preview?.trim() || `Session ${s.sessionId.slice(0, 8)}`
    out.push({
      id: s.sessionId,
      scope: 'session',
      title,
      subtitle: s.personaName ?? s.userId,
      navigateTo: `/sessions?session=${encodeURIComponent(s.sessionId)}`,
      haystack: buildHaystack([
        s.preview,
        s.personaName,
        s.userId,
        s.channel,
        ...(s.tags ?? []).map((t) => t.label),
      ]),
    })
  }
}

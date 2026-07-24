# Pre-Deployment Expert Review — 2026-04-05

> **Historical snapshot.** Captured at commit 84fa2c1 (28 features, 32 routes, 143
> test files, 54,731 LOC). The "FAIL" verdict on i18n was resolved by Stage F
> (`pnpm verify:i18n` quality gate, EN locale removed, all keys migrated to
> `ko.json`). Several CONDITIONAL items have been addressed by the Stage A–G
> design-system / accessibility cycles. Retained for audit history; not a
> reflection of the current codebase state.

## Overview

20 expert agents (5 Product + 8 Engineering + 4 Domain + 3 Operations) reviewed the entire Reactor Admin codebase in parallel before production deployment.

- **Project**: Reactor Admin (React 19 + Vite 7 + TypeScript 5.9)
- **Scale**: 28 features, 32 routes, 143 test files, 54,731 LOC
- **Branch**: main (commit 84fa2c1)

---

## Scorecard

| # | Expert | Score | Critical | Major | Minor | Verdict |
|---|--------|-------|----------|-------|-------|---------|
| 01 | PRD Conformance | 95% | 0 | 1 | 6 | PASS |
| 02 | UX/Flow | — | 3 | 8 | 6 | CONDITIONAL |
| 03 | i18n | — | 11 | 18 | 3 | FAIL |
| 04 | IA/Permissions | — | 0 | 0 | 4 | PASS |
| 05 | Design System | 78/100 | 3 | 5 | 1 | CONDITIONAL |
| 06 | React | B+ | 0 | 3 | 5 | PASS |
| 07 | Security (OWASP) | 8.5/10 | 0 | 0 | 7 | PASS |
| 08 | API/State Mgmt | — | 0 | 6 | 8 | CONDITIONAL |
| 09 | Performance | 8/10 | 0 | 2 | 6 | PASS |
| 10 | QA/Testing | — | 3 | 6 | 5 | FAIL |
| 11 | Accessibility | 78% | 0 | 5 | 6 | FAIL |
| 12 | DevOps | — | 3 | 5 | 7 | FAIL |
| 13 | Type Safety | 8.5/10 | 0 | 4 | 5 | PASS |
| 14 | Multi-tenancy | 6.3/10 | 0 | 1 | 4 | CONDITIONAL |
| 15 | SSE/Streaming | — | 0 | 3 | 4 | CONDITIONAL |
| 16 | Business Logic | — | 0 | 5 | 6 | CONDITIONAL |
| 17 | Memory/Resources | 92/100 | 0 | 0 | 5 | PASS |
| 18 | Observability | 3/10 | 3 | 5 | 4 | FAIL |
| 19 | Network Resilience | 5.1/10 | 3 | 5 | 4 | FAIL |
| 20 | Concurrency | 5/10 | 2 | 5 | 6 | FAIL |

**Total: Critical 21, Major 77, Minor 106**

---

## Cross-Expert Validated Issues (2+ experts independently found)

### 1. FeedbackManager / ProactiveChannelsManager / TenantAdmin — No TanStack Query
- **Experts**: #02 UX, #06 React, #08 API, #17 Memory, #19 Network (5 experts)
- useState+useEffect manual pattern → no caching, race conditions, no error recovery

### 2. Inline Modals Missing Accessibility (11 modals)
- **Experts**: #02 UX, #11 a11y
- No role="dialog", aria-modal, focus trap. DetailModal component exists but unused

### 3. Session Export No Error Handling
- **Experts**: #08 API, #19 Network
- Promise without .catch() → silent failure

### 4. SSE Streaming No Timeout/Reconnection
- **Experts**: #15 SSE, #19 Network
- fetchWithAuth not used (401 auto-logout missing), no idle timeout

### 5. Logout Doesn't Clear queryClient
- **Experts**: #14 Multi-tenancy, #20 Concurrency
- Different admin on same browser can see previous session data

### 6. No Optimistic Locking Anywhere
- **Experts**: #16 Business Logic, #20 Concurrency
- All PUT/UPDATE operations have no version management → lost updates on concurrent edits

---

## P0 — Must Fix Before Deploy (~5 hours total)

| # | Issue | Expert(s) | Est. |
|---|-------|-----------|------|
| P0-1 | Docker VITE_API_URL build-time ARG | #12 | 15min |
| P0-2 | Create .dockerignore | #12 | 10min |
| P0-3 | Sentry integration + hidden source maps | #18 | 2hr |
| P0-4 | Add queryClient.clear() on logout | #14, #20 | 15min |
| P0-5 | Add .catch() to session export | #08, #19 | 5min |
| P0-6 | Detect cross-tab token *changes* (not just deletion) | #20 | 30min |
| P0-7 | Apply nginx CSP to all location blocks | #12, #07 | 20min |
| P0-8 | Expand vitest coverage include scope | #10 | 15min |
| P0-9 | Add workspace mode switching E2E test | #10 | 1hr |
| P0-10 | Fix 11 broken i18n t() references | #03 | 30min |

---

## P1 — Fix Within 1 Week Post-Deploy

| Issue | Expert(s) | Est. |
|-------|-----------|------|
| Migrate FeedbackManager/ProactiveChannels/TenantAdmin → TanStack Query | #02,#06,#08 | 4hr |
| Refactor 11 inline modals → DetailModal | #02, #11 | 3hr |
| SSE idle timeout + use fetchWithAuth | #15, #19 | 1hr |
| Approval double-click protection + error handling | #16, #19, #20 | 1hr |
| Enable refetchOnReconnect: true | #19 | 5min |
| Add htmlFor to ~90 labels | #11 | 2hr |
| Add ARIA tablist/tab pattern to ~12 tab UIs | #11 | 2hr |
| i18n: fix 22 hardcoded strings | #03 | 1hr |
| Fix brand colors: #D4A34A → #E0B85A, #64748B → #94A3B8 | #05 | 30min |
| Add recharts to manualChunks | #09 | 10min |
| Pin pnpm version, nginx non-root user | #12 | 30min |
| Create CI/CD pipeline | #12 | 1hr |
| 429 rate limit handling with backoff | #19 | 1hr |
| Emergency deny-all retry logic | #19 | 1hr |
| Approval idempotency protection | #20 | 1hr |
| Scheduler double-click guard | #20 | 30min |

---

## Detailed Expert Reports

### Expert #01 — PRD Conformance (95%)

**Findings:**
- Major: `/issues` route missing from requirements.ts, PRD endpoint `/api/issues` doesn't exist (client-side composite)
- Minor: `/rag-cache` not in PRD, sidebar 15→16 count mismatch, endpoint path PRD typos (3), vendor chunk naming inconsistency, i18n 5 key drift
- Positive: dangerouslySetInnerHTML 0, any 0, manual memo 0, test infra complete
- Route coverage: 22/22 PRD routes implemented, all redirects working

### Expert #02 — UX/Flow

**Critical (3):**
1. UsersList: No loading/error/empty states (blank page)
2. SessionDetail: Hardcoded "Loading..." text, no retry on error
3. RagCacheManager: Search results counted but never rendered (broken feature)

**Major (8):**
1. FeedbackManager uses useState+useEffect instead of TanStack Query
2. ProactiveChannelsManager same anti-pattern
3. SessionDetail hardcoded English "Session not found"
4. PromptStudioManager raw modal without accessibility (no focus trap, escape, ARIA)
5. PromptsManager 2 raw modals same issue
6. IntentsManager raw modal same issue
7. ApprovalsManager 2 raw modals (approve + reject) same issue
8. MCP Servers "Register Server" and "Global Settings" buttons wired to empty handlers
9. MCP Server Detail "Edit" button empty handler
10. PromptLab "Auto Optimize" and "Analyze Feedback" buttons unreachable (no trigger)

**Minor (6):**
- Dashboard bare spinner (no skeleton), SafetyRules tab not synced to URL, MetricsIngestion no success toast, ProactiveChannels raw delete modal, DetailSkeleton hardcoded "Loading", SessionsFeed raw spinner

**Pages passing Karrot/Toss bar:** PersonasPage, McpServersListView, McpServerDetailView, OutputGuardManager, AuditLogManager, SessionsPage, ApprovalsManager, ToolPolicyManager, DocumentsManager, LoginPage, NotFoundPage, and 4 more

**Pages failing:** FeedbackManager, ProactiveChannelsManager, SessionDetail, UsersList, RagCacheManager, MCP buttons, PromptLab unreachable features, 5 raw modals

### Expert #03 — i18n

**Broken t() references (11):** common.back, scheduler.runbook.inspectBacklogTitle/Body, approvals.runbook.inspectQueueTitle/Body, promptLabPage.maxSamples/autoOptimize/candidateCount/judgeModel

**Hardcoded strings (22):** "Health" (ReactorGauge), "No data" (2 charts), "Reactor Admin" (Login), "Reactor" (Header), "Enter" (CommandPalette), "Reactor" (Topology), "Loading" aria-label (DetailSkeleton), mode aria-labels (Header), JSON validation errors (5), etc.

**Untranslated KO (13):** "Approvals Queue", "Admin Audit Log", "Rate Budget", "Guard Coverage", etc.

**KO-only keys (5):** mcpServers.status.connected/disconnected/error/failed/pending — missing from EN

**Unused keys (88):** Dashboard cards/statusBanner (28), mcpSecurityPage (10), mcpServers policy fields (26), etc.

**Stats:** EN 2,125 keys, KO 2,130 keys, EN→KO coverage 100%, fix estimate ~2.5 hours

### Expert #04 — IA/Permissions

**Verdict: Solid.** 3-layer auth defense working correctly (login gate → layout gate → route gate).

**Minor (4):**
1. /rag-cache missing from ROUTE_REQUIREMENTS (bypasses feature gating)
2. /issues missing from ROUTE_REQUIREMENTS (by design)
3. Workspace policy doc outdated (15→16 sidebar items)
4. resolveAvailableModes default grants both modes for unexpected roles (unreachable)

**Route coverage matrix:** All 26 routes verified against navigation.ts, requirements.ts, and router.tsx. Manager mode correctly shows 7 routes, developer mode shows 16+. Direct URL access properly protected by FeatureRoute.

### Expert #05 — Design System (78/100)

**Critical (3):**
1. #64748B fails WCAG AA contrast (3.7:1) — used in chart axis ticks
2. #D4A34A is not brand primary #E0B85A — used 8 times in charts
3. #64748B is off-palette (not defined in any token)

**Major (5):**
1. 11 CSS fallback values use wrong palette (CollapsibleSection, shared-components, dashboard)
2. 380 inline styles across 67 TSX files
3. #D4A34A brand variant inconsistency across chart components
4. 9 hardcoded 'IBM Plex Mono' declarations bypassing var(--font-mono)
5. ~20 unique rgba values without tokens

**Minor (1):** Hardcoded pixel font sizes

**Positive:** Token system well-architected, root :root block comprehensive, !important only in reduced-motion (3 instances, acceptable)

### Expert #06 — Senior React (B+)

**Major (3):**
1. FeedbackManager manual fetching (not TanStack Query)
2. ProactiveChannelsManager manual fetching
3. usePlatformAdminData render-time setState

**Minor (5):** SideNav useEffect missing deps, FeedbackManager useEffect missing deps, DocumentPolicyTab useEffect missing deps, PersonaFormModal manual template fetch, RegisterServerModal render-time setState (acceptable pattern)

**Positive:** Zero useMemo/useCallback/React.memo (React Compiler compliance perfect), 30/32 pages proper thin wrappers, excellent feature encapsulation, Zustand UI-only, proper context usage, code splitting via lazy()

### Expert #07 — Security OWASP (8.5/10, CONDITIONAL PASS)

**Medium (2):**
1. ChatInspector source.url rendered in <a href> without scheme validation (javascript: XSS)
2. JWT in localStorage (httpOnly migration planned)

**Low (5):**
1. Dev credentials in production bundle (handleDevLogin)
2. CSP not on static asset location blocks
3. External fonts without SRI
4. Docker HTTP only (needs TLS termination)
5. ReDoS risk in output guard regex validation

**Positive:** dangerouslySetInnerHTML 0, eval 0, Bearer token CSRF-immune, Zod schemas with limits, encodeURIComponent on all path params, error message sanitization, user data not persisted in localStorage (excellent security decision), proper role-based access

### Expert #08 — API Integration

**Major (6):**
1. Auth publicApi missing error normalization → generic "Server error" on login failure
2. FeedbackManager manual state (no TanStack Query)
3. ProactiveChannelsManager manual state
4. TenantAdmin manual state (8 useState hooks)
5. Session export unhandled promise rejection
6. Session tag mutations lack error feedback

**Minor (8):** Inline query keys (3 locations), Record<string,unknown> return types (2 features), no placeholderData for pagination, no AbortSignal propagation, session delete missing onError, bulk MCP actions not useMutation, integrations raw fetch bypasses 401, ISSUE_CENTER_QUERY_KEY outside queryKeys.ts

**Positive:** MutationCache global error handling excellent, optimistic update correct, error sanitization good, cross-tab session sync, staleTime 30s appropriate

### Expert #09 — Performance (8/10)

**Major (2):**
1. recharts 385KB chunk not in manualChunks → large download on first chart page
2. Issue Center API 3-4 level waterfall (500ms-2s unnecessary latency)

**Minor (6):** useClockDisplay 1s re-renders, SSE event array copy GC pressure, SessionsFeed infinite accumulation, logo.png 100KB unoptimized, both locale files loaded eagerly, dashboard readiness waterfall

**Positive:** Main bundle 340KB (under 500KB target), 21 routes all lazy-loaded, 8 vendor chunks, React Compiler enabled, TanStack Query config good, no any types

### Expert #10 — QA/Testing

**Critical (3):**
1. vitest.config.ts coverage only instruments shared/ (~40 files) — 27 feature modules excluded. 91.86% is misleading
2. No workspace mode switching E2E test
3. No role-based login rejection E2E test

**Major (6):** SSE streaming untested, 2 Zod schemas untested (personas, prompt-studio), dashboard composite untested, session expiry E2E missing, toast store untested, router.tsx untested

**Stats:** 1,225 tests all pass, 22 E2E specs, AuthContext 19 tests (exemplary), WorkspaceContext 18 tests, API client 30+ tests

### Expert #11 — Accessibility WCAG (78%, CONDITIONAL FAIL)

**Major (5 categories):**
1. 11 inline modals: no role="dialog", aria-modal, focus trap
2. ~90 labels: no htmlFor (no programmatic association)
3. ~12 filter selects: no aria-label
4. ~12 tab UIs: no role="tablist"/role="tab" semantics
5. Form error associations incomplete in inline modals

**Minor (6):** CollapsibleSection missing aria-controls, ReactorGauge missing accessible name, footer not semantic, dashboard missing h1, duplicate modal IDs, hardcoded English strings

**Positive:** All color contrasts pass AA 4.5:1, focus-visible excellent, skip nav implemented, core modals (DetailModal/SideDrawer/ConfirmDialog) fully accessible, toast aria-live="polite", DataTable proper semantics, CommandPalette full keyboard support, ToggleSwitch role="switch"

### Expert #12 — DevOps (NOT READY)

**Critical (3):**
1. VITE_API_URL not injectable at build time (Docker image hardcoded to empty string)
2. Missing .dockerignore (leaks .env into build context)
3. CSP header only on HTML responses, not JS/CSS assets

**Major (5):** pnpm@latest non-deterministic, nginx runs as root, no CI/CD pipeline, no explicit sourcemap:false, CSP connect-src too restrictive for MCP URLs

> Current Reactor 1.1 admin policy note: this review is historical. The
> "no CI/CD pipeline" item is no longer an active remediation request. GitHub
> Actions are intentionally removed; release confidence comes from the local
> gates in `docs/admin-qa-checklist.md`, plus `test ! -d .github`,
> `pnpm verify:release-tags`, and `pnpm verify:package-scripts`.

**Minor (7):** No resource limits in docker-compose, no network config for backend, no logging config, X-XSS-Protection deprecated, no rate limiting, no request body size limit, no proxy timeout config

**Positive:** Multi-stage Docker build, health check present, frozen lockfile, SPA routing correct, HSTS present, aggressive asset caching, gzip enabled

### Expert #13 — Type Safety (8.5/10)

**Major (4):**
1. `as unknown as` double cast erases TenantAnalyticsSummary[] (usePlatformAdminData:126)
2. `as unknown as` erases AlertInstance[] (usePlatformAdminData:149)
3. `as unknown as` erases TenantQuotaResponse (useTenantAdminData:77)
4. Tenant Admin API 7 endpoints all return Record<string, unknown>

**Minor (5):** i18n count type hack (StatusBar), URL params cast to union without validation (SessionsFeed), status filter cast, parseJsonObject false safety, localStorage tags JSON.parse no shape validation

**Positive:** Zero `any` in production code, strict:true with all flags, excellent generics (DataTable<T>), robust MCP parsers with field-by-field validation, proper `as const` usage, clean barrel exports

### Expert #14 — Multi-tenancy (6.3/10, CONDITIONAL GO)

**High (1):** No queryClient.clear() on logout → cross-session data leakage

**Medium (3):**
1. No tenant ID in TanStack Query cache keys
2. Tenant-admin state persists across tenant switches (data misattribution)
3. Metric ingestion allows arbitrary tenantId in POST body

**Low (3):** Capability cache not tenant-scoped, CSV filenames contain tenant ID, localStorage keys not tenant-scoped (acceptable for admin tool)

**Critical (backend-dependent):** X-Tenant-Id header fully client-controlled — backend must validate

### Expert #15 — SSE/Streaming

**Major (3):**
1. No idle timeout on SSE streams (infinite hang if backend stalls)
2. 401 during streaming doesn't trigger auto-logout (fetchWithAuth not used)
3. SSE error events silently ignored in Chat Inspector

**Minor (4):** Duplicated SSE parsing logic (2 features with subtle differences), streamMessage grows without bound, null reader guard missing in PersonaPlayground, no stream test coverage

**Positive:** AbortController integration correct, component unmount cleanup proper, stream event buffer capped at 400

### Expert #16 — Business Logic

**Major (5):**
1. Approval mutation lacks onError → concurrent approvals get no feedback
2. handleConfirmApprove JSON parse error leaves actioning permanently locked
3. Disabled scheduler jobs still generate attention items
4. Approval API limit:200 with no truncation warning
5. Tool Policy delete has no confirmation dialog (security-critical)

**Minor (6):** Approval payloadCoverage zero-division ambiguity, scheduler stuckRunning semantics, retry validation too strict, output guard bank account regex overly broad, tool policy stableStringify loses objects, approval sort inconsistency

**State machine completeness:** Approvals 90%, Scheduler 85%, Output Guard 80%, Tool Policy 85%

### Expert #17 — Memory/Resources (92/100)

**Critical/Major: 0** — No resource leaks found

**Minor (5):** CommandPalette rAF uncancelled (harmless), FeedbackManager/ProactiveChannelsManager no async cancellation guard, SessionsFeed Map direct mutation, localStorage tag store orphans

**Positive:** All EventListeners properly paired, SSE double-guarded, error buffer capped at 100, QueryClient 5min GC appropriate, toast timeouts properly managed, global handlers intentional

**Long-session stability: STABLE (8+ hours)**

### Expert #18 — Observability (3/10)

**Critical (3):**
1. No error reporting backend (in-memory buffer only, lost on tab close)
2. No production source maps (minified stacks unreadable)
3. No error spike alerting

**Major (5):** No Web Vitals tracking, no API latency monitoring, no API health polling, error buffer never flushed (dead code), no user session context on errors

**Positive:** Console hygiene excellent (0 production leaks), ErrorBoundary comprehensive (app+section level on every page), global error handlers wired, error sanitization good, Docker HEALTHCHECK configured

**Minimum for deploy:** Sentry + hidden source maps + CSP update + alerts

### Expert #19 — Network Resilience (5.1/10)

**Critical (3):**
1. Session export .catch() missing → silent failure
2. Approval actions no idempotency → duplicate approval on network error
3. Emergency deny-all no retry → security action fails silently

**Major (5):** refetchOnReconnect:false (stale data after reconnect), 429 no handling, export 30s timeout too short, SSE no stream timeout, TenantAdmin Promise.all all-or-nothing failure

**Minor (4):** Forms preserved on error (good), login double-submit, bulk actions no dedup, AbortSignal inconsistent

### Expert #20 — Concurrency (5/10)

**Critical (2):**
1. Zero optimistic locking across entire codebase → all editable resources vulnerable to lost updates
2. Cross-tab token change not detected → identity mismatch (Admin A displayed, Admin B token used)

**Major (5):** Approval double-click (RC-16), scheduler trigger double-click (RC-18), MCP toggle dual instance race (RC-08), SessionsFeed Map direct mutation (RC-12), document candidate dual approval (RC-06)

**Minor (6):** Login double-submit, workspace cross-tab nav guard, pagination empty page after delete, persona delete during stream, multiple modal opens, MCP prefetch stale ref

---

## Deployment Decision

```
VERDICT: NOT READY → Fix P0 (10 items, ~5 hours) → CONDITIONAL GO

Strengths:
  ✓ React architecture solid (B+)
  ✓ Security foundation strong (8.5/10)
  ✓ Memory stable (92/100)
  ✓ IA/Permissions 3-layer defense working
  ✓ any 0, dangerouslySetInnerHTML 0
  ✓ 1,225 tests all passing

Weaknesses:
  ✗ DevOps deploy config incomplete
  ✗ Observability absent (3/10)
  ✗ Network resilience insufficient (5.1/10)
  ✗ Concurrency protection insufficient (5/10)
  ✗ Accessibility below AA (78%)
```

# CLAUDE.md

This file provides guidance for Claude Code when working in this repository.

## Language Policy

**All of the following must be written in English:**

- Code (variable names, function names, type names)
- Comments and documentation in source files
- Commit messages
- Pull request titles and descriptions
- PR review comments and code review feedback

User-facing UI text follows i18n policy and can be multilingual. Internal team chat can use any language, but all repository artifacts must default to English.

---

## Package Manager

**Always use `pnpm`.** Never use `npm` or `yarn`.

```bash
pnpm install             # install dependencies
pnpm dev                 # dev server (port 3001)
pnpm build               # tsc -b && vite build
pnpm lint                # eslint
pnpm verify:admin-api    # OpenAPI ↔ requirements.ts coverage check
pnpm verify:i18n         # ko.json must contain every t('...') key referenced in src/
```

---

## Tech Stack

| Category | Library |
|---|---|
| Framework | React 19.2.4 + Vite 7 + TypeScript 5.9 |
| Routing | react-router-dom v7 (`createBrowserRouter`) |
| Server state | TanStack Query v5 |
| Client state | Zustand v5 |
| Forms | react-hook-form v7 + zod v4 + @hookform/resolvers |
| HTTP | ky v1 |
| Charts | recharts |
| i18n | i18next + react-i18next (KO only) |
| React Compiler | babel-plugin-react-compiler (global / infer mode) |
| CSS | CSS Custom Properties — pure CSS, no Tailwind |

---

## Project Structure

```
src/
├── router.tsx          # Route config only (createBrowserRouter)
├── App.tsx             # Provider composition only (no route logic)
├── main.tsx            # Entry point
├── features/<name>/
│   ├── api.ts          # API calls only (uses ky instance)
│   ├── types.ts        # Type definitions
│   ├── schema.ts       # Zod schemas (form features only)
│   ├── store.ts        # Zustand store (UI state only, if needed)
│   ├── index.ts        # Public re-exports
│   └── ui/             # Feature components
├── pages/              # Route entry points (thin wrappers, SectionErrorBoundary wrapper)
├── widgets/layout/     # AdminLayout, Header, Sidebar
└── shared/
    ├── api/            # ky instance, token management
    ├── store/          # App-wide Zustand stores
    ├── i18n/           # ko.json, i18n config
    ├── lib/            # constants, formatters, queryKeys
    └── ui/             # Shared UI components (DataTable, StatCard, etc.)
```

---

## Working Principles

1. **Prefer TanStack Query** for all server state. Do not manage remote data with `useState` + `useEffect`.
2. **Never call `fetch` directly.** Use the `api` ky instance from `shared/api/client.ts` via `features/<name>/api.ts`.
3. **Use `react-hook-form` + `zod`** for any form. Schema goes in `features/<name>/schema.ts`.
4. **No hardcoded user-facing strings.** Always use `t('key')` and update `ko.json`.
5. **Do not add manual memoization** (`useMemo`, `useCallback`, `React.memo`) — the React Compiler handles this automatically for all files.
6. **`any` type is forbidden.** Use `unknown`, precise types, or generics instead.
7. **New routes go in `src/router.tsx` only.** Never write route config in `App.tsx`.

---

## Routing

`createBrowserRouter` (object config) + `RouterProvider`. Never use JSX `<Routes>/<Route>`.

```typescript
// router.tsx
export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <AdminLayout />,
    children: [
      { index: true, element: <FeatureRoute ...><DashboardPage /></FeatureRoute> },
      { path: 'personas', element: <FeatureRoute ...><PersonasPage /></FeatureRoute> },
      // ...
    ],
  },
])

// App.tsx — providers only
export default function App() {
  return (
    <AuthProvider>
      <WorkspaceProvider>
        <FeatureAvailabilityProvider>
          <RouterProvider router={router} />
        </FeatureAvailabilityProvider>
      </WorkspaceProvider>
    </AuthProvider>
  )
}
```

### Adding a new route — required steps

1. `src/features/capabilities/requirements.ts` → add endpoint to `ROUTE_REQUIREMENTS`
2. `src/features/workspace/navigation.ts` → add item to `navGroups` with `visibleTo: 'all' | AdminRole[]`
3. `src/router.tsx` → add route entry

---

## HTTP Client (ky)

Single `api` instance in `shared/api/client.ts`. Import it in `features/<name>/api.ts`.

**All list endpoints must include `searchParams: { limit: 200 }` by default** to prevent unbounded responses. If a function already accepts pagination params, merge the limit into existing searchParams.

```typescript
// shared/api/client.ts
export const api = ky.create({
  prefixUrl: `${import.meta.env.VITE_API_URL || ''}/api`,
  hooks: {
    beforeRequest: [(req) => { const token = getAuthToken(); if (token) req.headers.set('Authorization', `Bearer ${token}`) }],
    afterResponse: [(_req, _opt, res) => { if (res.status === 401 && getAuthToken() && onUnauthorized) onUnauthorized() }],
    beforeError: [async (err) => { /* converts HTTPError → ApiError | NetworkError */ throw err }],
  },
  retry: 0,
  timeout: 30000,
})

// SSE/streaming endpoints that ky cannot handle: use fetchWithAuth (raw fetch wrapper, also in client.ts)

// features/<name>/api.ts
import { api } from '../../shared/api/client'

export const listThings = (): Promise<Thing[]> => api.get('things').json()
export const createThing = (data: CreateThingInput): Promise<Thing> =>
  api.post('things', { json: data }).json()
```

---

## Data Fetching (TanStack Query v5)

```typescript
// Query
const { data, isLoading } = useQuery({
  queryKey: ['things', 'list'],
  queryFn: listThings,
})

// Mutation
const mutation = useMutation({
  mutationFn: createThing,
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['things'] }),
})
```

- Cache key convention: `['feature', 'list']` / `['feature', id]`
- Centralise query keys in `shared/lib/queryKeys.ts`

---

## Forms (react-hook-form + zod)

```typescript
// features/<name>/schema.ts
export const thingSchema = z.object({
  name: z.string().min(1, 'Required'),
})
export type ThingFormValues = z.infer<typeof thingSchema>

// component
const form = useForm<ThingFormValues>({ resolver: zodResolver(thingSchema) })
```

Server errors → `form.setError('root', { message: '...' })`

**Zod schemas must include `.max()` on all string fields** — name(255), description(2000), large text(50000). Use `t('common.validation.maxLength', { max: N })` for error messages.

**Form ARIA requirements:**
- `aria-invalid={!!errors.fieldName}` on inputs
- `aria-describedby={errors.fieldName ? "fieldName-error" : undefined}` on inputs
- `id="fieldName-error"` on error message elements
- `role="alert"` on error containers

---

## Client State (Zustand v5)

UI-only state (workspace mode, sidebar open, etc.). Never store server data in Zustand.

```typescript
// shared/store/workspace.store.ts
export const useWorkspaceStore = create<WorkspaceStore>((set) => ({
  mode: 'developer',
  setMode: (mode) => set({ mode }),
}))
```

---

## Auth

- JWT Bearer — `localStorage` key: `reactor-admin-token`
- Injected via ky `beforeRequest` hook; auto-logout on 401 via `afterResponse`
- Allowed roles: `ADMIN` / `ADMIN_MANAGER` / `ADMIN_DEVELOPER`
- Users without an admin role are blocked at login
- **Cross-tab sync:** `storage` event listener detects token removal in other tabs → auto-logout
- **Double-click prevention:** All submit buttons must include `disabled={isSubmitting || mutation.isPending}`

---

## Role-Based Visibility

Navigation items are filtered by `visibleTo: 'all' | AdminRole[]` based on the user's auth role. No manual workspace mode toggle — visibility is automatic.

| Role | Sees | Item Count |
|---|---|---|
| ADMIN | All 7 groups, all items | 28 |
| ADMIN_DEVELOPER | All 7 groups, all items | 28 |
| ADMIN_MANAGER | Today, Monitoring (no Traces), Usage, Tenants (read-only) | 8 |

**ADMIN-only "View as Manager" toggle:** ADMIN users see a preview button in the header that temporarily filters the sidebar to the ADMIN_MANAGER view. This does not change the auth role or token — it is a client-side visibility filter persisted to `localStorage` key `reactor-admin-view-as`.

**Security invariant:** Frontend role gating is UX only. Every dev-only route must have server-side role enforcement. Client checks are never the security boundary.

**Navigation groups (7):** Today, AI Configuration, Safety & Policy, Monitoring, Analytics, Administration, Dev Tools.

---

## React Compiler

Enabled globally in `vite.config.ts` via `babel-plugin-react-compiler` (infer mode — no directive needed). **Do not add `useMemo`, `useCallback`, or `React.memo` manually.** The compiler optimises all files automatically.

---

## i18n

- Supported locale: `ko` (Korean only)
- File: `src/shared/i18n/ko.json`
- Always use `t('key')` — never hardcode user-visible strings
- Add keys to `ko.json` as needed
- Missing keys render as the key string itself (i18next default; no throw, no console error)
- The `react-i18next` infrastructure remains so re-introducing additional locales later requires only adding new resource files and a toggle UI

### Korean Tone Policy

| Context | Ending | Example |
|---|---|---|
| User-facing errors / warnings / confirms / empty states / toasts | `~해요 / ~어요 / ~할까요?` | `삭제할까요?`, `세션이 만료됐어요` |
| Validation messages + immutable system facts | `~합니다 / ~입니다` | `필수 항목입니다`, `이름은 필수입니다` |
| Operator runbook bodies (technical reference) | `~합니다` acceptable | `백엔드 로그를 확인하세요` |

**Friendly Karrot/Toss tone for any copy the user can act on or recover from.** Formal declarative is reserved for hard system rules and operator-facing reference text where authority/precision matter more than warmth.

**`{{name}}` placeholder + 조사 antipattern:** Korean grammar requires 를/을·이/가·은/는 to match the noun's final consonant. User input names break this. Always put the 조사 BEFORE the placeholder (or use a noun phrase after it):

- Wrong: `"페르소나 \"{{name}}\"를 삭제할까요?"` (을 vs 를 fails on arbitrary input)
- Right: `"\"{{name}}\" 페르소나를 삭제할까요?"` (조사 attached to fixed noun)

### Loanword Policy

- **Keep loanwords for tech terms** that have no clean Korean equivalent: API, MCP, JSON, regex, manifest, cron, endpoint, namespace.
- **Drop code-switched English nouns** in body copy when a natural Korean word exists:
  - `feature wiring` → `기능 연결 설정`
  - `stale` → `오래된`
  - `backlog` → `대기열`
  - `surface` (when meaning "노출 범위") → `노출 범위`
  - `drift` → `불일치`
  - `allowlist` → `허용목록`

---

## Design System

### Brand Colour Reference (Reactor Admin Dashboard)

Engineering Craft aesthetic — dark, professional, data-focused. Core brand colour: warm amber/gold `#E0B85A`.

| Role | Value | Usage |
|---|---|---|
| Brand Primary | `#E0B85A` | Highlights, active nav, CTA buttons |
| Background | `#0C1017` | Root background |
| Surface | `#111820` | Headers, panels, cards |
| Elevated | `#182030` | Popups, dropdowns |
| Border | `#1E2A3A` | Dividers |
| Text Primary | `#F1F5F9` | Data values, headings |
| Text Secondary | `#CBD5E1` | Body text, descriptions |
| Text Muted | `#94A3B8` | Labels, captions |
| Text Dim | `#8899AC` | Inactive / hint text (WCAG AA ≥4.5:1 on #0C1017) |
| WARN | `#FBBF24` | Warnings |
| ERROR | `#F87171` | Errors |

UI Font: **Pretendard Variable** 400 / 500 / 600
Data Font: **IBM Plex Mono** 400 / 500 / 600

Sans-serif (Pretendard) for all UI text. Monospace (IBM Plex Mono) for numeric values, codes, and IDs only. Uppercase restricted to table headers, labels, and captions.

### Current Project CSS Tokens (`src/index.css`)

```css
--bg-root: #0C1017        /* root background */
--bg-surface: #111820     /* cards / panels */
--bg-elevated: #182030    /* popups / dropdowns */
--bg-hover: #1C2636       /* row / card hover */
--accent: #E0B85A         /* primary interaction (gold) */
--accent-hover: #ECC86A   /* accent hover state */
--accent-dim: rgba(224, 184, 90, 0.10)
--green: #34D399           /* success / active */
--yellow: #FBBF24          /* warning */
--red: #F87171             /* error / danger */
--blue: #60A5FA            /* info */
--text-primary: #F1F5F9
--text-secondary: #CBD5E1
--text-muted: #94A3B8
--text-dim: #8899AC
```

### Linear-Style Tokens (Stage A–G additions)

The full token catalogue lives in `DESIGN.md`. These are the families added during the Linear-style refinement cycle:

- **Borders** (translucent, structural): `--border-subtle`, `--border-standard`, `--border-strong`
- **Ghost button surfaces**: `--button-ghost-bg`, `--button-ghost-bg-hover`, `--button-ghost-bg-active`
- **Type emphasis**: `--font-weight-emphasis: 510` (signature weight) — replaces `font-weight: 500/600` for nav, buttons, table headers, labels
- **Type features**: `--font-features: "ss01", "ss02"` (Pretendard Latin alternates) on body
- **Semantic intent colors** (DESIGN.md §10): `--color-{success,warning,error,info,pending,attention,processing,neutral}` each with `-dim`, `-border`, `-muted` variants — drives `.badge-*` classes
- **Chart palette** (DESIGN.md §11, CB-safe): `--chart-1..4` (blue / green / violet / red) plus marker shape + dash conventions. Use `getLineSeriesProps` / `getAreaSeriesProps` from `shared/ui/ChartConfig` rather than hardcoding stroke colors.

---

## Shared Components & Hooks

Stage A–G introduced reusable primitives under `src/shared/ui/` and `src/shared/lib/`. **Always reuse these before creating a new component.**

### UI Components (`src/shared/ui/`)

| Component | Purpose |
|---|---|
| `DataTable` | Sortable, paginated, optionally resizable / responsive / URL-synced / exportable table (see "DataTable opt-in props" below) |
| `Skeleton`, `SkeletonText`, `SkeletonCard`, `SkeletonTable`, `SkeletonChart` | Loading placeholders, reduced-motion aware |
| `LiveAnnouncer` + `LiveAnnouncerProvider` + `useAnnouncer` | `aria-live` polite/assertive surface for filter / CRUD / bulk results |
| `OverlayCloseButton` | Standard 32×32 hit target with 16×16 ✕ for modals, drawers |
| `StepProgress` | 1→N step wizard indicator (done / active / pending) |
| `FieldStatusIndicator` | Form field state badge (idle / validating / valid / error) |
| `ReadinessStrip` | Inline readiness checks (token / HMAC / URL / preflight signals) |
| `OperationButton` | Async-aware button with loading / success / error states, used for risky operator actions |
| `CommandPalette` + `commandPaletteActions` | ⌘K palette with role-gated action registry; emits `cmd-palette:create` events for list pages |
| `PageHelpOverlay` + `usePageHelp` | Per-page help / shortcut overlay (`?` to open) |
| `SavedViewsControl` | Per-table saved filter / sort presets |
| `RowContextMenu` | Right-click + `⋮` hover trigger + `Shift+Enter` keyboard menu for table rows |
| `ChartConfig` (helpers) | `CHART_PALETTE`, `CHART_SEQUENCE`, `CHART_AXIS_STYLE`, `CHART_GRID_STYLE`, `getLineSeriesProps`, `getAreaSeriesProps`, marker shape utilities |
| `SectionErrorBoundary`, `ErrorBoundary`, `ErrorFallback` | Error containment — wrap every page and large modal |
| Existing primitives (still preferred) | `StatCard`, `StatusBadge`, `EmptyState`, `ConfirmDialog`, `DetailModal`, `SideDrawer`, `Tabs`, `ToggleSwitch`, `RefreshButton`, `LoadingSpinner`, `ToastContainer`, `PageBanner`, `PageSuspense`, `ChartTooltip`, `ReactorGauge`, `WaterfallTimeline`, `PercentileChart`, `PipelineFlow`, `DateRangePicker`, `SparkLine`, `BucketDistribution`, `CollapsibleSection`, `NetworkStatus`, `TableSkeleton`, `DetailSkeleton` |

### Hooks (`src/shared/lib/`)

| Hook | Purpose |
|---|---|
| `useEscapeClose` | Unified ESC handler for modals / drawers / popovers |
| `useFocusTrap` | Focus containment within an overlay |
| `useDebouncedValue` | 250 ms debounce utility for search / live validation inputs |
| `useFieldStatus` | Derives form field status from `react-hook-form` state |
| `useUrlState` | `useSearchParams`-backed namespaced state (page / sort / filters) |
| `useAnnouncer` (re-export from `LiveAnnouncer`) | Imperative `aria-live` announcement |
| `usePageHelp` | Per-page help registration for `PageHelpOverlay` |
| `useTableExport` | CSV / JSON download helper used by DataTable's `exportable` prop |
| Existing hooks (still preferred) | `useEscapeKey`, `useUnsavedChanges`, `useClockDisplay`, `useBodyOverflowLock`, `useCountUp` |

When creating new shared primitives, place them under `shared/ui/` (visual) or `shared/lib/` (logic), export from the matching `index.ts`, and update `DESIGN.md` if it introduces a visual pattern.

---

## DataTable opt-in props

`DataTable` ships with conservative defaults; the following props opt rows / columns into the Stage A–G enhancements. All are non-breaking — existing call sites keep working unchanged.

| Prop | Scope | Behaviour |
|---|---|---|
| `truncate?: boolean` | per-column | Single-line CSS truncation + `title` attribute on string cell values (default `true`). Set `false` to render full multi-line content. |
| `resizable?: boolean` | per-column | Adds a header drag handle plus `ArrowLeft`/`ArrowRight` keyboard resize. Widths persist to `reactor-admin-datatable-{tableId}-widths` when `tableId` is set. |
| `responsivePriority?: number` | per-column | At ≤900px, columns with priority ≥3 are hidden from the main table and surfaced inline via a per-row `▸ Details` expander. Lower numbers stay visible. |
| `urlStateKey?: string` | table-level | Mirrors `page` / `sortKey` / `sortDirection` to URL search params (`{key}_p`, `{key}_s`, `{key}_d`) using `replace: true`, so back-navigation stays clean. |
| `exportable?: { filename, columns?, fallbackEmpty? }` | table-level | Renders a CSV / JSON export menu in the table toolbar via `useTableExport`. Auto-derives columns from visible `columns` (skips `excludeFromExport`); `exportAccessor` overrides ReactNode renders. |
| `rowActions?: RowAction<T>[]` | table-level | Surfaces row-level actions through `RowContextMenu` (right-click, `⋮` hover, `Shift+Enter`). |
| `selectable?: boolean` + `bulkActions?: BulkAction<T>[]` + `rowSelectable?: (row) => boolean` + `keepSelectionAcrossDataChange?: boolean` | table-level | Renders a leading checkbox column plus a sticky bulk-action bar when ≥1 row is selected. Shift+Click extends a contiguous range. `BulkAction` supports `variant`, `icon`, `hidden`, `disabled`, and `confirmMessage` (auto-wires `ConfirmDialog`). Selection clears on data refresh by default; opt out via `keepSelectionAcrossDataChange`. |

Per-column `exportAccessor` and `excludeFromExport` further refine `exportable` behaviour — see `Column<T>` JSDoc in `src/shared/ui/DataTable.tsx`.

---

## Development Workflow

### Git Workflow

All work uses the Reactor repository's feature branches and pull requests:

1. **Create worktree** — create it from the Reactor repository root
2. **Develop** — feature-unit commits on the branch
3. **Create PR** — `gh pr create`
4. **Merge** — merge to main after review
5. **Cleanup** — remove worktree and delete branch

Never commit directly to `main`. Every change goes through a PR.

**Direct push to `main` is strictly forbidden.** Do not run `git push origin main` under any circumstances — not even for "small fixes" or "hotfixes". All changes must go through a feature branch → PR → merge workflow.

### Development Process

Follow this strict order for every feature:

1. **Planning** — Define requirements, ask questions, clarify scope. Never assume — always ask when uncertain. If the user's reasoning seems flawed, push back with explanation.
2. **Design** — UI/UX design before code. Think from the user's perspective.
3. **Development** — Implement with tests alongside code.

### Testing Policy

- **Unit / integration tests are mandatory** for every feature — no exceptions
- **All tests must pass before any PR can be merged** — `pnpm test` must exit 0
- **E2E tests** must run after all development is complete
- No feature is considered done without passing tests
- **Test gate in workflow:** `pnpm test` is a required quality gate alongside `pnpm lint` and `pnpm build`
- **No repository CI:** GitHub Actions workflows are intentionally absent. Put the
  exact local verification commands and results in each PR body.
- **Coverage targets** (enforced by `vitest.config.ts` thresholds): Lines ≥75%, Statements ≥72%, Branches ≥65%, Functions ≥58%. Current (April 2026): Lines 78.08%, Statements 74.17%, Branches 67.82%, Functions 60.28%

```bash
pnpm test               # all unit/integration tests must pass
pnpm test:coverage      # check coverage thresholds
pnpm test:e2e           # E2E after all development (133 specs, Playwright + Chromium)
```

### E2E Test Conventions (`e2e/`)

- **URL matching in mocks:** Always use `requestUrl.pathname` (not full URL string) — query params like `?limit=200` break `url.endsWith()` matching
- **Tab selectors:** Use `getByRole('tab')` not `getByRole('button')` for tabs with `role="tab"`
- **StatCard labels:** Rendered in uppercase — match with `.toUpperCase()` or CSS selector

### UX / Design Principles

- Admin UI must be **user-centric** — comfortable for admins and developers
- Follow **Karrot (당근) / Toss** UX philosophy: intuitive, minimal friction, deeply considered
- **Brand-consistent** — only use project brand colors and fonts (see Design System section)
- **Prohibited**: AI-looking design (gradient neon, futuristic sci-fi), generic admin panel aesthetics, mismatched colors/fonts
- **"Quiet Authority"** design direction — clean, professional, no terminal cosplay or ASCII art. Reference: Linear, Vercel login pages

### Error Resilience

- **Every page must be wrapped with `<SectionErrorBoundary name="page-name">`** — prevents full app crash from component errors
- **`window.onerror`** handler in `main.tsx` captures uncaught synchronous errors via `errorLogger`
- **`window.addEventListener('unhandledrejection')`** captures async errors
- Large modals should wrap content with `<SectionErrorBoundary>` (e.g., RegisterServerModal, GlobalSettingsModal)

### Accessibility (WCAG AA)

- **Color contrast:** All text must achieve ≥4.5:1 contrast ratio against background
- **Skip navigation:** `<a href="#main-content">` as first focusable element in AdminLayout
- **Tables:** `scope="col"` on `<th>`, `aria-sort` on sortable columns, `aria-live="polite"` on pagination
- **Dynamic content:** `aria-live="polite"` on toast containers and status updates
- **Status indicators:** Never rely on color alone — include `aria-label` and `title` on status dots

---

## Quality Gates

All must pass before a PR can be merged:

```bash
pnpm test              # all tests pass (0 failures)
pnpm lint              # 0 errors, 0 warnings
pnpm build             # no build errors (main chunk < 500KB)
pnpm verify:admin-api  # no missing or extra API coverage
pnpm verify:i18n       # no missing i18n keys (ko.json contains every t('...') referenced in src/)
pnpm test:e2e          # E2E pass (run after all dev complete)
```

---

## Security

- Only admin roles (`ADMIN`, `ADMIN_MANAGER`, `ADMIN_DEVELOPER`) may access this app
- **Frontend role gating is UX only.** Every dev-only or manager-restricted route must have server-side role enforcement. Client-side `visibleTo` filtering in `navigation.ts` hides UI elements but is never the security boundary. Backend must return 403 for unauthorized role + endpoint combinations.
- MCP server registration is admin-only — never add user self-registration paths
- Do not expose user-identifying information (email, name) in list views
- Never use `dangerouslySetInnerHTML`

---

## Build Optimization

Vendor chunking is configured in `vite.config.ts` via `manualChunks`. Stable vendor libraries are split into separate chunks for better caching:

- `vendor-react`: react, react-dom, react-router-dom
- `vendor-query`: @tanstack/react-query
- `vendor-form`: react-hook-form, @hookform/resolvers
- `vendor-i18n`: i18next, react-i18next
- `vendor-ky`: ky
- `vendor-zustand`: zustand

When adding new large dependencies, consider adding them to `manualChunks` to keep the main bundle under 500KB.

---

## Deployment

- `Dockerfile` is app-local; the repository root owns `docker-compose.yml`
- `nginx.conf`: SPA routing (`try_files $uri /index.html`)
- Env var: `VITE_PROXY_TARGET` (backend proxy target URL)

---

## PR Checklist

Before submitting a pull request:

- [ ] No route or auth regression
- [ ] Loading / error / empty states handled
- [ ] Page wrapped with `<SectionErrorBoundary>`
- [ ] No missing i18n keys in `ko.json`
- [ ] Form inputs have `aria-invalid` + `aria-describedby` for errors
- [ ] Submit buttons have `disabled` during submission
- [ ] List API calls include `searchParams: { limit: 200 }`
- [ ] Zod schemas have `.max()` on string fields
- [ ] `pnpm lint` + `pnpm build` + `pnpm test` + `pnpm verify:admin-api` + `pnpm verify:i18n` all pass
- [ ] New routes declared in `requirements.ts` and `navigation.ts`
- [ ] Visual changes follow `DESIGN.md` — use design tokens (`--border-*`, `--button-ghost-*`, `--font-weight-emphasis`, semantic `--color-*`, chart palette helpers); no hardcoded hex values, no `font-weight: 700+`, no inline drop shadows
- [ ] Reused existing shared components / hooks where applicable (see "Shared Components & Hooks" above)
- [ ] Docs updated if behaviour changed

---

## Reference Docs

- `DESIGN.md` (project root) — Full design system: tokens, typography, components, semantic colors (§10), chart palette (§11). Single source of truth for visual decisions.
- `AGENTS.md` (project root) — Conventions for Claude Code / AI coding agents (workflow, boundaries, reuse-first policy).
- `README.md` (project root) — Quick start and high-level project intro.
- `docs/prd/reactor-admin-prd.md` — Full PRD
- `docs/admin-workspace-policy.md` — Role-based visibility policy (originally "Manager / Developer mode" — predates the role-driven model documented above; refer to "Role-Based Visibility" in this file for the current state)
- `docs/admin-qa-checklist.md` — QA checklist
- `../../docs/` — Reactor architecture, harness, and release contracts

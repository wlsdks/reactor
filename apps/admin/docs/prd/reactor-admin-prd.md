# Reactor Admin Product Requirements

> **Last verified: 2026-03 snapshot.** Sections 3.3 (Workspace Mode) and 5 (Feature Matrix)
> reflect the original 4-group / 15-item navigation. The current implementation uses
> **automatic role-based visibility** with **7 groups / 27 items** for `ADMIN` and
> `ADMIN_DEVELOPER`, and 8 items for `ADMIN_MANAGER` — see `CLAUDE.md` →
> "Role-Based Visibility" for the live matrix. The dependency table in §2 also predates
> Stage A–G additions (`@sentry/react`, `lucide-react`, `sonner`, `react-window`,
> `@xyflow/react`, `d3-force`); see `package.json` for the canonical list.
> The architectural principles, data layer rules, and quality gates remain accurate.

## 1. Overview

**Reactor Admin** is the operator and developer management console for the Reactor AI agent platform.
It is a single-page application built with React 19 + Vite 7, providing configuration, monitoring, and diagnostics for the entire platform.

---

## 2. Tech Stack

### Package Manager

- **pnpm only** — `npm` and `yarn` are prohibited

### Build Environment

- Dev server: `localhost:3001`
- Backend proxy: `VITE_PROXY_TARGET` env var (default `http://localhost:18081`)
- Proxied paths: `/api/*` and `/v3/api-docs/*`
- Env vars: handled natively by Vite (`import.meta.env.VITE_*`) — no dotenv library needed

### Dependencies

| Package | Version | Role |
|---|---|---|
| `react` | 19.2.4 | UI rendering |
| `react-dom` | 19.2.4 | DOM rendering |
| `react-router-dom` | ^7.6.3 | SPA routing (v7, `createBrowserRouter`) |
| `ky` | ^1.14.3 | HTTP client |
| `@tanstack/react-query` | ^5.90.21 | Server state cache |
| `zustand` | ^5.0.11 | Client UI state |
| `react-hook-form` | ^7.71.2 | Form state management |
| `@hookform/resolvers` | ^5.2.2 | zod ↔ react-hook-form adapter |
| `zod` | ^4.3.6 | Schema validation |
| `recharts` | ^2.15.3 | Dashboard charts |
| `i18next` | ^25.8.4 | i18n (ko) |
| `react-i18next` | ^16.5.4 | React i18n bindings |

### Dev Dependencies

| Package | Version | Role |
|---|---|---|
| `vite` | ^7.2.4 | Build tool |
| `babel-plugin-react-compiler` | ^1.0.0 | React Compiler (global infer mode) |
| `@vitejs/plugin-react` | ^5.1.1 | React Fast Refresh |
| `typescript` | ~5.9.3 | Static typing (strict) |
| `eslint` | ^9.39.1 | Linting (flat config v9) |
| `eslint-plugin-react-hooks` | ^7.0.1 | Hooks rules |
| `eslint-plugin-react-refresh` | ^0.4.24 | HMR rules |
| `typescript-eslint` | ^8.46.4 | TS lint rules |

---

## 3. Architecture

### 3.1 Folder Structure (Feature-Sliced Design)

```
src/
├── router.tsx            # Route config only (createBrowserRouter)
├── App.tsx               # Provider composition only
├── main.tsx              # Entry point
├── features/<name>/
│   ├── api.ts            # API calls only (ky instance)
│   ├── types.ts          # Type definitions
│   ├── schema.ts         # Zod schemas (form features only)
│   ├── store.ts          # Zustand store (UI state only, if needed)
│   ├── index.ts          # Public re-exports
│   └── ui/               # Feature components
├── pages/                # Route entry points (thin wrappers)
├── widgets/layout/       # AdminLayout, Header, Sidebar
└── shared/
    ├── api/              # ky instance, token management
    ├── store/            # App-wide Zustand stores
    ├── i18n/             # ko.json
    ├── lib/              # constants, formatters, queryKeys
    └── ui/               # Shared UI components
```

### 3.2 Authentication

- JWT Bearer token — stored in `localStorage` as `reactor-admin-token`
- Auto-injected via ky `beforeRequest` hook
- Auto-logout on 401 via ky `afterResponse` hook
- Allowed roles: `ADMIN` / `ADMIN_MANAGER` / `ADMIN_DEVELOPER`
- Users without an admin role are blocked at login

### 3.3 Workspace Mode

| Mode | Audience | Visible routes |
|---|---|---|
| Manager View | Operations staff | 7 sidebar items (Operations + Monitoring groups) |
| Developer Console | Engineers | All 15 sidebar items (4 groups) |

- Toggled from the Header
- New routes must declare `audience` before release

---

## 4. Data Layer

### 4.1 HTTP Client (ky)

- Single `api` instance in `shared/api/client.ts`
- `beforeRequest` hook: injects Authorization header
- `afterResponse` hook: triggers auto-logout on 401
- Direct `fetch` calls are forbidden

### 4.2 Server State (TanStack Query v5)

- All API data managed via `useQuery` / `useMutation`
- Cache key convention: `['feature', 'list']` / `['feature', id]`
- `useState` + `useEffect` fetch pattern is forbidden

### 4.3 Client State (Zustand v5)

- UI-only global state (workspace mode, sidebar, etc.)
- Never store server data in Zustand

### 4.4 Forms (react-hook-form + zod)

- All forms: `useForm` + `zodResolver`
- Schema defined in `features/<name>/schema.ts`
- Server errors: `form.setError('root', { message: '...' })`

### 4.5 React Compiler

- `babel-plugin-react-compiler` enabled globally in `vite.config.ts` (infer mode)
- All files are optimised automatically — **no manual memoization** (`useMemo`, `useCallback`, `React.memo`)

---

## 5. Feature Matrix

### Sidebar Routes (15 items)

**Operations (audience: all)**

| Route | Feature | Backend endpoint |
|---|---|---|
| `/` | Dashboard | `/api/ops/dashboard` |
| `/issues` | Issues | `/api/issues` |
| `/approvals` | Approvals | `/api/approvals` |
| `/platform-admin` | Platform Admin | `/api/admin/platform/*` |

**AI Config (audience: developer)**

| Route | Feature | Backend endpoint |
|---|---|---|
| `/personas` | Personas | `/api/personas` |
| `/prompt-studio` | Prompt Studio | `/api/prompt-templates` |
| `/documents` | Documents | `/api/documents`, `/api/rag-ingestion/candidates` |
| `/safety-rules` | Safety Rules | `/api/output-guard/rules` |

**Monitoring (audience: all)**

| Route | Feature | Backend endpoint |
|---|---|---|
| `/sessions` | Sessions | `/api/sessions` |
| `/feedback` | Feedback | `/api/feedback` |
| `/audit` | Audit Log | `/api/admin/audits` |

**Dev Tools (audience: developer)**

| Route | Feature | Backend endpoint |
|---|---|---|
| `/mcp-servers` | MCP Servers | `/api/mcp/servers` |
| `/chat-inspector` | Chat API Diagnostics | `/api/chat` |
| `/integrations` | Integration Diagnostics | `/api/slack/*`, `/api/error-report` |
| `/scheduler` | Scheduler | `/api/scheduler/jobs` |

### Non-Sidebar Routes (URL access or redirects)

| Route | Feature | Note |
|---|---|---|
| `/intents` | Intents | Direct URL access only |
| `/metrics-ingestion` | Metrics Ingestion | Direct URL access only |
| `/mcp-security` | MCP Security | Redirects |
| `/output-guard` | Output Guard | Redirects |
| `/tool-policy` | Tool Policy | Redirects |
| `/tenant-admin` | Tenant Admin | Redirects |
| `/proactive-channels` | Proactive Channels | Redirects |

---

## 6. Design System

See `CLAUDE.md` "Design System" section for the current brand colour reference, CSS tokens, and font policy. That file is the single source of truth for design tokens and is kept in sync with `src/index.css`.

---

## 7. i18n

- Supported locales: `ko`
- Files: `src/shared/i18n/ko.json`
- All user-facing strings must use `t('key')` — hardcoding is forbidden

---

## 8. API Coverage Verification

```bash
pnpm verify:admin-api
```

- Runs `scripts/verify-admin-api-coverage.mjs`
- Compares OpenAPI spec (`/v3/api-docs`) against `requirements.ts`
- Every new route must declare its endpoints in `ROUTE_REQUIREMENTS`

---

## 9. Quality Gates

```bash
pnpm lint              # 0 errors, 0 warnings
pnpm test              # 0 failures
pnpm build             # no build errors (main chunk < 500 kB)
pnpm verify:admin-api  # 100% API coverage
pnpm verify:i18n       # 0 missing keys in ko.json
pnpm test:e2e          # Playwright + Chromium (run after dev complete)
```

- ESLint flat config (v9), TypeScript strict mode
- React Hooks rules strictly enforced
- Coverage targets: lines ≥90%, branches ≥75%

---

## 10. Security

- Only `ADMIN`, `ADMIN_MANAGER`, `ADMIN_DEVELOPER` roles may access this app
- MCP server registration is admin-only — no user self-registration paths
- Minimise exposure of user-identifying information
- Auto-logout on 401
- `dangerouslySetInnerHTML` is forbidden

---

## 11. Deployment

- `Dockerfile` + `docker-compose.yml` included
- `nginx.conf`: SPA routing (`try_files $uri /index.html`)
- Build command: `tsc -b && vite build`

---

## 12. Backlog

1. **Backend role hardening** — `ADMIN_MANAGER` / `ADMIN_DEVELOPER` scopes are now returned from `/api/auth/me` (delivered)
2. **Server-side route enforcement** — partial: backend now enforces scope on critical routes; remaining dev-only routes still need backend guards
3. **Test coverage** — Vitest unit / integration suite is live (lines ≥90%, branches ≥75% targets enforced); E2E via Playwright (`pnpm test:e2e`)
4. **Design token tooling** — evaluate structured design token system beyond CSS custom properties (open)

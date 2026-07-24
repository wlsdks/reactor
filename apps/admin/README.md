# Reactor Admin Web

Operator and developer console for the **Reactor** AI agent platform. This is a
modular edge application inside the Reactor monorepo: it owns browser UX and
client-side presentation, while the FastAPI backend owns authentication,
authorization, policy, tenancy, and durable state.

## Quick Start

```bash
pnpm install   # from apps/admin; pnpm only
pnpm dev       # dev server on http://localhost:3001
```

By default the dev server proxies `/api/*` and `/v3/api-docs/*` to
`http://localhost:8000`. Override it with `VITE_PROXY_TARGET`.

## Common Scripts

```bash
pnpm build              # tsc -b && vite build (main chunk budget: 500 kB)
pnpm lint               # eslint flat config — must be 0 errors
pnpm test               # vitest run — must be 0 failures
pnpm test:coverage      # coverage targets: lines ≥90%, branches ≥75%
pnpm test:e2e           # Playwright + Chromium
pnpm verify:admin-api   # strict FastAPI method/path ↔ client/route coverage
pnpm verify:i18n        # ko.json must contain every t('...') key referenced in src/
pnpm verify:package-scripts # package scripts must stay on pnpm, not npm/yarn
pnpm verify:release-tags # verifies the current v1.2.0 release tag locally and remotely
```

Local quality gates (`lint`, `build`, `test`, `verify:admin-api`, `verify:i18n`,
`verify:package-scripts`, and `verify:release-tags`) must pass before any PR can merge.

## Reference Docs

- `CLAUDE.md` — Architecture, routing, data layer, role-based visibility, shared components, PR checklist (start here for human contributors)
- `AGENTS.md` — Conventions for Claude Code / AI coding agents (workflow, boundaries, reuse-first policy)
- `DESIGN.md` — Design system: tokens, typography, components, semantic colors (§10), chart palette (§11)
- `docs/prd/reactor-admin-prd.md` — Full product requirements
- `docs/admin-workspace-policy.md` — Role / route audience matrix
- `docs/admin-qa-checklist.md` — QA checklist
- `../../docs/` — product architecture and operating contracts

## Live Operator Stack

When the local operator stack (Reactor + optional MCP servers + admin dev server) is running, you can run live smoke tests against it:

```bash
pnpm test:e2e:live          # E2E against live admin UI
pnpm verify:operator:live   # API-only contract checks (actuator, capabilities, MCP, scheduler, etc.)
pnpm verify:operator:stack  # API checks then UI smoke
```

Defaults:

- Admin UI: `http://127.0.0.1:4174` (override with `PLAYWRIGHT_BASE_URL`)
- Backend API: `http://127.0.0.1:8000` (override with `OPERATOR_STACK_API_BASE`)
- Login: `admin@example.com` / `admin1234` (override with `PLAYWRIGHT_LIVE_ADMIN_EMAIL` / `PLAYWRIGHT_LIVE_ADMIN_PASSWORD` or `OPERATOR_STACK_ADMIN_EMAIL` / `OPERATOR_STACK_ADMIN_PASSWORD`)

Tighten policy expectations with comma-separated env vars when needed:

- `OPERATOR_STACK_SWAGGER_SOURCES`
- `OPERATOR_STACK_JIRA_KEYS`
- `OPERATOR_STACK_CONFLUENCE_KEYS`
- `OPERATOR_STACK_BITBUCKET_REPOS`

## Monorepo commands

From the repository root, prefix commands with `pnpm --dir apps/admin`, for
example `pnpm --dir apps/admin verify:admin-api`. The API coverage check resolves
the Reactor backend from the monorepo root automatically.

## Deployment

The app-local `Dockerfile` and `nginx.conf` define the web image. The repository
root `docker-compose.yml` owns full-stack orchestration.

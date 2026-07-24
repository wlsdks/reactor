# Admin Workspace Policy

> **Last verified: 2026-07-09** — aligned with the role-driven navigation model.
>
> Navigation visibility is driven by the authenticated admin role
> (`ADMIN` / `ADMIN_DEVELOPER` / `ADMIN_MANAGER`). `ADMIN` users may temporarily
> preview the manager view through the header "View as Manager" control, persisted
> to `localStorage` key `reactor-admin-view-as`; this does not change the auth token or
> backend scope.
>
> Current sidebar shape:
>
> | Role | Sidebar shape |
> | --- | --- |
> | `ADMIN`, `ADMIN_DEVELOPER` | 8 groups. The v1.1 Release operations group contains release cockpit, RAG ingest, RAG lifecycle, feedback promotion, eval/LangSmith sync, live smoke, and provider smoke. |
> | `ADMIN_MANAGER` | 8 items in 3 groups: Today at a glance, Usage, Organization. |
>
> Source of truth: `src/features/workspace/navigation.ts` plus
> `src/shared/releaseWorkflow.ts`. Audience policy lives on each item's
> `visibleTo: 'all' | AdminRole[]` field. Backend capability gating lives in
> `src/features/capabilities/requirements.ts` and normalizes query/hash deep links
> to their base route.

## Goal
Split the admin experience into two explicit modes without changing backend APIs:

- `Manager View`: monitor service status with low technical complexity.
- `Developer Console`: configure, debug, and operate all admin features.

## Current Boundary
Backend roles:

- `ADMIN`: full access
- `ADMIN_DEVELOPER`: developer/admin control surfaces
- `ADMIN_MANAGER`: manager dashboard surfaces

Frontend navigation grouping follows the role. Backend scope and capability
checks remain the security boundary; the sidebar is only a discoverability layer.

## Current Route Audience Matrix

### Developer Sidebar Groups

`ADMIN` and `ADMIN_DEVELOPER` see these 8 groups:

| Group | Routes |
| --- | --- |
| Today | `/`, `/health`, `/issues`, `/approvals` |
| AI Config | `/personas`, `/prompt-studio`, `/reactor-universe` |
| Release operations | `/#release-cockpit`, `/documents?tab=ingestion#documents-tabpanel-ingestion`, `/rag-cache?tab=rag#rag-lifecycle`, `/feedback#feedback-promotion`, `/evals#eval-regression`, `/integrations#release-smoke`, `/models#provider-smoke` |
| Safety & Policy | `/safety-rules`, `/input-guard`, `/access-control` |
| Monitoring | `/sessions`, `/traces`, `/audit` |
| Analytics | `/performance`, `/usage` |
| Administration | `/tenants`, `/retention`, `/settings` |
| Dev Tools | `/mcp-servers`, `/chat-inspector`, `/scheduler`, `/metrics-ingestion`, `/debug-replay` |

### Manager Sidebar Groups

`ADMIN_MANAGER` sees these 8 items in 3 groups:

| Group | Routes |
| --- | --- |
| Today at a glance | `/`, `/health`, `/issues`, `/approvals` |
| Usage | `/sessions`, `/feedback`, `/usage` |
| Organization | `/tenants` |

### Historical 2026-03 Matrix

The older mode-toggle matrix is retained below only to explain earlier product
intent. It is not the current source of truth.

**Operations (4) — historical shared group:**

| Route | Audience | Why |
|---|---|---|
| `/` | all | Primary operations dashboard |
| `/issues` | all | Issue tracking and triage |
| `/approvals` | all | Workflow approvals |
| `/platform-admin` | all | Platform-level control surface |

**AI Config (4) — developer only:**

| Route | Audience | Why |
|---|---|---|
| `/personas` | developer | Prompt/persona authoring |
| `/prompt-studio` | developer | Prompt experimentation and versioning |
| `/documents` | developer | RAG document pipeline |
| `/safety-rules` | developer | Safety rule operations |

**Monitoring (3) — visible in both modes:**

| Route | Audience | Why |
|---|---|---|
| `/sessions` | all | Conversation diagnostics |
| `/feedback` | all | Quality signal triage |
| `/audit` | all | Audit/compliance inspection |

**Dev Tools (4) — developer only:**

| Route | Audience | Why |
|---|---|---|
| `/mcp-servers` | developer | Central MCP inventory and connection operations |
| `/chat-inspector` | developer | API-level chat diagnostics |
| `/integrations` | developer | Slack/error-report integration diagnostics |
| `/scheduler` | developer | Job automation setup |

### Non-Sidebar Routes (URL access only)

These routes exist in the router but are not shown in sidebar navigation:

| Route | Note |
|---|---|
| `/metrics-ingestion` | Direct URL access only |
| `/mcp-security` | Redirects |
| `/output-guard` | Redirects |
| `/tool-policy` | Redirects |
| `/tenant-admin` | Redirects |
| `/proactive-channels` | Redirects |
| `/intents` | Redirects to `/prompt-studio` |

## UX Rules

1. Manager mode exposes dashboard-only read-safe flows.
2. MCP registration and credential inputs are always central admin operations.
3. Advanced filter/diagnostic controls should default to collapsed even in shared dashboard screens.
4. Any new route must declare `visibleTo` before release.
5. Release workflow entries that use query/hash deep links must share capability
   requirements with their base route.

## Follow-up (Backend Hardening)

1. Keep `ADMIN_MANAGER` / `ADMIN_DEVELOPER` role scopes returned from `/api/auth/me`.
2. Enforce route capability server-side, not only in UI.
3. Keep the release operations group aligned with Reactor release readiness gates.

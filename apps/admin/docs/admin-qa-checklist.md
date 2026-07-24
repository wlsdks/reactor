# Admin Revamp QA Checklist

> **Last verified: 2026-07-09** — matches the role-driven navigation model.
> `ADMIN` and `ADMIN_DEVELOPER` see the developer taxonomy with 8 sidebar groups,
> including the v1.1 **Release operations** group. `ADMIN_MANAGER` sees 8 items in
> 3 manager-specific groups. `ADMIN` users can preview the manager view through the
> "View as Manager" header control; this is a client-side preview only and does not
> change the auth role.

## 1) Workspace Split

1. As `ADMIN`, enable the "View as Manager" preview in the header.
2. Confirm sidebar shows 8 items in 3 groups: Today at a glance, Usage, Organization.
3. Enter a developer-only URL manually (for example `/mcp-servers`) and confirm the permission-denied page explains the role boundary.
4. Disable the preview and confirm the developer sidebar returns with 8 groups, including Release operations.

## 2) Dashboard

1. In manager mode, confirm only high-level health information is shown.
2. In developer mode, confirm advanced metric filter and raw metric table are visible.
3. Confirm MCP status visualization renders with and without data.
4. Confirm generated timestamp and language labels render correctly in `ko`.

## 3) Manager View Boundaries

1. In manager mode, confirm 8 routes are reachable from navigation: `/`, `/health`, `/issues`, `/approvals`, `/sessions`, `/feedback`, `/usage`, `/tenants`.
2. Enter a developer-only URL (e.g. `/personas`) manually and confirm the permission-denied page explains the role boundary.
3. Switch back to developer mode and confirm the hidden routes are visible again.

## 4) Release Operations

1. In developer mode, confirm the Release operations group appears with steps 1-7.
2. Confirm the release steps open: Release cockpit, RAG ingestion, RAG lifecycle, feedback promotion, eval/LangSmith sync, live smoke, provider smoke.
3. Confirm deep links with query/hash fragments still respect backend capability gating.

## 5) Sessions (Large Volume)

1. Open a session with many messages.
2. Confirm detail panel starts with recent messages only.
3. Click `Load older messages` repeatedly and verify no UI freeze.
4. Confirm exports (`JSON`, `Markdown`) still work.

## 6) MCP Operations Language

1. Confirm central management notice is visible.
2. Confirm transport help text explains `SSE`, `STDIO`, `STREAMABLE_HTTP`.
3. Confirm access policy save/reset feedback appears.

## 7) Global i18n and Style

1. Confirm all user-facing copy renders in Korean across every updated page.
2. Confirm no major clipping or overlap in 1440px and mobile widths.
3. Confirm new cards/charts/details use consistent spacing and color tokens.

## 8) Verification Loop (Required)

```bash
pnpm lint --quiet
pnpm test -- --reporter=dot
pnpm build
pnpm verify:admin-api
pnpm verify:i18n
pnpm verify:release-tags
pnpm verify:package-scripts
git diff --check
test ! -d .github
```

Pass criteria:

- `lint` has 0 errors and 0 warnings
- `test` exits 0 (no unit / integration failures)
- `build` succeeds (main chunk < 500 kB)
- `verify:admin-api` shows no missing/extra endpoint coverage
- `verify:i18n` shows no missing keys in `ko.json`

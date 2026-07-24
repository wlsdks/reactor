# AGENTS.md

> Conventions for agents operating on the Reactor admin web application.
>
> - For human developer guidelines, architecture, and routing rules → see `CLAUDE.md`
> - For visual design tokens, components, and patterns → see `DESIGN.md`
> - For high-level project intro and quick start → see `README.md`

---

## Workflow

The repository-level workflow in `../../AGENTS.md` is authoritative. Admin work
ships on the same Reactor feature branch and PR as any backend contract changes.

Before any worktree, `gh`, push, tag, or release operation, run
`../../scripts/dev/verify-repository-identity.sh` from this directory. Admin
worktrees and branches must originate from the verified `wlsdks/reactor`
checkout and may be pushed only to its verified `origin`. A directory named
`reactor` is not proof of repository identity.

1. **Worktree per task** — create the worktree from the Reactor repository root. Never edit `main` in place.
2. **Cohesive branch** — one operator workflow boundary / fix / refactor per branch. Do not open or merge a PR for a single backlink, copy tweak, or package-version bump unless it is part of a larger verified workflow batch. Conventional Commits-style prefixes (`feat`, `fix`, `refactor`, `docs`, `style`, `test`, `chore`).
3. **Open a PR** — `gh pr create` with an English title and body. Title ≤ 70 chars; details belong in the body. Use `--squash` merge.
4. **Cleanup discipline** — after merge: remove the worktree, delete the local branch, delete the remote branch.
5. **Never push to `main`.** Direct `git push origin main` is strictly forbidden — even for "small fixes" or "hotfixes". Every change goes through PR review.

### Branch / release cadence

- Batch adjacent navigation, i18n, test, and evidence-surface edits into one PR
  when they support the same admin workflow boundary.
- Do not create bump-only branches or commits. `package.json` version changes are
  release-candidate work only, never a progress marker.
- Do not create tags for normal admin PRs. Run `pnpm verify:release-tags` before
  release-adjacent PRs to prove the admin release baseline has not drifted.
- Prefer a single PR for a complete RAG / feedback / eval / smoke operator flow
  improvement over a series of one-link PRs.

### Quality gates per PR

All must pass locally before opening the PR. This repository intentionally has
no GitHub Actions workflow; PR readiness is based on local verification evidence
recorded in the PR body.

```bash
pnpm lint              # 0 errors, 0 warnings
pnpm build             # main chunk < 500 kB
pnpm test              # 0 failures
pnpm verify:admin-api  # OpenAPI ↔ requirements.ts coverage
pnpm verify:i18n       # ko.json contains every t('...') referenced in src/
pnpm verify:package-scripts # package scripts stay on pnpm, not npm/yarn
pnpm verify:release-tags # admin release baseline has no progress tags/version drift
```

E2E (`pnpm test:e2e`) runs after broader development cycles complete, not on every PR.

---

## Boundaries

### Allowed

- `src/**` — production source
- `e2e/**` — Playwright specs
- `docs/**` — human-facing project docs (when relevant)
- Root markdown files (`CLAUDE.md`, `AGENTS.md`, `README.md`, `DESIGN.md`, `CHANGELOG.md`) when factually updating them

### Off-limits

- `node_modules/` — managed by pnpm
- `dist/`, `coverage/`, `playwright-report/`, `test-results/` — generated artifacts
- `.claude/`, `.github/workflows/` — agent configuration / intentionally absent CI configuration (touch only with explicit user direction)
- `pnpm-lock.yaml` — only changes via `pnpm add` / `pnpm install`, never hand-edit

### i18n

- `src/shared/i18n/ko.json` is the **only** locale file. Korean is the sole supported UI language.
- **Never recreate `en.json`.** The `react-i18next` infrastructure is preserved so additional locales can be added later, but the EN/KO toggle UI was removed and must not be reintroduced as part of an unrelated PR.
- All new keys go into `ko.json`. Missing keys render as the key string (no throw, no console error).
- Korean placeholders / examples must be in Korean — see `CLAUDE.md` "i18n" section for examples.

### Package manager

- **`pnpm` only.** Never run `npm install`, `yarn add`, etc. The lockfile and `pnpm.overrides` block in `package.json` assume pnpm.

---

## Reuse-First Policy

Before writing a new component or hook, check what already exists. The Stage A–G refactor cycles consolidated dozens of one-off implementations into shared primitives.

- **Shared UI** lives in `src/shared/ui/` — exported from `src/shared/ui/index.ts`
- **Shared hooks / utilities** live in `src/shared/lib/` — exported from `src/shared/lib/index.ts`
- The current shared catalogue is documented in `CLAUDE.md` → "Shared Components & Hooks"

### When creating a new shared primitive

1. Confirm no existing component / hook covers the use case (search `shared/ui` and `shared/lib`)
2. Place the file under `shared/ui/` (visual) or `shared/lib/` (logic) — not in `features/<name>/ui/`
3. Export from the matching `index.ts`
4. Add a Vitest test alongside (under `__tests__/`)
5. If it introduces a new visual pattern (color, border, shadow, spacing rhythm), update `DESIGN.md`
6. If it changes user-visible copy, update `ko.json`

### When extending `DataTable`

`DataTable` accepts six opt-in enhancement props (`truncate`, `resizable`, `responsivePriority`, `urlStateKey`, `exportable`, `rowActions`). Prefer adding to existing call sites over forking. See `CLAUDE.md` → "DataTable opt-in props".

---

## Communication & Honesty

- Code, comments, commit messages, PR titles / bodies, and reviews must be in **English** (see `CLAUDE.md` "Language Policy"). User-facing UI copy follows i18n policy (Korean).
- No marketing language ("blazingly fast", "production-ready") in commit messages or PR bodies. Cite measurable evidence (test counts, bundle size deltas, lint output).
- When uncertain about scope or design intent, ask before implementing — never assume.
- If the user's reasoning seems flawed, push back with explanation rather than silently complying.

# Reactor Admin Release Tagging Policy

## Current Decision

`reactor-admin` uses frequent PRs and small branches for implementation progress.
Git tags are not progress markers. Tags are reserved for release-worthy admin
states that operators can use as stable coordination points with the Reactor
backend.

## Tag Eligibility

Create an admin release tag only when all of these are true:

- The change batch is merged to `main`.
- The admin app is aligned with a known Reactor backend release or release
  readiness boundary.
- The batch changes an operator-visible capability, workflow boundary, or
  deployable admin state.
- Affected tests and admin release checks pass locally.
- The tag points at a clean `main` commit, not a feature branch commit.

Do not tag:

- Single-page backlink or navigation-only slices.
- Mechanical i18n, copy, CSS, or small test-only changes.
- Intermediate PRs inside a longer admin reconstruction loop.
- Commits that only update local evidence, docs, or handoff notes.
- Package-version-only commits or branches.

## Version Bump Rules

- Patch: deployable admin fixes or workflow polish that operators can safely take
  without a backend product boundary change.
- Minor: a complete admin workflow boundary, such as release cockpit plus RAG
  ingest/ask/citation plus feedback/eval/LangSmith review surfaces aligned with a
  Reactor minor release.
- Major: incompatible admin route, API, deployment, or operator workflow change.

## Naming

Use SemVer tags in the existing form, for example `v1.1.0` or `v1.1.1`. The
admin tag does not need to increment for every PR. When the admin release is
intended to match a backend release, document that backend version in the tag
message.

## Cleanup Status

The former `v1.1.1` through `v1.1.201` progress tags have been removed from local
and remote refs. Keep `v1.1.0` as the first Reactor 1.1 admin alignment tag
unless a later release candidate is explicitly selected as the new baseline.

`package.json` is prepared at the `1.2.0` release-candidate version while
`v1.1.0` remains the only allowed tag. Do not
bump the package version again until the next eligible release tag.

## Branch And Merge Cadence

Use frequent local commits if useful, but merge PRs at coherent operator
workflow boundaries. A good admin PR should make one release workflow state more
complete, such as document search handoff into cited-answer review, feedback
promotion into eval sync, or smoke evidence into release readiness. Avoid
standalone PRs whose only observable effect is a backlink, a package version
bump, or a small text change.

Before opening a PR, include `pnpm verify:release-tags` in the verification list
for any release-adjacent change. This checks both local and `origin` SemVer
release tags against the explicit allowlist so accidental progress tags or
package-version drift do not return.

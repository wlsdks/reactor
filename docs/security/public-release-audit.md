# Public Release Audit

Date: 2026-07-24

Status: **approved source boundary — recreate the GitHub repository before publication**

Target: `https://github.com/wlsdks/reactor.git`

Audited baseline: the publication commit containing this report

This report applies only to the standalone personal repository above. Historical
source-archive evidence is not evidence for this repository's current reachable
history.

## Repository boundary

- The publication history contains one reviewed root commit and shares zero
  commit objects with the former restricted source repository.
- `main` is the only branch, and no tags or releases are attached.
- Wiki and Pages are disabled, and Actions has no retained artifacts.
- Two old pull requests remain GitHub-hosted references. One retains the
  superseded merge commit whose author metadata used a personal email address.
  A force push cannot remove that pull-request ref, so the remote must be
  recreated from the approved local history before visibility changes.

## Current verification

- Checksum-verified Gitleaks 8.30.1 scanned the complete candidate history and
  current source tree with zero findings.
- Every reachable commit uses the same GitHub noreply author identity.
- Exact tracked-tree and reachable-history scans found no legacy project or
  company branding, personal-domain email address, personal username,
  repository-local machine name, or absolute home path.
- Slack token-shaped strings occur only in six test files and use explicit
  `test` or `secret-must-not-pass-through` canaries. No live Slack credential was
  detected.
- Only GitHub noreply commit identities are accepted in the publication history.
- Local authentication is development-only, process-local, and disabled outside
  the `local` environment. No generated signing secret is persisted.

## Historical source archives

Former private repositories remain separate restricted archives. Their branches,
tags, author metadata, deleted files, prompts, and Git objects were not imported.
They must not be used as development remotes for this project.

## Public release decision

The source boundary is approved for publication. Complete these remote steps as
one operation:

1. Run backend lint/type/tests, frontend lint/type/tests/build, strict API
   method/path coverage, i18n verification, and the repository identity gate.
2. Run Gitleaks against both the current tree and every reachable commit.
3. Rename the existing private GitHub repository to a restricted archive so its
   pull requests and existing star are preserved without becoming public.
4. Recreate `wlsdks/reactor` from the approved local `main` so old pull-request
   refs and superseded commit metadata are absent from the public repository.
5. Enable secret scanning and push protection when GitHub exposes those controls.
6. Make the recreated repository public and verify its default branch, visibility,
   commit identities, branches, tags, releases, Pages, wiki, and Actions surfaces
   from GitHub.

Rewriting history never invalidates a real credential. Any later confirmed secret
must be revoked before publication.

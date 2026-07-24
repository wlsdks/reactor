# Admin Operator Roadmap

> **Last verified: 2026-03-12** — strategic roadmap, mostly evergreen. Several P0
> "Operator Clarity" items have shipped through later stage cycles, including
> Stage P's Reactor 1.1 release-ops alignment. P1 / P2 items remain valid
> forward-looking targets. Use this as a directional reference, not a status
> tracker — for the latest delivered work see
> Historical stage reports remain in the archived standalone admin repository.

## Audience

This admin is for internal system administrators and developers operating Reactor in production or pre-production environments. It is **not** an end-user product surface.

UI polish matters, but only after operational clarity, safety, and diagnosability are covered.

## Current Assessment

The current admin is strong as a **feature console** and only partial as an **operator control plane**.

What already exists:

- Central MCP registry and connection management
- MCP preflight and access-policy flows
- Swagger source, revision, diff, and publish operations
- Platform-level and tenant-level admin surfaces
- Audit log, scheduler, approvals, sessions, and diagnostics pages
- API coverage verification and automated UI tests

What is still missing for operators:

- A true top-level operational overview across Reactor + connected MCP systems
- Clear action loops: detect issue -> inspect cause -> run safe action -> confirm recovery
- More admin-facing language and information architecture
- Stronger config readiness visibility (missing token/HMAC/URL/timeout/allowlist signals)
- Better change history, rollback, and emergency controls

## Product Principle

For this admin, the goal is **not** “friendly SaaS UX.”

The goal is:

1. Show current state with minimal ambiguity
2. Explain failure reason with exact technical context
3. Make safe operator actions obvious and reversible
4. Preserve auditability for every sensitive change

Dense tables, badges, timestamps, raw JSON, and exact error messages are acceptable here. Ambiguous wording and hidden state are not.

## P0: Operator Clarity

Ship these first. They directly improve day-to-day use for system administrators.

- Rename navigation and page copy into operator language instead of internal feature jargon
- Increase overall UI scale and readability so the console does not feel cramped
- Add one-screen operational status for:
  - Reactor API
  - Atlassian MCP
  - Swagger MCP
  - core runtime health and readiness
- Surface config readiness signals:
  - admin URL present/missing
  - admin token present/missing
  - HMAC required/missing
  - preflight pass/warn/fail counts
- Keep advanced details expandable, but make summary state visible immediately
- Ensure every critical operator page answers:
  - what is broken
  - why
  - what can I do next

## P1: Safe Operations

These features move the admin from “viewer” toward “control plane.”

- Bulk operational actions for MCP servers:
  - rerun preflight
  - reconnect
  - disable/enable inventory entries
- Emergency controls where supported:
  - deny-all policy
  - read-only mode
  - scheduler pause/resume
- Richer runtime drilldown:
  - last success / last failure
  - reconnect attempts
  - upstream 401 / 403 / 429 trends
  - top failing tools by server
- Policy history with diff and rollback
- Better queue views for:
  - approvals backlog
  - stuck scheduler jobs
  - high-risk sessions or trust failures

## P2: Production Ops Depth

These complete the operator story for larger installations.

- Full service topology page with dependency graph and blast-radius hints
- Incident timeline combining:
  - MCP failures
  - policy changes
  - scheduler failures
  - trust / guard events
- Config drift detection across environments
- Maintenance windows and change freeze support
- Multi-tenant bulk administration and export workflows
- Saved operator views, filtering presets, and incident-mode layouts
- Deeper audit analytics for who changed what, how often, and with what effect

## Definition of “Good Enough” for Admin

This admin is “good enough” for operators when a developer on call can do the following without leaving the console:

1. Confirm whether the system is healthy
2. Identify which connected component is degraded
3. Read the exact reason for the degradation
4. Run the safe recovery action
5. Verify recovery
6. Review the audit trail afterwards

Until that loop is fast and reliable, additional visual polish should stay secondary.

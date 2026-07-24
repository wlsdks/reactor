# Reactor Quality Elevation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Reactor from Python/LangGraph parity-ready into a higher-confidence product runtime by closing every `ported` area with explicit verification, live evidence, and product-depth QA.

**Architecture:** Keep the existing parity ledger and release readiness tools as the source of truth. Add small, testable quality gates and evidence reports instead of broad rewrites, then promote ledger rows from `ported` to `verified` only when the matching tests, static gates, and smoke evidence are current.

**Tech Stack:** Python 3.13.14, uv, pytest, FastAPI, LangGraph, LangChain, PostgreSQL/pgvector, MCP SDK, A2A SDK, Slack SDK, release smoke CLIs.

---

## Execution Order

1. Surface every `ported` area as a first-class verification backlog in the release readiness JSON.
2. Add deeper LangGraph and LangChain runtime parity tests for approvals, tools, checkpoints, streaming, and usage accounting.
3. Refresh live smoke evidence for provider, Slack, A2A, scheduler/provider, and backend/provider observability gates.
4. Add Slack product-depth QA scenarios for mention gating, allowlists, thread follow-up, and approval button flows.
5. Add MCP live-profile coverage for stdio, streamable HTTP, tool-name normalization, access policy, and credential fail-close behavior.
6. Add durable job crash/reclaim and multi-replica operation tests for scheduler, outbox, and alert execution.
7. Add observability and cost/SLO integration checks that prove provider spans, usage ledger records, and SLO alert state agree.

## Task 1: Verification Backlog In Readiness Reports

**Files:**
- Modify: `src/reactor/release/readiness.py`
- Modify: `tests/unit/test_replatform_readiness.py`

- [ ] **Step 1: Write failing test**

Add a test proving `build_replatform_readiness_report()` returns `verification_backlog` for all `ported` rows, with the area, status, and completion gate.

- [ ] **Step 2: Run RED**

Run: `uv run pytest tests/unit/test_replatform_readiness.py::test_replatform_readiness_report_lists_ported_verification_backlog -q`

Expected: fail with missing `verification_backlog`.

- [ ] **Step 3: Implement backlog**

Add a small helper that maps rows with `status == "ported"` into JSON-safe backlog entries. Include the helper result in the report without changing `release_ready` semantics.

- [ ] **Step 4: Run GREEN**

Run: `uv run pytest tests/unit/test_replatform_readiness.py::test_replatform_readiness_report_lists_ported_verification_backlog -q`

Expected: pass.

- [ ] **Step 5: Run nearby tests**

Run: `uv run pytest tests/unit/test_replatform_readiness.py tests/unit/test_release_smoke_plan.py -q`

Expected: pass.

## Task 2: Agent Runtime Deep Verification

**Files:**
- Modify: `tests/unit/test_run_service.py`
- Modify: `tests/unit/test_langchain_agent.py`
- Modify only if the tests expose a real gap: `src/reactor/runs/service.py`, `src/reactor/agents/langchain_agent.py`, `src/reactor/agents/graph.py`

- [ ] **Step 1: Add focused tests**

Cover equivalent runtime behavior for `runtime=langgraph` and `runtime=langchain_agent`: response schema propagation, model-facing enabled tools only, shared checkpointer config, streaming event persistence, and sanitized error payloads.

- [ ] **Step 2: Run focused RED**

Run only the new or changed test names with `uv run pytest ... -q`.

- [ ] **Step 3: Patch the smallest runtime gap**

Change only the runtime boundary that failed. Do not refactor graph structure unless the failing test requires it.

- [ ] **Step 4: Verify agent lane**

Run: `uv run pytest tests/unit/test_run_service.py tests/unit/test_langchain_agent.py tests/unit/test_agent_graph_policy.py -q`

## Task 3: Live Evidence Refresh

**Files:**
- Existing reports under `reports/release/`
- No production code unless smoke tooling fails for a code reason.

- [ ] **Step 1: Preflight environment**

Run: `uv run reactor-release-smoke-run --plan reports/release/release-smoke-plan.local.json --report-file reports/release/local-contract-smoke-report.json --preflight-file reports/release/release-smoke-preflight.local.json --preflight-only`

- [ ] **Step 2: Run available automated smoke lanes**

Use local Ollama overrides when cloud provider credentials are unavailable:

```bash
REACTOR_RELEASE_SMOKE_PROVIDER=ollama \
REACTOR_RELEASE_SMOKE_MODEL=gemma4:12b \
REACTOR_RELEASE_SMOKE_TRACE_EXPORTER=console \
uv run reactor-release-smoke-run \
  --plan reports/release/release-smoke-plan.local.json \
  --report-file reports/release/local-ollama-release-smoke-run.json \
  --verified-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --evidence-output reports/release/local-ollama-release-evidence.json
```

- [ ] **Step 3: Recompute readiness**

Run: `uv run reactor-replatform-readiness --evidence reports/release/local-ollama-release-evidence.json --output reports/release/replatform-readiness.local.json`

## Task 4: Slack Product-Depth QA

**Files:**
- Modify: `tests/unit/test_slack_inbound.py`
- Modify: `tests/unit/test_slack_worker.py`
- Modify: `tests/unit/test_slack_feedback.py`
- Modify implementation only if tests reveal a gap under `src/reactor/slack/`

- [ ] **Step 1: Add mention and allowlist tests**

Prove unmentioned channel messages are dropped unless free-response is configured, DMs are accepted, and channel/user allowlists fail closed before rate limit, FAQ, or agent execution.

- [ ] **Step 2: Add thread follow-up tests**

Prove app participation is recovered from persisted tenant-scoped `agent_runs.thread_id`, not only in-process memory.

- [ ] **Step 3: Add approval button tests**

Prove malformed payloads fail closed and approved decisions resume the stored thread/checkpoint namespace.

- [ ] **Step 4: Verify Slack lane**

Run: `uv run pytest tests/unit/test_slack_inbound.py tests/unit/test_slack_worker.py tests/unit/test_slack_feedback.py tests/integration/test_slack_api.py -q`

## Task 5: MCP Live-Profile Coverage

**Files:**
- Modify: `tests/unit/test_mcp_preflight.py`
- Modify: `tests/unit/test_mcp_registry.py`
- Modify: `tests/unit/test_mcp_tool_sync.py`
- Modify implementation only if tests reveal a gap under `src/reactor/mcp/` or `src/reactor/tools/mcp/`

- [ ] **Step 1: Add profile matrix tests**

Cover stdio and streamable HTTP profile normalization, `ServerName:tool_name` public naming, credential binding, SSRF deny, and access-policy allowlist filtering.

- [ ] **Step 2: Verify MCP lane**

Run: `uv run pytest tests/unit/test_mcp_preflight.py tests/unit/test_mcp_registry.py tests/unit/test_mcp_security_policy.py tests/unit/test_mcp_tool_sync.py tests/integration/test_mcp_server_api.py -q`

## Task 6: Durable Jobs Operation

**Files:**
- Modify: `tests/unit/test_scheduler_worker.py`
- Modify: `tests/unit/test_outbox_dispatcher.py`
- Modify: `tests/integration/test_durable_outbox_postgres.py`
- Modify implementation only if tests reveal a gap under `src/reactor/jobs/`, `src/reactor/scheduler/`, or `src/reactor/workers/`

- [ ] **Step 1: Add crash/reclaim tests**

Prove expired dispatching leases are reclaimed, fencing tokens prevent stale completion, failed dispatches schedule retry, and dead-letter state is terminal.

- [ ] **Step 2: Add multi-replica readiness check**

Prove production multi-replica settings require Redis while local/single-node remains usable without Redis.

- [ ] **Step 3: Verify jobs lane**

Run: `uv run pytest tests/unit/test_scheduler_worker.py tests/unit/test_outbox_dispatcher.py tests/unit/test_redis_check.py tests/integration/test_durable_outbox_postgres.py -q`

## Task 7: Observability, Cost, And SLO Integration

**Files:**
- Modify: `tests/unit/test_tracing.py`
- Modify: `tests/unit/test_pricing_cost_ledger.py`
- Modify: `tests/unit/test_slo_alerts.py`
- Modify: `tests/unit/test_release_evidence.py`
- Modify implementation only if tests reveal a gap under `src/reactor/observability/` or `src/reactor/release/`

- [ ] **Step 1: Add agreement tests**

Prove provider usage metadata, usage ledger records, cost calculations, and emitted trace/span metadata agree on tenant, run, provider, model, and token counts.

- [ ] **Step 2: Add SLO state tests**

Prove burn-rate evaluators create alert instances with tenant-scoped rule metadata and dispatch failure tracking.

- [ ] **Step 3: Verify observability lane**

Run: `uv run pytest tests/unit/test_tracing.py tests/unit/test_pricing_cost_ledger.py tests/unit/test_slo_alerts.py tests/unit/test_release_evidence.py -q`

## Completion Gate

After tasks 1-7 have passed their focused lanes, run:

```bash
uv lock --check
uv run ruff check
uv run ruff format --check
uv run pyright
uv run pytest
```

For any Docker/Postgres-dependent changes, also run the relevant `REACTOR_TEST_POSTGRES=1` integration lane before promoting a ledger row to `verified`.

## 2026-06-29 Progress Log

- Task 1: Added readiness `verification_backlog` output for all `ported` rows and refreshed local readiness evidence.
- Task 2: Added LangChain-agent runtime tool-context filtering coverage in run streaming and patched `RunService` to keep runtime tool metadata through response filtering.
- Task 3: Refreshed local provider/backend provider smoke evidence and recomputed `reports/release/replatform-readiness.local.json`.
- Task 4: Added Slack approval button channel-mismatch fail-close coverage and patched approval handling so tampered action channel IDs cannot receive ACKs or resume runs.
- Task 5: Added MCP tool sync coverage proving disabled snapshots are excluded from model-facing tool specs.
- Task 6: Added outbox dispatcher lease-owner fencing coverage and patched dispatcher/store completion paths so stale workers cannot mark a reclaimed outbox event dispatched or failed.
- Task 7: Added SLO alert notification fail-open coverage and patched async alert dispatch so notification failures do not lose saved active alerts.
- Task 7 follow-up: Added RunService trace/usage-ledger agreement coverage for cached and reasoning token details, and added legacy-compatible usage ledger total-token validation.
- Full gate: `uv lock --check`, `ruff check`, `ruff format --check`, `pyright`, and full `pytest` passed with `1286 passed, 22 skipped`.
- Docker/Postgres gate: `REACTOR_TEST_POSTGRES=1` integration lane passed with `22 passed`.
- Ledger promotion: `docs/migration/full-replatform-parity-ledger.md` now reports all 22 retained feature rows as `verified`; regenerated readiness reports `verification_backlog=0`, `blocking_areas=0`, and `deferred_gates=0`.

## Self-Review

- No broad architecture rewrite is included.
- Every task has a focused test lane.
- The first task is immediately executable without live credentials.
- Live smoke work is separated from local deterministic test work.

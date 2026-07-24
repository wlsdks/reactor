# Reactor

Reactor is a Python-first AI agent system built around FastAPI, LangGraph,
LangChain, PostgreSQL/pgvector, and Redis only for ephemeral coordination.

This file is loaded every session. Keep it short. The canonical architecture is
`docs/architecture/python-langgraph-replatform-spec.md`; update that spec first when
changing stack, module boundaries, storage, security, or verification policy.
Prior implementation is inventory only, not a structure, package layout, endpoint
set, or data shape to preserve.

Long-form harness rules live in `docs/architecture/agent-harness-operating-model.md`.
If `CLAUDE.md`, `AGENTS.md`, and the canonical spec disagree, fix the stale document
in the same change.

## Repository Identity

The only allowed repository target for this project is
`https://github.com/wlsdks/reactor.git`. Run
`scripts/dev/verify-repository-identity.sh` before any worktree, GitHub, push,
visibility, tag, or release action. Stop if the check fails. Historical Reactor
repositories are out of scope unless the user explicitly names one in the current
request.

## Session Workflow

1. Inspect the relevant spec section and changed files before editing.
2. For structural questions, use CodeGraph if available: start with
   `codegraph_context`, use `codegraph_trace` for flow, `codegraph_impact` for
   blast radius, and `codegraph_status` for index health. Use `rg for literal`
   string checks.
3. Keep the change inside the smallest package boundary that can own it.
4. Before edits, identify which tests prove the change.
5. Implement with explicit types, async boundaries, and deterministic policy.
6. Verify narrow tests first, then widen only when the change crosses boundaries.
7. Summarize changed files, verification, and residual risk.

## Stack Baseline

| Area | Decision |
| --- | --- |
| Runtime | Python 3.13.14 through `uv` |
| API | FastAPI |
| Agent runtime | LangGraph |
| Model/tool/protocol integration | LangChain packages, MCP SDK/adapters, A2A SDK |
| RAG | `langchain-postgres` with PostgreSQL/pgvector |
| Memory | application-owned store plus LangMem extraction/consolidation |
| Durable state | PostgreSQL |
| Ephemeral coordination | Redis for multi-replica locks, counters, cache, pub/sub wakeups |
| Package layout | `src/reactor` |

Library-first rule:

- Prefer official LangGraph/LangChain primitives for generic agent behavior.
- Use LangChain `create_agent` or LangGraph prebuilt/tool-calling helpers for
  simple model-tool loops when they do not weaken Reactor policy contracts.
- Use explicit LangGraph nodes when Reactor must enforce guards, approvals, audit,
  tenancy, cost accounting, or retained product contracts between steps.
- Use LangGraph checkpointing, interrupts, streaming, stores, and subgraphs instead
  of hand-rolling those generic runtime semantics.
- Use `langchain-postgres`, LangChain retriever/tool/provider integrations, MCP/A2A
  SDKs, and LangMem before custom adapters. Custom code belongs at Reactor's product
  boundary: policy, RBAC, audit, schema normalization, migration compatibility, and
  retained product behavior.
- Use LangChain agent middleware before custom generic agent controls: model/tool
  call limits, PII guardrails, model/tool retry, fallback, summarization/context
  editing, tool selection, and HITL. Reactor code remains responsible for tenant
  policy, approval rows, audit, idempotency, ACL, cost ledger, and retained product
  contracts.
- Compose model fallback outside model retry so each model exhausts its retry budget
  before the next configured fallback is attempted. The primary model belongs only
  to `create_agent(model=...)`, never in `ModelFallbackMiddleware`'s fallback list.
- Configure LangChain model/tool retry with Reactor's transient-only predicate:
  timeouts, connection failures, rate limits, HTTP 408/409/425/429, and server
  errors. Validation, authentication, permission, and other permanent failures
  must not consume retry budget. Explicit LangGraph model invocation uses the same
  provider-level predicate.
- Reactor policy owns the retry budget. Initialize primary, fallback, and explicit
  LangGraph provider models with SDK-internal retry disabled (`max_retries=0`) so
  provider defaults cannot multiply `ModelRetryMiddleware` or graph retry attempts.
- Middleware evidence planning is side-effect free. Only the agent runtime may
  initialize primary or fallback providers; metadata/reporting paths use the
  deterministic middleware plan and must not construct provider clients.
- Prefer concrete structured output schemas for model-visible answer contracts.
  Schema-less JSON structured output must still be object-shaped; arrays and
  scalars are invalid unless an explicit schema permits them.
  RAG-backed structured JSON answers must cite manifest evidence when citations are
  available; unknown or missing citation IDs are policy failures.
  If RAG chunks are present but citation IDs are absent, structured JSON responses
  fail closed instead of accepting model-invented citations.
- Structured-output citation metadata includes the allowed manifest citation IDs so
  release review can audit unknown-source rejection without raw context payloads.
- Invalid explicit `metadata.responseSchema` records
  `structuredOutput.ignoredSchema.reason=invalid_response_schema` instead of
  silently disappearing into JSON fallback.

Retention rule:

- Treat Spring/Kotlin behavior as a source inventory, not a target architecture.
- Classify old features, routes, tables, settings, and packages as `keep`, `remap`,
  `drop`, or `defer` before porting them.
- Keep or remap only capabilities needed for active users, security, audit/legal
  retention, billing, approved memories, prompts/evals, tool policy, RAG, or
  production operations.
- Drop implementation artifacts, stale compatibility paths, transient caches,
  framework-era wrappers, and empty packages once LangChain/LangGraph/LangSmith or
  the new product model makes them unnecessary.
- Prefer LangSmith for agent tracing/evaluation workflows where it replaces custom
  trace viewers or ad-hoc eval plumbing without weakening product retention,
  redaction, or compliance rules.

Harness rule:

- Treat the model as one replaceable component inside the Reactor harness. The
  durable quality surface is specs, typed boundaries, deterministic graph policy,
  tests, smoke gates, observability, and eval feedback.
- As of 2026-06-29, harness source basis is recorded in
  `docs/architecture/agent-harness-operating-model.md`: OpenAI harness/Codex/App
  Server/Symphony guidance, Anthropic effective-agent patterns, Agentic Harness
  Engineering, evidence-provenance research, LangChain/LangGraph/LangSmith docs,
  and HumanLayer 12-factor agents. These references inform Reactor but never
  override Reactor invariants.
- Keep this file short. Use it as a navigation and invariant map; put long-form
  operating detail in `docs/architecture/agent-harness-operating-model.md` and the
  canonical spec.
- Maintain reference freshness for the harness source basis when framework major
  APIs change, when always-loaded instruction files gain a new rule class, or before
  runtime-changing releases.
- When a repeated agent mistake appears, prefer executable constraints over more
  prose: focused regression tests, architecture tests, smoke/eval gates, static
  checks, typed policy surfaces, and clearer error contracts.
- Classify harness changes through Component layer, Experience layer, and Decision
  layer: what editable component owns the fix, what evidence captured the failure,
  and what verification proves the decision worked.
- Keep a Rules-to-sensors matrix for durable instructions: every feedforward rule
  needs a feedback sensor such as a focused test, static gate, eval, smoke report,
  trace contract, or release artifact.
- Make work legible to the next agent: explicit names, narrow package ownership,
  current source-of-truth docs, local verification commands, and reports with
  remediation details.
- Do not rely on CI as the confidence mechanism. Local focused tests, affected lane
  tests, static gates, and release smoke/eval artifacts are the required evidence.
- Release/eval gate reports expose `ok`, `status`, `scope`, and `evidence` metadata
  so humans and agents can distinguish a passing gate, skipped dry run, and failure
  without reverse-engineering logs.
- Named release gates preserve their canonical `scope`, `owner`, and `mode`;
  readiness aggregation fails closed when a passed gate reports the wrong identity.
- Hardening suite evidence includes LangGraph stage order, node order,
  `composition=stage_subgraphs`, `subgraphOrder`, parent-level `subgraphEdges`,
  and subgraph entry/exit plus per-subgraph `nodes`/`nodeCount`/`checkpointMode`
  topology so release review can detect runtime-structure drift without manually
  inspecting traces.
- Hardening suite evidence includes the tool profile budget contract so release
  review can see active-tool range and resolved budget metadata fields.
- Hardening suite evidence includes the context management lifecycle contract so
  release review can see LangChain-native summarization, context editing, tool
  selection, provider tool search, context checksums, tool-pair preservation, and
  mutation audit safeguards without raw context payloads.
- Hardening suite evidence includes the usage/cost lifecycle contract so release
  review can see LangChain usage metadata, LangSmith token/cost tracking,
  Reactor usage ledger persistence, Prometheus cost metrics, tenant/run/session
  scoping, admin review surfaces, and cost/token validation together.
- Hardening suite evidence includes the outbox/inbox lifecycle contract so release
  review can see replayable external side effects, webhook/event de-duplication,
  Postgres `SKIP LOCKED` claims, lease ownership, retry/dead-letter behavior, and
  stale-owner dispatch protection together.
- Hardening suite evidence includes LangGraph cache serialization policy so
  release review can see that `CachePolicy` pickle-key fallback is disabled for
  Reactor cache paths and side-effect nodes remain uncached.
- Hardening suite evidence includes `langchainSerializationBoundary` so release
  review can see that LangChain object/prompt load/loads APIs, env-secret
  revival, and user-config deserialization are forbidden outside trusted JSON-only
  paths.
- Graph runtime tool profile budget metadata must include `dropped_tools` with
  deterministic reasons such as `denied_tool`, `tool_not_allowed`,
  `risk_level_not_allowed`, or `max_tools_exceeded` whenever configured tools are
  removed from the active model-facing tool set.
- `reactor-langsmith-eval-sync` reports include `datasetName`, source suite,
  enabled-case count, deterministic `exampleIds`, `metadataCaseIds`,
  `splitCounts`, a metadata-only `exampleContract` with `secretScan`, and
  `sdkContract` naming the LangSmith `Client` dataset/example APIs so dataset sync
  remains tied to source-controlled eval gates, framework-native SDK usage, and
  the regression split.
- `reactor-release-readiness-evidence` aggregates observability, hardening, eval,
  and other gate reports into one `release_readiness` artifact; skipped gates block
  release readiness, skipped report reasons stay visible for remediation, and
  malformed reports fail closed.
- Release readiness preserves live A2A peer-network smoke evidence as
  `a2aProtocol` so release review can see SDK, protocol endpoint, agent card,
  task API, diagnostics, audit, idempotency, telemetry, and push-outbox coverage.
- Release readiness derives `toolOutputGuard` from context manifest tool-output
  metadata so release review can see sanitizer counts and findings without
  inspecting the full manifest.
- Release readiness preserves and validates `guardBlock` so fail-close
  input/output guard decisions remain visible in release review without raw user
  or model content.
- Public run API responses expose only projected, allowlisted run metadata.
  Approval metadata must omit raw tool input payloads while preserving the IDs,
  risk, timeout, and idempotency fields needed for recovery or HITL UX.
- Release readiness preserves structured privacy evidence from gate reports; the
  LangSmith observability item must expose the trace privacy contract without
  leaking raw inputs, outputs, metadata, secrets, or PII, including
  `redactionCoverage` for the fields exercised by local smoke.
- Release readiness preserves and validates observability SDK evidence as
  `observabilitySdk`: LangSmith tracing/privacy environment keys plus
  OpenTelemetry `TracerProvider`, `BatchSpanProcessor`, console and OTLP/HTTP
  exporters, resource attributes, sampler, and provider force-flush/shutdown on
  FastAPI lifespan exit.
- PII middleware policy evidence records `applyToInput`, `applyToOutput`,
  `applyToToolResults`, and `applyToStreamOutput`; on the current LangChain
  middleware surface, stream output follows `applyToOutput` and cannot diverge.
- Release readiness validates LangSmith `feedbackLoop.promotedCaseIds` against
  `langsmith_eval_sync.caseIds` so online trace/feedback findings cannot claim
  offline coverage without synced source-controlled eval cases.
- Release readiness preserves the LangSmith smoke target as `observabilityTarget`:
  trace provider, project, endpoint, span name, and `secretFree=true`; never include
  API keys or raw trace payloads in this facet. Secret-bearing target fields are
  dropped from the aggregate and fail readiness.
- Live backend provider smoke evidence must include LangChain
  `AIMessage.usage_metadata` token counts in `backendProviderIntegration` so live
  provider, tracing, and cost-accounting readiness are reviewed together.
- `checkpointProvenance.storageSemantics` must prove tenant/thread/product-namespace
  hashing, LangGraph root `checkpoint_ns=""`, official saver source-read and
  target-write APIs, empty-target and pending-write guards, materialization modes,
  typed fork capability authority, runtime/profile compatibility, and the complete
  fail-close reason set.
- Release readiness also preserves review-critical evidence facets from gate
  reports: LangGraph topology, tool profile budget, context manifest
  `contextManifest`, LangChain middleware policy `langchainMiddlewarePolicy`,
  checkpoint fork/replay provenance `checkpointProvenance`, LangSmith
  `datasetName`, observability SDK `observabilitySdk`, structured output strategy and repair boundary
  `structuredOutput`, research answer contract `researchAnswerContract`, tool
  invocation lifecycle `toolInvocationLifecycle`, A2A protocol `a2aProtocol`, MCP preflight
  `mcpPreflight`, Slack/MCP surface policy `slackMcpSurfacePolicy`,
  memory maintenance lifecycle `memoryMaintenanceLifecycle`,
  RAG ingestion lifecycle `ragIngestionLifecycle`, artifact lifecycle
  `artifactLifecycle`, prompt release lifecycle `promptReleaseLifecycle`,
  approval lifecycle `approvalLifecycle`, provider fallback policy
  `providerFallbackPolicy`, LangGraph fault tolerance `langgraphFaultTolerance`,
  checkpoint retention policy `checkpointRetentionPolicy`, streaming event contract
  `streamingEventContract`, context management lifecycle
  `contextManagementLifecycle`, usage/cost lifecycle `usageCostLifecycle`,
  outbox/inbox lifecycle `outboxInboxLifecycle`, Redis coordination
  `redisCoordination`, source suite, enabled eval case
  count, and deterministic
  `exampleIds`, `metadataCaseIds`, `splitCounts`, `exampleContract`, and
  `sdkContract`.
- `checkpointRetentionPolicy` includes `graphStoreRuntime` evidence naming
  `AsyncPostgresStore` for durable graph stores, `InMemoryStore` as local-only,
  and the same-store handoff to LangChain `create_agent`.
- `redisCoordination` proves Redis remains ephemeral-only: multi-replica production
  requires Redis readiness, Pub/Sub is treated as at-most-once wakeup traffic, rate
  limit failures fail closed by default, `runLifecyclePublisherClosedOnContainerClose`
  proves cached Redis publisher clients close during `AppContainer.close()`,
  `slackUserRateLimiterClosedOnContainerClose` proves Redis-backed Slack rate
  limiter clients close during shutdown, and durable state/checkpoints stay out of
  Redis.
- MCP preflight readiness must include authorization-security evidence for OAuth
  2.1, PKCE, protected-resource metadata discovery, server-side token storage,
  scope validation, and rejection of authenticated registrations without scoped
  credential binding.
- MCP preflight readiness also includes `adapterToolLoading` evidence for
  `MultiServerMCPClient.get_tools`, `load_mcp_tools`, stdio/streamable HTTP
  connection dictionaries, structured-content artifacts, and tool-error handling.
- A2A readiness includes `protocolNegotiation` evidence for `A2A-Version: 1.0`,
  Major.Minor-only versions, SDK FastAPI serving, and telemetry instrumentation.
- API smoke readiness includes `apiBoundary` evidence for FastAPI, OpenAPI,
  Pydantic validation, required public paths, and secret-free schema metadata.
- Migration dress readiness includes `migrationPersistence` evidence for
  SQLAlchemy, Alembic, psycopg, retained-table manifests, parity, rollback, and
  idempotent import ledger guarantees.
- Context manifests must expose memory/RAG policy evidence: `memoryAdmissionPolicy`
  documents active-only memory admission and exclusion of tombstoned or missing
  status memories, while `ragGroundingPolicy` documents required citation tracking,
  uncited chunk accounting, and ACL-hash-only evidence. Memory status counts must
  reconcile rendered active memory plus skipped memory so tombstones or missing
  statuses cannot disappear from review evidence.
- Memory maintenance readiness must expose LangMem manager contract plus
  consolidation policy: `create_memory_manager`, `create_memory_store_manager`,
  `ainvoke`, disabled LangMem deletes, reviewed promotion can supersede prior
  active memories, and superseded items stay out of active model-visible context.
- Memory approval review surfaces expose safe `maintenance` summaries for API/CLI
  operators and must not expose raw proposal `source_payload`.
- Memory maintenance readiness also preserves dependency warning scan evidence as
  `dependencyWarnings` so LangMem/trustcall/LangGraph deprecations stay visible
  during release review. The evidence must include `directPins` and `pinSource`
  when `pyproject.toml` exact pins block a dependency fix; remediation updates the
  pins and then runs `uv lock --upgrade-package langmem --upgrade-package trustcall
  --upgrade-package langgraph`.
- `reactor-release-smoke-run --readiness-output` writes that aggregate directly
  from the smoke run and release evidence outputs so release review uses one
  machine-readable handoff artifact.
- `reactor-release-smoke-run --readiness-output` requires `smoke_run` and
  `release_evidence` by default. The aggregate records `requiredReports` and
  `missingReports`; missing required gates block readiness.
- Release readiness records `tagRecommendation` so version-tag decisions are tied
  to passed/blocked/skipped gate evidence instead of commit count or session time.
  It records `recommendedVersionBump`, `recommendedTagPattern`, and
  warning-review fields; `eligible_with_warnings` remains tag-eligible only after
  operators review `warningReports`. Minor recommendations require passed
  `productCapabilityBoundary.minorEligible` evidence.
- Do not tag every validated commit. Keep commits small and pushed, but create
  version tags for release-worthy batches, deployment candidates, or explicit
  user requests. Verified hardening batches should receive v1.0.x patch tags
  instead of being collapsed into one later tag; internal evidence, docs, and
  focused test slices usually do not bump `pyproject.toml` or create tags.
- Version bump boundary: patch tags are for verified hardening batches; minor tags
  require a user-visible product/runtime capability boundary, not just additive
  evidence fields, diagnostics, docs, or focused tests; major tags require an
  incompatible product, API, data, or deployment contract.
- Commit granularity checklist: commit at reviewable product or safety
  boundaries, not every RED/GREEN micro-step. A commit should normally contain
  one coherent behavior, policy, workflow, or evidence-sensor change with its
  tests. Batch adjacent fixture, CLI wording, report-shape, and readiness-surface
  edits when they only support the same behavior. Split commits when rollback,
  review ownership, migration risk, or verification scope would otherwise become
  unclear.
- Long-running hardening goal stop condition: do not mark a goal complete merely
  because one coherent slice landed or a commit was pushed. After each stable
  slice, continue with the next highest-risk gap; stop only when the requested
  release, parity, or hardening boundary is met; memory or context pressure is a
  handoff condition, not a completion condition.

Do not add a second serving-path agent framework. Other SDKs and workflow engines are
references or graduation candidates; use framework-native behavior before custom code.

## Product Shape

Reactor is a centrally managed agent product, not only a backend API. The backend
package is the source of truth for policy and agent execution, while users should
get personal workspaces under tenant policy: runs, threads, checkpoints, memories,
artifacts, preferences, tool permissions, and integration identities.

Client apps, gateways, CLI commands, plugins, MCP servers, and A2A peers live at
the edges. They must call the same FastAPI/LangGraph policy layer instead of
duplicating or bypassing the core agent runtime.

The operator web client lives in `apps/admin`. It is a separately built React
application inside this monorepo; `src/reactor` remains the only backend policy
and execution authority. Full-stack Docker orchestration belongs at the repository
root, while app-local build configuration stays inside `apps/admin`.

## Module Boundaries

Use product-capability packages under `src/reactor`, not framework-layer dumping.
Create, remove, or defer packages according to selected workflows and framework coverage.

| Package | Owns |
| --- | --- |
| `core` | settings, container, lifespan, feature flags, top-level error mapping |
| `kernel` | ids, clocks, tenancy values, pagination, tiny shared primitives |
| `api` | FastAPI routers, dependencies, DTOs, auth extraction, SSE adapters |
| `agents` | LangGraph state, graph factories, nodes, graph profiles, graph policies |
| `context` | context manifests, token budgets, trimming, context assembly |
| `prompts` | prompt registry, prompt releases, prompt eval gates |
| `prompt_lab` | prompt experiments, trials, recommendations, and report contracts |
| `providers` | chat, embedding, reranker, provider routing, fallback policy |
| `tools` | built-in tools, MCP adapters, schemas, risk policy, audit |
| `a2a` | agent card, peer registry, protocol endpoint, task mapping |
| `rag` | ingestion, chunking, retrieval, reranking, citations |
| `memory` | `ReactorMemoryStore`, LangMem jobs, proposals, consolidation |
| `guards` | input, output, and tool-output guards |
| `response` | response filters, structured output repair, and output boundary enforcement |
| `hooks` | lifecycle hooks and non-blocking side effects |
| `jobs` | queue, leases, retries, outbox, inbox, dead letters |
| `cache` | ephemeral cache contracts backed by Redis or in-process local adapters |
| `persistence` | SQLAlchemy models, Alembic migrations, DB session helpers |
| `artifacts` | blob references, local dev storage, retention |
| `sandbox` | code/tool execution isolation policy |
| `observability` | logs, metrics, traces, LangSmith/OpenTelemetry, redaction |
| `workers` | process entrypoints only |
| `evals` | datasets, judges, rubrics, release gates |

Dependency direction:

```text
api -> application services -> feature packages -> persistence/providers
workers -> jobs/agents/rag/memory/tools/a2a
agents -> context/prompts/providers/tools/rag/memory/guards/hooks
feature packages -> kernel/observability
persistence -> kernel
```

Do not break these boundaries:

- Routers do not open DB sessions, assemble prompts, retrieve chunks, or execute tools.
- Graph nodes do not open DB sessions directly.
- Repositories do not import FastAPI, LangGraph, chat models, or provider SDKs.
- Feature packages do not import API routers or request objects.
- `kernel` does not import feature packages.
- No dynamic imports from user-controlled strings.

## LangGraph Contract

- Production graph execution is async: `ainvoke`, `astream`, or `astream_events`.
- Checkpoint with `AsyncPostgresSaver`.
- Compile production graphs with a LangGraph store: `AsyncPostgresStore` for
  database deployments and `InMemoryStore` only for local/non-durable execution.
- Production or `database_required` startup must fail closed when `database_url` is
  missing; do not silently fall back to an in-memory graph/checkpointer.
- Pass the same graph store to LangChain `create_agent(store=...)` runtime paths.
- Resolve LangChain agent middleware policy in this order: internal
  `metadata.middlewarePolicy`, tenant runtime setting
  `langchain.middleware_policy`, global runtime setting
  `langchain.middleware_policy`, then the default code policy.
- Completed run metadata records `langchainMiddlewarePolicy.status` as `applied`
  or `ignored`; invalid runtime settings must leave source/key/tenant/reason
  evidence instead of disappearing into default policy behavior.
- PII middleware policy records input, output, tool-result, and stream-output
  scope for every rule so release review can see where redaction/blocking applies.
- Invalid explicit `metadata.middlewarePolicy` records
  `reason=invalid_metadata_policy` and does not silently fall through to tenant or
  global runtime settings.
- Resolve LangChain active tool profile budgets in this order: internal
  `metadata.toolProfileBudget`, tenant runtime setting `tools.profile_budget`,
  global runtime setting `tools.profile_budget`, then no additional profile
  budget. Budget fields are `maxTools`, `allowedRiskLevels`, `allowedTools`,
  and `deniedTools`.
- Preserve the input `toolProfileBudget` metadata and record resolved enforcement
  separately as `resolvedToolProfileBudget` with source, budget, configured tool
  count, active tool count, and dropped tool count.
- Invalid explicit `metadata.toolProfileBudget` records
  `reason=invalid_metadata_budget` and does not silently fall through to tenant or
  global runtime settings; invalid `tools.profile_budget` runtime settings record
  source/key/tenant/reason evidence. Unknown or misspelled budget fields are invalid;
  the four budget fields form a closed policy schema.
- Keep Reactor's tenant, logical `thread_id`, and product `checkpoint_ns` as the
  application checkpoint identity. Map that tuple to an opaque tenant-scoped
  LangGraph `config["configurable"]["thread_id"]`, set LangGraph's framework-owned
  root `checkpoint_ns` to `""`, and set a positive `recursion_limit` on durable
  direct-graph and LangChain-agent invocations as the loop-exit budget. Never use a
  product namespace as LangGraph's root namespace; non-empty values identify
  subgraph paths and cause root replay pins to be cleared.
- Native LangGraph invoke, HITL resume, and stream calls use distinct framework
  `run_name` values with the shared `runtime:langgraph` tag and secret-free
  `reactor.runtime=langgraph` metadata.
- Use `MessagesState` or `Annotated[list[AnyMessage], add_messages]`.
- Tool results are `ToolMessage(tool_call_id=...)`, including errors.
- Human approval uses LangGraph interrupts plus Reactor approval rows.
- State schemas are versioned. Breaking changes need migration or invalidation.
- Checkpoint fork APIs must create a new run under caller access control, use a
  new or requested `thread_id`/`checkpoint_ns`, and persist provenance metadata:
  `forkedFromRunId`, `forkedFromThreadId`, `forkedFromCheckpointNs`, and optional
  `forkedFromCheckpointId`, plus trusted target metadata `forkTargetThreadId` and
  `forkTargetCheckpointNs`.
- Only the typed internal fork capability created after the fork API authorizes the
  source run may select a `checkpoint_id`; request metadata alone never authorizes
  replay and all provenance-shaped user metadata is stripped. Same-scope replay may
  pin the selected checkpoint directly; cross-scope fork must read it through the
  configured LangGraph saver and materialize it into an empty tenant-scoped target
  root before invocation. Missing source checkpoints, pending writes, unavailable
  savers, or non-empty targets fail closed. When the fork body omits `checkpointId`,
  the fork API may derive trusted provenance from the source run's persisted
  `last_checkpoint_id`. Ignore user-supplied checkpoint metadata keys outside the
  fork contract.
- A checkpoint-bearing fork must preserve its source execution contract: runtime
  (`langgraph` or `langchain_agent`) and graph profile must match the target before
  saver reads or writes. Runtime/profile changes require a fresh run without a
  checkpoint pin.
- User-controlled chat metadata strips checkpoint provenance keys, including
  `source`, `checkpointId`, `checkpoint_id`, `forkedFrom*`, and `forkTarget*`.
- Fork APIs scrub stale fork provenance from source/request metadata before writing
  the new trusted provenance; stale `forkedFromCheckpointId` must not replay-pin a
  later fork and stale target metadata must not mislabel the new branch. Explicit
  fork checkpoint IDs are trimmed before becoming trusted provenance or LangGraph
  `checkpoint_id` config.
- `langgraph.json` is for local dev and Studio, not the product API.

## Critical Invariants

1. Guard stages fail-close. Hooks fail-open except cancellation.
   Input and output guard block exceptions expose structured, raw-content-free metadata such as
   stage, reason, run id, tenant id, and graph node; completed run metadata
   preserves this as `guardBlock` when a guard rejects a run.
   Tool outputs are sanitized before model-visible ToolMessage or prompt context:
   label as `[tool_output:data]`, redact canary secrets, and record guard findings.
   Context manifests preserve tool-output guard counts and findings.
   LangChain `ToolRetryMiddleware` exhaustion uses Reactor's fixed
   `[tool_output:data]` envelope. Raw exception types, messages, and tool names must
   not become model-visible. Automatic tool retry is allowlisted to enabled,
   approval-free `read` tools; write, destructive, and external-side-effect handler
   exceptions or timeouts become `requires_reconciliation` without automatic replay.
2. Tool approval, timeout, budget, max tool calls, and loop exit are code policy.
3. When `max_tool_calls` is reached, remove active tools and ask for a final answer.
4. Message trimming never breaks assistant/tool response pairs.
5. Tool output, retrieved text, MCP resources, uploads, and web pages are untrusted.
6. Tenant and ACL filters happen before vector/full-text ranking and before `LIMIT`.
7. Memory is not checkpointing. The application owns memory lifecycle, deletion, and evals.
8. Redis is not durable source of truth.
9. External side effects require outbox/idempotency records before dispatch.
10. Side-effect retries require upstream idempotency or reconciliation.
11. Set `LANGGRAPH_STRICT_MSGPACK=true` before LangGraph imports.
12. Normalize checkpoint-bound product state before graph invocation. Pending tool
    requests use the versioned `reactor.pending_tool_request.v1` JSON-safe schema;
    custom objects and unknown schema versions fail closed.
13. New graph inputs receive the current `state_schema_version`; reject incompatible
    input before checkpointing and validate the version at every node so stale
    durable replay cannot resume midway.
14. Native approval resumes use `reactor.approval_resume.v1`; reject unexpected
    fields and external `Command.update`, `goto`, or `graph` controls before
    LangGraph invocation.
15. LangChain HITL resumes allow exactly one approve/reject decision. Reject edit
    or multiple decisions and external `Command` controls before invocation.
16. No untrusted LangChain object deserialization.
17. LangChain native `structured_response` is authoritative when present; empty
    native structured responses fail closed for invoke and stream without message
    or token fallback. Streaming accepts identical root replay but fails closed on
    conflicting root structured responses instead of using last-write-wins. Native
    LangGraph streaming follows the same replay rule for root response text and
    metadata.
18. Unserializable native structured-response objects fail closed with a safe
    error code and do not expose raw objects or serialization exceptions.
19. Native LangGraph and LangChain paths share bounded RAG citation normalization.
    Invalid or oversized IDs are count-only, never persist raw in manifests, and
    never count as manifest citations or cited chunks. LangChain runtime RAG
    artifact manifests must match evidence recomputed from the versioned labeled
    durable envelope; mismatches are invalid count-only artifacts. Tool artifact
    `model_visible_text` must also exactly match authoritative
    `ToolMessage.content`; mismatches reject invoke and stream runs without
    exposing either value or a success response. Every model-visible tool message
    must carry the `[tool_output:data]` label; unlabeled output is a count-only
    invoke/stream failure and its raw content is never persisted. Mapping-wrapped
    LangChain `on_tool_end` message state and LangGraph `Command.update` messages
    pass through the same guard.
20. RAG citations must identify returned chunks. Orphan and duplicate claims are
    count-only diagnostics, do not inflate grounding counts, and fail structured
    output closed.
21. Citation source, document, chunk-index, and content-hash provenance must not
    contradict the matched chunk; mismatches are count-only fail-close evidence.
22. Duplicate returned chunk citation IDs are ambiguous: reject last-write-wins
    and one-citation-to-many-chunk grounding as count-only fail-close evidence.
23. Native explicit citation IDs are authoritative. Legacy document/chunk-key
    fallback never aliases two conflicting explicit IDs.
24. Every returned RAG chunk requires a safe explicit citation ID. Missing or
    invalid chunk IDs stay uncited as count-only evidence, and partially grounded
    structured output fails closed. Validate the original ID exactly at ingestion
    and manifest-read boundaries; never trim or normalize it into validity.
25. No LangChain object/prompt `load`/`loads` APIs, `secrets_from_env=True`, or
    user-controlled serialized configs in product request paths; architecture
    static tests must reject forbidden LangChain load imports and non-literal
    dynamic imports.
26. No user-controlled checkpoint metadata keys or retrieval filter keys.
27. No SQLite checkpointer in production.
28. No LangGraph cache backend with pickle fallback enabled.
29. No secrets in config defaults, prompts, logs, traces, or model-visible context.
30. Cancellation propagates through `asyncio.CancelledError` for native LangGraph
    and LangChain invoke paths. Invoke and stream timeouts cancel the underlying
    coroutine or async generator rather than only returning a timeout status.
    External cancellation during stream runtime execution persists terminal
    `cancelled` state before re-raising, including cancellation during approval-row
    persistence after a streamed interrupt or final response filtering. The
    tenant-scoped persistence transition is atomic and only permits
    `running -> cancelled`, preserving existing terminal results. A cancellation
    racing the final completion transaction resolves to `cancelled` before commit
    or preserves the committed terminal result after commit. Cancellation while
    persisting the final model-visible token event or a post-interrupt approval
    event also persists terminal `cancelled` state before re-raising. Explicit
    client stream closure after the started event or after the final model-visible
    token also transitions the run to terminal `cancelled` before completion
    persistence. The same applies after a durable post-interrupt approval event is
    delivered. A successful `running -> cancelled` transition atomically cancels
    tenant/run-scoped pending approvals so a cancelled run cannot be approved
    later. It also cancels only unexecuted `started` tool-invocation claims with
    the `approval_required` marker; other `started` claims remain reconciliation
    candidates. The explicit cancel API uses this same atomic transition and
    accepts `running` or `interrupted` runs while returning conflict instead of
    overwriting a terminal run.

## Tool, MCP, And A2A Rules

- Tools are model-facing APIs. Prefer 10-20 active tools per graph profile.
- Every tool has Pydantic input/output schemas, risk level, timeout, idempotency key,
  audit event, and recovery-friendly error shape.
- Use official Python protocol packages: `mcp`, `langchain-mcp-adapters`, `a2a-sdk`.
- MCP tools use fully qualified names: `ServerName:tool_name`; runtime MCP
  registration is data, not static config.
- Authenticated MCP registrations fail preflight unless a scoped credential-binding
  layer is available; never connect by passing through unrelated provider or user
  tokens.
- Slack is split: the native gateway owns Events API/Socket Mode ingress, slash and
  interaction ACKs, assistant/thread UX, response URL delivery, FAQ/proactive
  workflows, and current-thread replies. Slack MCP is optional model-facing
  workspace capability.
- Do not expose overlapping native Slack write tools and Slack MCP write tools in
  the same graph profile unless tool policy selects one route.
- A2A is external agent-to-agent task interoperability, not Reactor's internal graph
  runtime or local tool protocol.
- A2A agent cards are versioned and secret-free; A2A tasks map to Reactor run/thread,
  event, idempotency, auth, guard, approval, and audit records.
- Write, destructive, external-side-effect, shell, browser, and file-write tools need
  approval or sandbox policy.
- Tool output is sanitized before it re-enters model context.
- A profile that needs more than 20 model-visible tools requires a tool-selection or
  subgraph strategy, not a larger default prompt surface.

## RAG And Memory Rules

- LangGraph orchestrates RAG; RAG itself is ingestion, chunking, embedding, retrieval,
  context assembly, generation, and citation.
- PostgreSQL/pgvector is the v1 retrieval and memory default.
- `langchain-postgres` is default. Do not directly pin standalone `pgvector==0.4.2`
  while `langchain-postgres 0.0.17` requires `pgvector<0.4`.
- Missing ACL, missing `visibility`, unknown visibility, or malformed ACL data denies
  retrieval; do not default restricted company documents to tenant-visible access.
- LangMem proposes/extracts/consolidates memories. Promoted facts live in
  application-owned tables.
- RAG tool outputs redact raw ACL metadata and internal `acl_user_*`/`acl_group_*`
  markers from model-visible chunk payloads using normalized, case-insensitive
  metadata keys; ACL state is authorization data, not answer context.
- Context manifest metadata also drops raw authorization fields such as `acl`,
  `acl_proof`, `acl_visibility`, `acl_users`, `acl_groups`, and internal
  `acl_user_*`/`acl_group_*` markers while preserving safe evidence such as
  `acl_hash`, citation ids, source URI, document id, chunk index, and content hash.
- RAG-backed structured answers cite `context_manifest` evidence through the response
  schema when the output format supports it. The model sees source/citation labels,
  not ACL proof.
- Memory and RAG sections record manifest evidence counts. RAG tool context records
  direct context count, tool chunk count, cited/uncited chunk counts, citation
  count, and all sanitized citation IDs from both legacy single-id and citation-list
  manifest fields so structured-output schemas can reject unknown sources.
- Only citation IDs matching returned RAG chunks contribute to grounding. Orphan
  and duplicate claims remain count-only diagnostics and fail structured output
  closed.
- Returned RAG chunks without safe explicit citation IDs remain uncited and are
  count-only failures; a valid citation for another chunk does not make the
  partially grounded response safe. Noncanonical IDs are rejected as supplied,
  not trimmed or normalized into safe IDs, including when reading a persisted or
  caller-provided manifest.
- Each context manifest section records `content_checksum` over model-visible
  redacted section content so replay/fork/eval review can detect context drift.
- Structured memory items expose only memory content to the model. Memory ids,
  source ids, confidence, reviewer/proposal metadata, and extraction prompt versions
  stay in `context_manifest` evidence.
- Non-active memories, including tombstoned memories, are excluded from model-visible
  context and recorded only as skipped/status evidence in the manifest.
- Structured memory records with ids or source ids require explicit `active` status;
  missing status is skipped rather than treated as active.
- External memory frameworks are graduation candidates only after eval evidence.

## Verification

Use the narrowest command that proves the change. Then widen if the package boundary
or release risk requires it.

Harness-grade verification leaves an executable trail:

- Write or select the smallest focused RED test or smoke check before changing
  behavior.
- Feed type/lint/test/tool errors back into implementation; do not rely on prompt
  wording where a deterministic guard or test can own the rule.
- Preserve partial-test strategy: focused tests during iteration, affected lane
  tests before commit, full gate only for broad/runtime/security/dependency/release
  risk.
- Runtime changes should exercise the real harness: LangGraph state/checkpoints,
  LangChain middleware/tool contracts, LangSmith/OpenTelemetry redaction, RAG ACL
  filters, and release smoke reports.

Default migration loop:

1. RED: run exactly the focused test for the new or missing behavior.
2. GREEN: rerun that test and the nearest affected test file.
3. Commit-ready: run static gates and the affected lane tests.
4. Batch/release-ready: run the full gate when a batch crosses runtime, persistence,
   auth/security, RAG ACL, durable job, dependency, or cutover boundaries.

```bash
uv lock --check
ruff check
ruff format --check
pyright
pytest
```

Full `pytest` is not required after every small TDD slice. Prefer focused commands
such as `pytest tests/integration/test_chat_api.py tests/unit/test_run_service.py -q`
while iterating. Run full `pytest` before marking a ledger area `verified`, before
release/cutover evidence, or after broad shared changes.

Targeted checks:

- Graph: state transitions, checkpoint/resume, interrupt/resume, message-pair tests.
- Tool: schema validation, recovery errors, output sanitization, idempotency, approval.
- RAG: retrieval eval, ACL-before-ranking, citation accuracy, poisoning tests.
- Memory: proposal promotion, conflict handling, deletion/tombstone, retrieval eval.
- Durable jobs: queue reclaim, fencing token, outbox/inbox idempotency.
- API: OpenAPI/schema snapshot and streaming event contract.

No feature is complete without at least one focused regression test. Safety-sensitive
features require paired malicious and safe inputs.

## Commit And PR

- Commit prefixes: `feat:` `fix:` `refactor:` `sec:` `perf:` `docs:` `chore:` `test:` `ops:`.
- Mention cost impact when model calls, retries, context size, or eval volume increase.
- Mention security impact when tool policy, MCP, A2A, auth, secrets, sandbox, RAG, or
  memory behavior changes.
- Do not commit secrets or local-only config.

## Project Docs

When architecture, module boundaries, commands, or safety rules change, update:

- `docs/architecture/python-langgraph-replatform-spec.md`
- `docs/architecture/agent-harness-operating-model.md`
- `AGENTS.md`
- `CLAUDE.md`

# Reactor Python/LangGraph Replatform Specification

Status: final planning baseline
Date: 2026-06-26
Scope: full Python replatform with LangChain and LangGraph; no previous backend runtime

## Decision Summary

Reactor will move to a Python-first architecture. This is a greenfield serving-path
design that can reuse prior product learning, but it is not constrained by the prior
code structure, module boundaries, endpoints, or implementation patterns.

- Runtime: Python 3.13.14
- API/control plane: FastAPI
- Agent runtime: LangGraph, embedded in the Reactor app process
- Model/tool/protocol integration: LangChain provider packages, MCP, and A2A
- RAG implementation: LangChain retrieval components backed by Postgres/pgvector
- Source of truth: PostgreSQL 18 + pgvector
- Redis: production profile dependency, not the durable source of truth
- Durable execution: Postgres-backed run queue, outbox, inbox, and idempotency ledger
- Artifact storage: Postgres metadata plus S3-compatible blob storage in production
- Prompt/context/model governance: versioned records with per-call context manifests
- Package manager: uv with a committed lockfile

The prior implementation is reference inventory, not a structural contract. Preserve
only product and safety invariants that still matter in the new architecture:

- Guard stages fail-close.
- Hooks fail-open except cancellation.
- Tool execution is deterministic code, never prompt-only policy.
- Tool approvals, timeouts, max tool calls, audit logs, and usage accounting are enforced in code.
- Long-running work is resumable through checkpoints plus a durable job/outbox contract.
- Prompt, model, retrieval, memory, and tool changes are versioned and eval-gated.
- Hardening tests are required for new safety behavior.

Framework-native first:

- Prefer LangGraph, LangChain, FastAPI, Pydantic, SQLAlchemy, Alembic, MCP SDK, A2A
  SDK, LangSmith, and OpenTelemetry capabilities when they satisfy the product and
  safety requirement.
- Build application-specific code only for product policy, tenancy, ACL, approval,
  idempotency, audit, durable side effects, memory lifecycle, context manifests, eval
  gates, or integration behavior the framework does not own.
- Remove prior custom mechanisms when the new framework provides the same behavior
  with acceptable observability, durability, and testability.
- Do not recreate previous module boundaries, endpoint shapes, settings, or extension
  points unless a current product requirement needs them.

Non-goals:

- Do not keep the previous backend runtime in the serving path.
- Do not introduce a second primary backend language.
- Do not preserve previous package/module/API shape for its own sake.
- Do not duplicate framework-managed graph, protocol, validation, serialization,
  migration, tracing, or provider-integration behavior without a concrete gap.
- Do not make LangGraph Platform the only product API surface.
- Do not store durable agent state in Redis.
- Do not use a Redis queue as the source of truth for long-running agent work.
- Do not add a dedicated vector database before pgvector fails measured gates.

## Product Topology

Reactor is not a single-user local assistant, but it should still be a product
platform that individuals can use directly. The target shape is centrally managed
personal agent workspaces: a control plane governs policy, tenants, identity, model
and tool access, audit, billing, and safety, while each user gets durable personal
sessions, memories, tools, integrations, and task history under that central policy.

The closest structural analogy is not a pure backend API and not a purely local
personal agent. It is a managed agent product similar in product surface to systems
that expose a shared agent core through multiple clients and integration gateways.
The difference is ownership and safety: Reactor's core policy, tenancy, data
retention, approvals, and observability are centrally enforced.

Required product surfaces:

- **Control plane:** FastAPI admin/user APIs for tenants, users, policies, tool/MCP
  registries, prompts, memory, RAG, usage, audit, jobs, and evals.
- **Personal workspace surface:** user-scoped runs, threads, checkpoints, memories,
  artifacts, preferences, tool permissions, and integration identities.
- **Gateway surface:** Slack and future messaging/event gateways route user activity
  into the same LangGraph run service, not a separate agent runtime.
- **Protocol surface:** MCP and A2A expose controlled extension/interoperability
  without turning every integration into core code.
- **Operator/developer CLI:** migration, diagnostics, cutover, worker, and local
  development commands are first-class product operations. A user-facing CLI or
  desktop client may be added later, but it must call the same product APIs and
  policy layer instead of bypassing them.
- **Optional client apps:** web, desktop, or TUI shells belong at the edge of the
  monorepo or separate clients. They must not duplicate the agent core.

Slack integration strategy:

- Slack has two planes. The native Slack gateway owns product ingress and UX:
  Events API or Socket Mode, slash commands, interactions, assistant thread events,
  response URL delivery, FAQ/proactive workflows, tenant bot registration, signing
  secret verification, retry/ACK deadlines, idempotency, and durable outbox routing
  into LangGraph runs.
- Slack MCP is optional model-facing workspace capability, not gateway plumbing.
  Use Slack MCP tools for user/admin-authorized workspace actions such as search,
  channel/thread lookup, user lookup, message send, reactions, or canvas access when
  tenant policy, OAuth scopes, and graph profile allow them.
- Do not replace Slack Events API, Socket Mode, slash-command ACKs, interaction ACKs,
  response URL handling, or assistant/thread UX with MCP. MCP does not provide the
  product event lifecycle Reactor must control.
- Avoid exposing overlapping native Slack write tools and Slack MCP write tools in
  the same graph profile unless tool policy selects one route. Product replies to
  the current Slack thread go through the native gateway. Cross-channel or
  user-authorized workspace actions go through namespaced Slack MCP tools.
- Slack context is structured state, not a raw channel transcript. Gateway payloads
  and MCP search/read results are tainted external content until sanitized, source
  labeled, tenant/user authorized, rate budgeted, and cited.
- Prompt/context assembly must say whether Slack workspace tools are loaded. If no
  Slack MCP or native Slack tool is available, the agent must not claim it can search
  history, list users, manage channels, pin messages, or send cross-channel messages.
- Audit both native gateway actions and Slack MCP calls with tenant, team, channel,
  thread, user, triggering principal, model/profile, action, scope class, latency,
  status, and redacted payload metadata.
- Follow least-privilege Slack scopes. Expanding Slack read/write capability requires
  explicit tenant/admin approval and updated policy records.

Structure rule:

- Reactor may become a product monorepo, but the backend package remains the
  source of truth for policy and agent execution. Client apps, gateways, and plugins
  live at the edges and call the core through stable APIs/protocols.
- The operator web client is implemented at `apps/admin`. It remains an
  independently built and deployable React application; repository-root
  orchestration may compose it with the backend, PostgreSQL, and Redis without
  moving policy or durable state into the browser package.
- Add plugin-like boundaries only for real extension categories: model providers,
  MCP servers, tools, memory backends, retrieval profiles, observability exporters,
  and client/gateway adapters.
- Keep the core narrow. New model-visible tools or always-on context are expensive
  for every user and must pass tool-risk, prompt-budget, audit, and eval gates.
- Personalization is a first-class product concern, but it is always scoped by
  tenant, user, ACL, retention, and deletion policy.

## Framework Ownership

| Layer | Framework-owned by default | Application-owned only when needed |
| --- | --- | --- |
| Graph runtime | LangGraph state graph, message merge, interrupts, streaming, checkpoint APIs | graph profile policy, approval rows, product run records |
| Model integration | LangChain provider packages and tool-call abstractions | routing, budget, fallback constraints, provider policy |
| API boundary | FastAPI routing, OpenAPI, request parsing; Pydantic validation | authn/authz, tenancy, product DTO versioning, audit |
| MCP | official MCP SDK transports, protocol negotiation, serialization | server registry, credential scope, tool risk and access policy |
| A2A | official A2A SDK agent card, endpoint, tasks, protocol serialization | peer trust policy, task-to-run mapping, push outbox, audit |
| Persistence | SQLAlchemy sessions/models and Alembic migrations | product schema, RLS/ACL, idempotency, outbox/inbox semantics |
| RAG adapters | LangChain vector store/retriever interfaces | ACL-before-ranking, citation contract, ingestion policy, evals |
| Memory helpers | LangGraph stores and LangMem extraction/consolidation helpers | canonical memory schema, deletion, promotion, conflict policy |
| Observability | LangSmith and OpenTelemetry spans/exports | redaction, cost ledger, product metrics, compliance retention |

If a framework can own a concern, do not wrap it in a Reactor abstraction until there
are at least two implementations, a testability problem, or a product policy gap.

## Agent Harness Operating Baseline

Reactor treats agent quality as a harness property, not a model-only property. The
long-form operating rules live in `docs/architecture/agent-harness-operating-model.md`.
This spec owns the architectural implications:

- Instruction files are navigation maps. Durable rules belong in this spec or the
  harness operating model; repeated mistakes must become tests, smoke gates, evals,
  static checks, or typed policy surfaces.
- CodeGraph is the preferred structural exploration tool for symbol ownership,
  call paths, impact, and package layout: use `codegraph_context` for broad
  structural context, `codegraph_trace` for flow, `codegraph_impact` for blast
  radius, and `codegraph_status` for index health. Use `rg for literal` string
  checks and after a specific file is already identified.
- Local focused verification is required. Remote CI may mirror checks, but Reactor
  cannot depend on remote automation as its confidence mechanism.
- Full `pytest` is reserved for cross-boundary/runtime/security/persistence/RAG ACL,
  dependency, release, or cutover evidence. The inner loop remains RED, GREEN,
  affected lane, then static gates.
- LangSmith and OpenTelemetry provide trace/eval mechanics, but Reactor owns
  redaction, tenant scoping, release gate meaning, cost metadata, and retention.
- Named release gates must preserve their canonical `scope`, `owner`, `mode`, and
  artifact identity; release readiness fails closed on passed reports with the wrong
  identity before trusting their evidence facets.
- Agent harness source basis as of 2026-06-29: OpenAI harness engineering guidance,
  OpenAI Codex/App Server/Symphony runtime guidance, Anthropic effective-agent
  patterns, the Agentic Harness Engineering paper, LangChain/LangGraph/LangSmith
  official docs, and HumanLayer 12-factor agent principles. These are input
  references, not authority above Reactor security and durability invariants.
- Reference freshness is an operating requirement: revisit the source basis when
  LangChain/LangGraph/LangSmith major APIs shift, when always-loaded instruction
  files gain new rule classes, or before runtime-changing releases.

Reactor treats harness quality as a three-layer loop:

- **Component layer:** editable harness components have owners and executable
  contracts: instruction files, prompt releases, graph nodes, LangChain middleware
  policy, tool schemas, MCP/A2A adapters, context manifests, eval rubrics, smoke
  scripts, and release evidence.
- **Experience layer:** traces, logs, tool transcripts, and eval outputs are
  compressed into durable artifacts: failing tests, eval cases, smoke reports,
  trace references, or dated implementation plans.
- **Decision layer:** each harness change states which failure class it should
  reduce and which local verification or LangSmith experiment will confirm it.
  Failed predictions become new tests or a rule rollback, not more prompt prose.

Every durable instruction needs a Rules-to-sensors matrix entry: a feedforward rule
in docs, policy, prompt release, or typed API, plus a feedback sensor such as a
focused test, static gate, eval, smoke report, trace contract, or release artifact.
Rules without sensors should not live in always-loaded instruction files.

LangSmith usage is split deliberately:

- LangSmith offline evals compare graph, prompt, model, context, and tool-policy
  releases against curated datasets before deployment.
- LangSmith online observability watches production traces, feedback, anomalies,
  latency, cost, and safety signals after deployment.
- Online incidents graduate into offline eval cases before they block future
  releases.
- Reactor owns redaction, tenant scope, dataset release policy, retention, and
  cost metadata for both modes.
- Local release/eval gate reports are machine-readable artifacts with `ok`,
  `status`, `scope`, and `evidence` fields. `reactor-hardening-suite` owns the
  local agent hardening release gate and records artifact path, intended command,
  owner package, pass/fail/skipped status, LangGraph stage/subgraph topology
  evidence including per-subgraph `nodes`, `nodeCount`, and `checkpointMode`, and
  tool profile budget contract evidence.
- `reactor-langsmith-eval-sync` reports carry the same machine-readable evidence
  contract plus `datasetName`, the source suite path, enabled-case count,
  deterministic `exampleIds`, `metadataCaseIds`, `splitCounts`,
  source-suite-bearing `datasetMetadata`, a metadata-only `exampleContract` with
  `secretScan`, and `sdkContract` naming LangSmith `Client`, `has_dataset`,
  `create_dataset`, `create_examples`, `kv` data type, deterministic example ids,
  source-controlled cases, and max concurrency 1. LangSmith datasets are managed experiment
  surfaces, while source-controlled suites remain the release gate source of truth.
  Dataset example sync rejects secret-shaped keys and values before calling
  LangSmith so inputs, outputs, metadata, and dynamic field names cannot leak live
  credentials into managed eval data.
- `reactor-observability-smoke` reports carry privacy evidence plus `feedbackLoop`
  metadata connecting LangSmith online traces/feedback to source-controlled offline
  eval gates, and readiness aggregation preserves that facet. `promotedCaseIds`
  must reconcile with the LangSmith eval sync `caseIds` so online findings cannot
  claim offline coverage without synced source-controlled cases.
- `reactor-release-readiness-evidence` aggregates observability, hardening, eval,
  and other gate reports into one `release_readiness` artifact. Skipped gates block
  readiness, skipped report reasons stay visible for remediation, and malformed
  gate reports fail closed, so release review never depends on reading raw logs.
- Readiness aggregation preserves structured privacy evidence from gate reports.
  The LangSmith observability gate must expose its trace privacy contract
  (`hideInputs`, `hideOutputs`, `hideMetadata`, and required redaction check) in
  the aggregate without exposing raw inputs, outputs, metadata, secrets, or PII.
  It also carries `redactionCoverage`, the named field set exercised by the local
  redaction smoke.
- The observability gate also exposes `observabilitySdk`, proving the
  framework-native tracing path: LangSmith tracing/privacy environment keys for
  managed traces and OpenTelemetry `TracerProvider`, `BatchSpanProcessor`, console
  and OTLP/HTTP exporters, resource attributes, sampler, and provider
  force-flush/shutdown on FastAPI lifespan exit for local/OTLP export.
- The observability gate also exposes `observabilityTarget`: trace provider,
  LangSmith project, endpoint, span name, and `secretFree=true`. This identifies
  the smoke target in release readiness without exposing API keys or raw trace
  payloads. Secret-bearing target fields are dropped from aggregate readiness
  evidence and fail the observability target contract.
- Readiness aggregation also preserves allowlisted review evidence facets from
  gate reports: LangGraph `graphTopology`, tool profile budget contract, LangSmith
  `datasetName`, `sourceSuite`, `enabledCases`, `exampleIds`,
  `metadataCaseIds`, `splitCounts`, `exampleContract`, `sdkContract`,
  `observabilitySdk`, API boundary `apiBoundary`, and context manifest
  `contextManifest`, LangChain middleware policy `langchainMiddlewarePolicy`, and
  checkpoint fork/replay provenance `checkpointProvenance`, plus structured output
  strategy and repair boundary `structuredOutput` and research answer contract
  `researchAnswerContract` and tool invocation lifecycle
  `toolInvocationLifecycle`, A2A protocol `a2aProtocol`, MCP preflight
  `mcpPreflight`, Slack/MCP surface policy `slackMcpSurfacePolicy`, and memory
  maintenance lifecycle `memoryMaintenanceLifecycle`, RAG ingestion lifecycle
  `ragIngestionLifecycle`, artifact lifecycle `artifactLifecycle`, prompt release
  lifecycle `promptReleaseLifecycle`, approval lifecycle `approvalLifecycle`, plus
  provider fallback policy `providerFallbackPolicy` and LangGraph fault tolerance
  `langgraphFaultTolerance`, plus checkpoint retention policy
  `checkpointRetentionPolicy` and streaming event contract
  `streamingEventContract`, plus context management lifecycle
  `contextManagementLifecycle`, usage/cost lifecycle `usageCostLifecycle`, and
  outbox/inbox lifecycle `outboxInboxLifecycle`, plus Redis coordination
  `redisCoordination`. Arbitrary gate payloads are not copied into the aggregate.
- `checkpointProvenance.storageSemantics` records and validates the opaque
  tenant/thread/product-namespace key strategy, LangGraph's empty root namespace,
  `BaseCheckpointSaver.aget_tuple`/`aput` materialization boundary, empty-target
  and pending-write guards, typed fork capability authority, typed chat namespace
  precedence over untrusted metadata, end-to-end streaming namespace propagation,
  graph-profile metadata sourced from the already-resolved durable namespace rather
  than overriding it, runtime/profile compatibility, supported materialization
  modes, and fail-close reasons.
- `langchainSerializationBoundary` preserves the LangChain serialization safety
  policy: `langchain_core.load.load/loads` are class-revival APIs with allowlists,
  namespace/import mapping, and optional `secrets_from_env`; Reactor forbids those
  object/prompt load paths for user-controlled configs and permits only trusted
  JSON contracts parsed into Reactor-owned schemas. Its `checkpointState` facet
  also proves new LangGraph inputs receive the current top-level state version,
  incompatible new inputs fail before the initial checkpoint, and every graph
  node rejects missing or stale versions so replay cannot resume midway under an
  incompatible schema. It further proves inputs are normalized before checkpoint,
  pending tool state uses the versioned
  `reactor.pending_tool_request.v1` JSON-safe schema, reducers normalize later
  updates, and catalog identity survives round trips. Native approval resume
  commands similarly use `reactor.approval_resume.v1`; unexpected fields,
  versions, or external `Command.update/goto/graph` controls fail closed before
  LangGraph sees the resume.
- `langgraphFaultTolerance.cacheSerialization` preserves the LangGraph cache
  serialization policy: `CachePolicy` defaults to pickle-based key hashing, so
  Reactor cache paths require custom key functions, disable pickle fallback, and
  keep side-effect nodes uncached.
- `checkpointRetentionPolicy` preserves `graphStoreRuntime` so release review can
  verify `AsyncPostgresStore` is the durable graph store, `InMemoryStore` is
  local/non-durable only, and LangChain `create_agent` receives the same graph
  store as Reactor graph execution.
- `redisCoordination` preserves Redis readiness evidence for ephemeral-only usage,
  production multi-replica requirements, at-most-once Pub/Sub wakeups, fail-closed
  rate limiting, cached Redis publisher client cleanup during `AppContainer.close()`,
  `runLifecyclePublisherClosedOnContainerClose`,
  `slackUserRateLimiterClosedOnContainerClose`, and the ban on durable Redis state
  or primary Redis checkpoints.
- MCP preflight readiness records authorization-security evidence for OAuth 2.1,
  PKCE, protected-resource metadata discovery, server-side token storage, and
  scope validation, plus rejection of authenticated registrations when scoped
  credential binding is unavailable.
- The hardening suite `researchAnswerContract` facet records that research
  answers require `requiresCitationIds=true` and `requiresSourceLabels=true`, use
  manifest-id citation style, disallow uncited claims, publish only
  `research_plan.answerContract` plus `research_plan.answerExtraction`, track
  content-hash mismatches and missing cited chunks, and include sources in
  deterministic fallback responses.
- The hardening suite `contextManagementLifecycle` facet records LangChain-native
  `SummarizationMiddleware`, `ContextEditingMiddleware`, `LLMToolSelectorMiddleware`,
  and provider tool search coverage plus Reactor safeguards for context manifest
  checksums, tool-call/tool-result pair preservation, tenant policy before context
  mutation, mutation audit, active-tool budget enforcement, selection reason audit,
  and raw-context exclusion from release evidence.
- The hardening suite `usageCostLifecycle` facet records LangChain
  `usage_metadata`, LangSmith token/cost tracking, Reactor's Postgres usage
  ledger, Prometheus cost metrics, tenant/run/session scoping, model breakdowns,
  admin token-cost and tenant-cost review APIs, token total validation including
  total-token breakdown matching, negative cost rejection, zero-cost recording,
  and quantized estimated cost.
- Live backend provider smoke evidence records LangChain
  `AIMessage.usage_metadata` token counts inside `backendProviderIntegration` and
  release readiness fails closed when the live provider invocation omits or
  malforms that usage metadata.
- The hardening suite `outboxInboxLifecycle` facet records replayable external
  side effects, incoming webhook/event de-duplication, Postgres `SKIP LOCKED`
  claim behavior, lease ownership, retry/dead-letter behavior, stale-owner
  dispatch protection, and replayable payload routing through the durable store.
- Live A2A peer-network smoke evidence is preserved as `a2aProtocol` so release
  review can verify SDK/protocol version, protocol endpoint availability, agent
  card metadata, task API behavior, diagnostics, audit, idempotency, telemetry,
  push-outbox routing, and secret-free public payloads including agent-card
  interface URLs and diagnostics endpoints.
- Context manifest evidence includes `memoryAdmissionPolicy` for active-only
  memory admission and `ragGroundingPolicy` for citation tracking, uncited chunk
  accounting, and ACL-hash-only retrieval evidence. Memory status counts must
  reconcile rendered active memory plus skipped memory so tombstoned and
  missing-status records remain visible to diagnostics and release readiness. Raw
  ACL metadata remains authorization data and is not model-visible context.
- RAG citations must carry nonblank source labels. When chunk metadata omits a
  usable `source_uri`, citation evidence falls back to the chunk `document_id`
  instead of emitting blank or stringified null source values.
- Memory maintenance evidence includes the LangMem manager contract plus a
  consolidation policy. The contract names `create_memory_manager`,
  `create_memory_store_manager`, `ainvoke`, the `messages` input key, `max_steps=1`,
  enabled inserts/updates, disabled LangMem deletes, and Reactor-owned deletion.
  Insert, update, and delete behavior is passed explicitly to the LangMem factory;
  Reactor must not rely on SDK defaults for lifecycle policy.
  Every extracted LangMem result must carry a nonblank SDK memory id before Reactor
  creates a proposal so review and audit provenance cannot silently disappear. Its
  extracted `content` must also be a nonblank string; missing fields, arbitrary
  mappings, and blank model output fail closed at the LangMem boundary.
  One extraction accepts at most 20 SDK memory results by default. Candidate overflow
  rejects the whole extraction instead of silently truncating or flooding the
  proposal review queue; the effective budget is recorded in proposal provenance.
  Reviewed promotion may supersede a prior active memory in the same namespace, the
  old item is marked `superseded`, and active context queries exclude superseded
  records. The memory approval review surface must expose a safe `maintenance`
  projection for API/CLI operators while keeping raw proposal `source_payload`
  private; release readiness preserves only contract metadata and records
  `sourcePayloadPrivacy` evidence that raw payload values, source payload keys,
  and unscanned secrets are not exposed. Dependency warning scans preserve
  LangMem/trustcall/LangGraph deprecations as `dependencyWarnings` release
  evidence instead of hiding them in test logs. When `pyproject.toml` exact pins
  block dependency remediation,
  evidence records `directPins` and `pinSource`; remediation updates those pins and
  runs `uv lock --upgrade-package langmem --upgrade-package trustcall --upgrade-package langgraph`.
- The hardening suite `graphTopology` facet identifies `composition` as
  `stage_subgraphs`, includes deterministic `subgraphOrder`, and exposes
  parent-level `subgraphEdges` separately from internal `nodeOrder`; this keeps
  LangGraph subgraph separation auditable without manually reading trace logs.
- `reactor-release-smoke-run --readiness-output` writes this aggregate directly
  after smoke execution, combining smoke run status and release evidence status in
  one machine-readable release-review artifact.
- Release smoke handoffs default `requiredReports` to `smoke_run` and
  `release_evidence` so the aggregate emits `requiredReports` and
  `missingReports` without relying on caller discipline. Missing required gates
  block readiness even when every submitted report passed.

Model-visible context, tools, and output contracts are part of the architecture:

- Every model call has a context manifest with governed section order, source type,
  taint labels, tenant/user scope, prompt release, and checksum.
- Context manifests are application-owned evidence. Public run, preflight, chat,
  and fork metadata must drop both `contextManifest` and `context_manifest` before
  execution so callers cannot inject a citation allowlist. The non-executing
  structured-output diagnostics endpoint may accept an explicit manifest solely
  to explain the resulting schema and citation boundary.
- Context manifest sections carry machine-checkable evidence counts and
  `content_checksum` values over model-visible redacted section content. Memory
  sections record memory count; RAG sections record direct context count, tool
  chunk count, cited/uncited chunk counts, citation count, and sanitized citation
  IDs. Citation evidence contributes to grounding only when its ID identifies a
  returned chunk; orphan and duplicate claims remain count-only failures.
  Model-visible context receives labels and redacted text, not ACL proof.
- Structured memory items render only memory content into model-visible context.
  Memory ids, source/proposal ids, confidence, reviewer metadata, and extraction
  prompt versions remain manifest evidence.
- Non-active memories, including tombstoned memories, are excluded from model-visible
  context. The manifest records skipped memory count and status counts so memory
  lifecycle decisions remain auditable without leaking deleted content.
- Structured memory records with ids or source ids require explicit `active` status.
  Missing status is counted as skipped `missing` status, not inferred as active.
- Tools are explicit APIs with schema, risk, timeout, idempotency, audit, and
  recovery-friendly error contracts. More than 20 model-visible tools in one
  profile requires tool selection, subgraphs, or profile splitting.
- Completed run metadata preserves requested `toolProfileBudget` separately from
  `resolvedToolProfileBudget`, which records the enforcement source, normalized
  budget, configured tool count, active tool count, and dropped tool count. Invalid
  explicit `metadata.toolProfileBudget` records `reason=invalid_metadata_budget`
  and does not silently fall through to runtime settings; invalid
  `tools.profile_budget` runtime settings record source/key/tenant/reason evidence.
  Tool profile budget objects use the closed field set `maxTools`,
  `allowedRiskLevels`, `allowedTools`, and `deniedTools`; unknown or misspelled
  fields are invalid so a typo cannot silently weaken the active tool boundary.
- LangChain middleware should own generic controls such as call limits, retries,
  fallback, PII handling, tool selection, summarization, context editing, and HITL
  only when Reactor can preserve audit, tenant policy, redaction, and usage ledger
  metadata.
- Compose `ModelFallbackMiddleware` outside `ModelRetryMiddleware`: exhaust the
  configured retry budget for the current model before trying the next fallback.
  The primary `create_agent(model=...)` model must not be duplicated in the
  fallback middleware's model list.
- Configure `ModelRetryMiddleware` and `ToolRetryMiddleware` with Reactor's
  transient-only predicate: timeout, connection, provider rate-limit/server errors,
  HTTP 408/409/425/429, and 5xx responses. Validation, authentication, permission,
  not-found, and other permanent failures do not consume retry budget. Explicit
  LangGraph model invocation uses the same provider-level predicate.
- Reactor policy is the single retry-budget owner. Initialize primary, fallback,
  and explicit LangGraph provider models with SDK-internal retry disabled
  (`max_retries=0`) so provider defaults cannot multiply middleware or graph retry
  attempts.
- Middleware evidence planning is side-effect free. Provider initialization belongs
  only to the agent runtime; metadata and reporting paths derive the deterministic
  middleware plan without constructing primary or fallback clients.
- Completed run metadata records `langchainMiddlewarePolicy.status=applied` for
  the effective policy and `status=ignored` with source/key/tenant/reason when a
  tenant or global runtime setting is invalid. Invalid explicit
  `metadata.middlewarePolicy` records `reason=invalid_metadata_policy` and does
  not silently fall through to runtime settings. Middleware policy objects and
  nested PII rule objects use closed field sets; unknown or misspelled fields are
  invalid rather than silently falling back to defaults.
- PII middleware policy evidence records `applyToInput`, `applyToOutput`,
  `applyToToolResults`, and `applyToStreamOutput` for every rule so release review
  can verify where redaction or blocking is active. With the current LangChain
  `PIIMiddleware` constructor, streamed output is governed by `apply_to_output`;
  Reactor rejects policies that claim a different `applyToStreamOutput` value.
- LangGraph durable execution, interrupts, stores, and streaming events are runtime
  contracts. Reactor keeps non-idempotent side effects behind approvals, outbox,
  inbox, or idempotency records because retries and resumes can replay nodes.
- Structured output should use concrete LangChain/Pydantic/provider schemas first.
  Completed run metadata records `structuredOutput.strategy`: `schema_passthrough`
  for explicit schemas, `json_object_schema` for JSON object fallback, and
  `reactor_boundary` for formats enforced only by Reactor response validation.
  Schema-less JSON structured output still requires an object shape; arrays and
  scalars are invalid unless an explicit schema permits them.
  Structured-output policy failures terminate as `rejected`, never `completed`;
  streaming returns the blocked response only in the terminal rejection event,
  not as a successful model token. Native LangGraph streaming treats final v2
  `on_chain_end.data.output` response text and metadata as authoritative over
  earlier model chunks, but only when the v2 event carries an empty `parent_ids`
  list proving it is the root graph termination. Missing, malformed, or nested
  lineage fails closed and cannot replace the root result. Identical root graph
  results may replay, but conflicting root response text or metadata fails closed
  with `native_graph_result_stream_conflict` instead of using last-write-wins.
  LangChain agent
  streaming reads native
  `structured_response` from that same explicit final-output envelope, serializes
  it with the invoke path's helper, and treats the field as authoritative even
  when its value is empty; empty native structured responses fail closed instead
  of falling back to token or message text. A v2 structured-response event must
  carry an empty `parent_ids` list, proving it is the root `on_chain_end`;
  missing, malformed, or non-empty lineage fails closed so nested chain responses
  cannot override root output. Repeated identical root structured responses are
  tolerated as replay, while conflicting root values fail closed with
  `structured_response_stream_conflict` instead of using last-write-wins.
  Release readiness also records supported LangChain response-format strategy
  surfaces: `ProviderStrategy`, `ToolStrategy`, direct schema types, and no
  structured response format.
  Invalid explicit `metadata.responseSchema` records
  `structuredOutput.ignoredSchema.reason=invalid_response_schema` instead of
  silently disappearing into JSON fallback.
  RAG-backed structured JSON answers must cite context-manifest evidence when
  citation metadata is available; missing or unknown citation IDs are policy
  failures. If RAG chunks are present but citation IDs are absent, structured JSON
  responses fail closed instead of accepting model-invented citations. Native
  LangGraph and LangChain paths use the same field allowlist and length
  bounds. IDs that are invalid or oversized remain diagnostic-only: exclude raw
  values from manifest citation lists and cited/grounded counts, and keep their
  chunks uncited.
  Valid-looking citation IDs must also match returned chunk IDs. Orphan and
  duplicate claims are excluded from citation and cited-chunk counts and fail
  structured output closed. A matched citation's source URI, document ID, chunk
  index, and content hash must not contradict the returned chunk; mismatches are
  excluded as count-only provenance failures. Duplicate citation IDs across
  returned chunks are ambiguous: never select the last chunk or let one citation
  ground multiple chunks; all affected chunks stay uncited and structured output
  fails closed. Every returned chunk must also carry a safe explicit citation ID;
  missing or invalid chunk IDs remain uncited count-only failures, and one valid
  citation cannot make a partially grounded response safe. Validate citation IDs
  exactly as supplied; leading/trailing whitespace or other noncanonical forms are
  rejected rather than normalized at both ingestion and manifest-read boundaries.
  When both native chunk and citation records
  provide explicit IDs, they must match exactly; legacy
  document/chunk-key fallback cannot alias an explicit-ID conflict. Citation enum
  generation must include every sanitized citation id from both legacy
  single-id and citation-list manifest fields. Run metadata and release evidence
  preserve `structured_output_allowed_citation_ids` so unknown-source rejection can
  be audited without inspecting raw context payloads.
  LangChain runtime RAG artifact manifests are admitted only when their chunk,
  citation, and failure-count evidence matches metadata recomputed from the
  versioned `[tool_output:data]` durable envelope. A mismatched manifest is an
  invalid runtime artifact: its claimed citation values are excluded and
  structured output fails closed.
  A tool artifact's `model_visible_text` is never more authoritative than the
  actual `ToolMessage.content`. When both are present they must match exactly;
  mismatches are recorded as count-only guard evidence and the invoke or stream
  run is rejected without exposing either value or a model success response.
  Every model-visible `ToolMessage.content` must also start with
  `[tool_output:data]`; unlabeled values are count-only failures and reject invoke
  and stream runs without persisting their content.
  When LangChain returns a native `structured_response` field, that field is the
  authoritative source for invoke and stream results. Empty native structured
  responses fail closed and never fall back to ordinary model message text.
  Streaming accepts identical replay of the root structured response but rejects
  conflicting root values with `structured_response_stream_conflict`.
  Provider objects that cannot be JSON-serialized also fail closed with the safe
  `STRUCTURED_RESPONSE_SERIALIZATION_FAILED` code; raw objects and exception text
  are not exposed.
- Human control uses LangGraph interrupts or LangChain HITL primitives for runtime
  semantics, plus Reactor approval rows for RBAC, expiry, audit, and resume
  provenance. Release readiness preserves an `approvalLifecycle` facet from the
  hardening suite. A passed gate must show the approval store/request/decision/row
  models, pending and terminal statuses, RBAC, tenant scoping, run access checks,
  nonblank rejection reasons validated at the API boundary before storage, resume
  provenance, audit, expiry support, Slack
  decision routing, native LangGraph direct/streaming and follow-up interrupt
  persistence, per-runtime approval-state matching, durable decision provenance
  with missing-actor fail-close, separated run-owner, decision-actor, and
  resume-actor audit identity, runtime-accurate atomic resume claims,
  persisted run identity as the authoritative runtime, owner, status, thread, and
  checkpoint namespace, fail-close mismatch rejection before resume claim, exact
  matching of the approval request's runtime, thread, and checkpoint namespace
  against that authoritative resume identity before claim, rejection of unsupported
  persisted runtimes before runtime dispatch, and revalidation of approved tools
  against the current catalog identity, enabled/approval policy, and resolved tool
  profile budget before claim. Missing or inactive tool policy fails closed for an
  approved execution; a rejection may still resume to finalize without executing
  the deactivated tool. LangChain HITL resumes are validated before invocation:
  exactly one approve/reject decision is allowed, edit decisions and external
  `Command` state/routing controls are forbidden. Public resume APIs accept only
  literal JSON booleans for `approved`; numeric and string coercions are rejected.
  Approval lifecycle evidence also covers terminal-state and resume-audit
  co-commit, exclusion of success audit on runtime failure,
  native-resume timeout, guard fail-close, provider usage-ledger, graph
  response-metadata preservation, retained run-policy metadata, and durable
  sanitized runtime failure coverage for both native LangGraph and LangChain HITL
  resumes. Approval-row persistence failure must fail closed to a recorded failed
  run rather than escape as a raw exception; streaming must still emit its terminal
  completion without publishing a phantom pending approval. Buffer the public
  approval event until approval-row persistence succeeds, then include the same
  durable `approval_id` in its public payload. Persisted event replay must retain
  that identifier and remove raw `tool_input`. Only fixed failure metadata is
  public, storage error details are excluded, cancellation propagates, and the
  returned approval id must normalize to a non-empty value before the interrupt
  is resumable. The facet carries focused verification sensors for these rules and
  proves that side effects before approval are forbidden.

## LangChain-Native Feature Adoption

Official LangChain v1 guidance treats agents as LangGraph-backed systems and exposes
middleware for common agent controls. Reactor must use these primitives wherever they
cover the generic behavior, then add Reactor code only for product policy, tenancy,
audit, or legacy compatibility.

Primary references:

- LangChain overview: https://docs.langchain.com/oss/python/langchain/overview
- Agents: https://docs.langchain.com/oss/python/langchain/agents
- Middleware: https://docs.langchain.com/oss/python/langchain/middleware
- Built-in middleware: https://docs.langchain.com/oss/python/langchain/middleware/built-in
- Guardrails: https://docs.langchain.com/oss/python/langchain/guardrails
- Retrieval: https://docs.langchain.com/oss/python/langchain/retrieval
- MCP: https://docs.langchain.com/oss/python/langchain/mcp
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph human-in-the-loop: https://docs.langchain.com/oss/python/langgraph/interrupts

Adoption rules:

| Concern | LangChain/LangGraph primitive first | Reactor-owned boundary |
| --- | --- | --- |
| Chat model creation | LangChain standard model interface through `init_chat_model` | `reactor.providers.chat_models` central factory, provider/model registry, tenant entitlement |
| Simple agent loop | `create_agent` or LangGraph prebuilt helpers | explicit custom graph only when policy gates, state shape, streaming contract, or retained API behavior require it |
| Model-call limit | `ModelCallLimitMiddleware` | tenant budget, usage ledger, billing, hard fail policy |
| Tool-call limit | `ToolCallLimitMiddleware` | Reactor max-tool policy, audit, recovery UX, legacy response metadata |
| Human approval | `HumanInTheLoopMiddleware` and LangGraph interrupts | approval rows, RBAC, audit, expiry, Slack/admin decisions |
| PII guardrail | `PIIMiddleware` for email, credit card, IP, URL, and similar generic patterns | tenant-specific rules, policy records, retention/deletion, compliance audit |
| Model retry | `ModelRetryMiddleware` | provider routing policy, cost caps, retry budgets |
| Tool retry | `ToolRetryMiddleware` | idempotency, side-effect classification, approval policy |
| Fallback models | `ModelFallbackMiddleware` | allowed provider/model registry, tenant entitlement, cost policy |
| Context trimming/summarization | `SummarizationMiddleware`, `ContextEditingMiddleware` | context manifest, source labels, taint metadata, prompt-release checksums |
| Tool selection | `LLMToolSelectorMiddleware`, provider tool search middleware | tool risk tier, active-tool caps, audit, deterministic allow/deny policy |
| Structured output | LangChain `create_agent(response_format=...)` | YAML/fallback repair, response metadata, output guard ordering |
| Retrieval/RAG | LangChain text splitters, retriever/vector interfaces, and `langchain-postgres` | ACL-before-ranking, citation contract, ingestion review, poisoning evals |
| Persistence/resume | LangGraph checkpointers, stores, interrupts, streaming | product run records, durable queue/outbox/inbox, cutover parity |
| MCP tools | `langchain-mcp-adapters` and official MCP SDK | registry, credentials, SSRF policy, tool naming, access policy |

Implementation rule:

- New simple model-tool loops should start from `create_agent(..., middleware=[...])`
  plus Reactor tools/policies. Custom LangGraph nodes are allowed only where Reactor
  must enforce policy between steps or preserve product/API behavior.
- The default middleware bundle is assembled in `reactor.agents.langchain_middleware`
  and must stay aligned with the installed LangChain version.
- Product runs can opt into the LangChain-native harness with `runtime=langchain_agent`.
  This path uses `create_agent` and the default middleware bundle while preserving
  Reactor run records, thread/checkpoint config, model metadata, and usage accounting.
- Container-built explicit LangGraph runtimes must receive chat models from
  `reactor.providers.chat_models` in non-fallback deployments, so the default graph
  model node uses LangChain's standard model interface instead of deterministic
  placeholder responses. Local containers may omit the model for no-key fallback tests.
- The LangChain-agent harness must receive the same LangGraph checkpointer that the
  explicit Reactor graph uses. Do not create a separate persistence mechanism for
  `create_agent`; map Reactor's tenant/thread/product-namespace tuple to the same
  opaque LangGraph root thread key used by the explicit graph, keep the framework
  root `checkpoint_ns` empty, and pass the container checkpointer to
  `create_agent(checkpointer=...)`.
- Reactor tools enter LangChain through `reactor.tools.langchain_adapter`. The adapter
  converts `ToolSpec` JSON Schema into LangChain `StructuredTool` args schemas, but
  execution still flows through `ToolExecutionRequest`, `ToolHandler`, admission
  policy, timeout, idempotency, and structured result payloads.
- MCP tools enter LangChain through `langchain-mcp-adapters`. Reactor owns only the
  product boundary around it: registry-to-connection normalization, credential binding,
  SSRF/access policy, audit, and model-visible `ServerName:tool_name` names. The
  upstream adapter's underscore prefix is not Reactor's public tool contract.
- Agentic RAG retrieval is exposed as a normal Reactor `ToolSpec` and then as a
  LangChain `StructuredTool`; the tool uses LangChain `init_embeddings` for query
  embeddings and Reactor's Postgres retriever for tenant/ACL-safe hybrid retrieval.
- Vector-store-native RAG paths use `langchain-postgres` `PGVector` through the
  `reactor.rag.vector_store` factory and the authorized wrapper exposed by the app
  container. Generic PGVector filters must be tenant and collection scoped, include
  user/group private ACL markers derived from authenticated execution context, and
  fail closed before vector ranking.
- RAG ACLs are explicit allow rules. Missing ACL, missing `visibility`, unknown
  visibility values, malformed users/groups, or untrusted caller-supplied ACL filters
  must deny retrieval instead of falling back to tenant-visible access.
- The RAG tool revalidates every retriever result against the trusted tenant,
  collection, principal, and group ACL context before producing model-visible chunks
  or citations, then caps authorized results to the validated request limit. This is
  defense in depth and never replaces SQL ACL filtering before ranking and `LIMIT`.
- App-owned RAG chunks expose a LangChain `Document` conversion boundary through
  `reactor.rag.documents`; canonical tenant, collection, document, chunk, hash, ACL,
  and citation metadata must travel with the document before vector-store insertion.
- Admin document ingestion accepts ACL as a first-class API field, not only as
  arbitrary metadata. Private or restricted company documents must be stored with
  explicit `visibility=private` plus allowed users/groups so retrieval can deny them
  before ranking.
- RAG tool ACL groups are trusted execution context, not model input. Do not expose
  caller groups in model-facing tool schemas; `ToolExecutionRequest.trusted_user_groups`
  is the only source for group ACL checks. API authentication resolves groups into
  `AuthPrincipal.groups` from signed JWT claims, tenant-scoped API keys, or
  explicitly local-only development headers,
  `RunService` copies them into `ReactorState.trusted_user_groups`, and graph/tool
  adapters copy that state into tool execution requests. Request bodies, chat metadata,
  prompts, and tool arguments must not grant or expand RAG groups.
- Do not add a custom guard, retry loop, fallback loop, PII scanner, summarizer, or
  tool selector before checking whether the current LangChain package already exposes
  middleware for that concern.
- Generic middleware is not enough for regulated product policy. Reactor still owns
  tenant isolation, source/citation metadata, ACL filters, approval records, audit
  logs, idempotency, cost ledger, and deletion lifecycle.
- Context trimming uses LangChain Core message utilities first. Reactor may keep only
  product-specific validity repair, such as preserving AI/tool-call message pairs.
- System prompt assembly uses LangChain `ChatPromptTemplate` through
  `reactor.context.prompt_templates`; Reactor still owns the governed section order,
  taint labels, prompt release hashes, and rendered checksum.
- Memory extraction uses LangMem managers first. Reactor owns proposal review,
  promotion, deletion/tombstones, ACLs, and persistence; it should not reimplement
  generic memory extraction loops when LangMem can produce candidate memories.
- Structured model outputs in the LangChain-agent runtime use
  `create_agent(response_format=...)` first. Prefer concrete Pydantic models,
  dataclasses, TypedDicts, or provider-supported JSON schemas for LLM output
  contracts; use the generic JSON object fallback only when no product schema exists.
  Reactor's graph-side structured validator/repairer remains for YAML, non-native
  runtimes, and fallback validation before output filters.
- LLM-as-judge paths use LangChain structured output first when the selected chat
  model supports `with_structured_output(...)`. Manual JSON parsing remains only as a
  compatibility fallback for non-native test doubles or providers.

## Runtime And Framework

| Area | Decision | Version |
| --- | --- | --- |
| Python | Latest compatible stable, not newest available | 3.13.14 |
| Package manager | uv | 0.11.24 |
| API framework | FastAPI | 0.138.1 |
| ASGI base | FastAPI-managed Starlette | lockfile transitive |
| ASGI server | Uvicorn | 0.49.0 |
| Validation | Pydantic | 2.13.4 |
| Settings | pydantic-settings | 2.14.2 |
| Redis client | redis | 8.0.1 |
| SSE helper | sse-starlette | 3.4.5 |
| JSON serialization | orjson | 3.11.9 |
| Retry utilities | tenacity | 9.1.4 |
| Slack SDK | slack-sdk | 3.42.0 |
| Slack SDK async transport | aiohttp | 3.14.1 |

Python 3.14.6 exists, but it is not the baseline. Python 3.13.14 is the latest
conservative baseline that keeps all required runtime packages on a mature supported
line. Track 3.14 as a compatibility lane after the default lockfile and integration
tests pass on 3.13.

Known package constraints behind this decision:

- `langgraph-checkpoint-redis 0.5.0`: `<3.15,>=3.10`
- `litellm 1.89.4`: `<3.14,>=3.10` if evaluated later as a provider gateway
- `presidio-analyzer 2.2.362`: `<3.14,>=3.10` if evaluated later for PII analysis
- `llm-guard 0.3.16`: `<3.13,>=3.10`; excluded from core

Do not pin Starlette directly in `pyproject.toml` unless Reactor imports Starlette APIs
outside FastAPI's supported surface. FastAPI owns the compatible Starlette range; the
resolved Starlette version belongs in `uv.lock`.

FastAPI is selected over Litestar because the LangChain/LangGraph Python ecosystem,
Pydantic-based schemas, OpenAPI tooling, examples, and hiring/operations familiarity
are stronger around FastAPI. Litestar remains a valid alternative, but switching to it
would not improve the core agent runtime enough to justify ecosystem friction.

## Agent Stack

| Area | Decision | Version |
| --- | --- | --- |
| Agent graph runtime | langgraph | 1.2.7 |
| LangGraph checkpoint core | langgraph-checkpoint | 4.1.1 |
| Postgres checkpointer | langgraph-checkpoint-postgres | 3.1.0 |
| Redis checkpointer | langgraph-checkpoint-redis | 0.5.0, optional only |
| LangGraph CLI/dev server | langgraph-cli | 0.4.30 |
| LangGraph SDK | langgraph-sdk | 0.4.2 |
| LangGraph prebuilt nodes | langgraph-prebuilt | 1.1.0 |
| LangChain facade | langchain | 1.3.11 |
| LangChain core | langchain-core | 1.4.8 |
| OpenAI integration | langchain-openai | 1.3.3 |
| Anthropic integration | langchain-anthropic | 1.4.7 |
| Google GenAI integration | langchain-google-genai | 4.2.6 |
| Retriever interfaces | LangChain custom retriever adapter | application-owned |
| Postgres vector store package | langchain-postgres | 0.0.17 |
| Community integrations | langchain-community | 0.4.2, optional |
| MCP Python SDK | mcp | 1.28.1 |
| MCP LangChain adapter | langchain-mcp-adapters | 0.3.0 |
| FastMCP convenience framework | fastmcp | 3.4.2, optional only |
| A2A protocol | Agent2Agent | 1.0 |
| A2A Python SDK | a2a-sdk[fastapi,telemetry] | 1.1.0 |
| Long-term memory tools | langmem | 0.0.30 |
| LangSmith | langsmith | 0.9.3 |

Use LangGraph as the explicit state machine. `create_agent` is acceptable for
prototypes and low-risk profiles. Policy-critical production profiles should expose
explicit nodes for guard, model, approval, tool execution, output guard, and hooks.

Library-first rule:

- Prefer official LangChain/LangGraph primitives over Reactor-owned
  reimplementations whenever they cover the needed agent behavior without weakening
  Reactor's deterministic policy contracts.
- Use LangChain `create_agent` or LangGraph prebuilt/tool-calling helpers for simple
  model-tool loops, prototypes, and low-risk internal agents. Promote to explicit
  LangGraph nodes only when Reactor must enforce tenancy, guard stages, approvals,
  audit, cost, or retained product contracts between steps.
- Use LangGraph persistence, interrupts, streaming, stores, subgraphs, and
  checkpoint packages for durable execution, human approval, resumability, and
  stateful orchestration. Do not hand-roll generic checkpoint, interrupt, or stream
  semantics outside the framework.
- Use LangChain provider integrations, tool abstractions, structured output,
  retriever interfaces, and `langchain-postgres` before custom adapters. Custom code
  belongs at Reactor's product boundary: policy, RBAC, audit, schema normalization,
  migration compatibility, and retained product behavior.
- Create chat models through `reactor.providers.chat_models` so provider swaps keep
  using LangChain's standard model interface instead of scattering provider SDK or
  `init_chat_model` calls across feature packages.
- Use LangMem for memory extraction/consolidation workflows before writing bespoke
  memory agents. Reactor still owns namespaces, ACLs, deletion/tombstones, review
  policy, and persistence schemas.
- Every migration slice must first ask whether a current Python ecosystem package
  already owns the generic agent capability. Direct implementation requires a short
  reason in the plan or code review notes.

LangGraph Platform/Agent Server is not the primary production API. It is useful for
local development, Studio workflows, and graph inspection. The application owns its
product API through FastAPI so auth, tenancy, approvals, audit, and cost controls
remain under deterministic application code.

LangGraph requirements:

- Production graph execution is async: use `ainvoke`, `astream`, or `astream_events`.
  Reactor's persisted raw event bridge uses LangChain/LangGraph
  `astream_events(..., version="v2")` `StreamEvent` payloads. A v2 interrupt is
  accepted only from a root `on_chain_stream` event with `parent_ids=[]`; missing,
  malformed, or nested lineage fails closed before public approval projection or
  approval-row persistence with `stop_reason=interrupt_stream_lineage_invalid`.
  A root `__interrupt__` payload must be a non-empty sequence; mappings, strings,
  and empty sequences fail before model-token projection with
  `stop_reason=interrupt_stream_payload_invalid`.
  Reactor's current approval lifecycle requires exactly one normalized action per
  interrupt frame. Missing, malformed, or multiple actions fail before checkpoint
  lookup or approval persistence with
  `stop_reason=interrupt_stream_action_invalid`. The invoke path applies the same
  cardinality and schema rule before reading checkpoint evidence or returning an
  interrupt, records `stop_reason=interrupt_action_invalid`, and terminates the
  run as failed rather than creating an unresumable approval state.
  Streaming reads the latest checkpoint id for completed run provenance. Invoke
  and stream paths both require a latest checkpoint id before persisting approval
  for a verified interrupt; a missing checkpointer, missing checkpoint, or
  checkpoint read failure fails closed with
  `stop_reason=checkpoint_provenance_unavailable`. Failed, rejected, timeout, and
  cancelled runs do not perform this checkpoint read.
  Public approval events are derived only from verified
  `__interrupt__` payloads; ordinary state chunks containing
  `approval_status=pending` are ignored and cannot override a verified interrupt.
  Repeated root interrupt frames must normalize to the same approval actions;
  identical repeats are idempotent, while conflicting actions fail closed with
  `stop_reason=interrupt_stream_conflict` before approval persistence.
  For interrupt-capable streaming runs, release evidence must separately track
  LangGraph's `stream_events(..., version="v3")` / async
  `astream_events(..., version="v3")` projection contract:
  `stream.interrupted`, `stream.interrupts`, `stream.output`,
  `Command(resume=...)`, the same `thread_id`, and a persistent checkpointer.
- Production checkpointing uses `AsyncPostgresSaver` from
  `langgraph-checkpoint-postgres`.
- Checkpointer setup is owned by Alembic-compatible bootstrap code. Either vendor the
  checkpointer DDL into Alembic or run the saver setup during a migration job; never
  mutate checkpoint tables lazily from request handling.
- If the runtime is production or `database_required=true`, missing or blank
  `database_url` is a startup failure before engine creation. Reactor must not
  silently compile a local in-memory graph or checkpointer for a durable deployment.
- Durable container startup is transactional after engine creation. Any exception
  or cancellation while creating the session factory, entering
  `AsyncPostgresSaver`/`AsyncPostgresStore`, or compiling the graph closes the
  entered async contexts and disposes the SQLAlchemy engine before propagating the
  original startup failure.
- Every resumable or streaming run maps the Reactor tenant, logical `thread_id`, and
  product `checkpoint_ns` tuple to an opaque tenant-scoped LangGraph
  `config["configurable"]["thread_id"]`; these values are not graph state fields.
  LangGraph owns `config["configurable"]["checkpoint_ns"]` as a subgraph path, so
  root invocations always use `""`. Durable direct-graph and LangChain
  `create_agent` invocations also set a positive `recursion_limit` so graph loops
  have an explicit code-owned exit budget. Native invoke, HITL resume, and stream
  completion persist the latest framework-issued `checkpoint_id` on the run.
  Approval resume pins that ID only when it came from the persisted run record;
  caller-supplied metadata must never select a resume checkpoint. An interrupted
  persisted run without checkpoint identity fails closed before approval claim or
  graph execution. Invoke and stream interrupt paths verify checkpoint identity
  before creating an approval row or publishing an approval event; an unavailable
  checkpoint produces an unresumable failed result instead of an orphan approval.
  These execution modes also set distinct framework `run_name` values plus a shared
  `runtime:langgraph` tag and secret-free `reactor.runtime=langgraph` metadata so
  LangSmith/OpenTelemetry traces preserve execution-mode identity. External
  cancellation propagates through native and LangChain invoke paths, and invoke
  or stream timeout handling must cancel the underlying coroutine or async
  generator before returning a timeout result. External cancellation during stream
  runtime execution first persists terminal `cancelled` run state and then
  re-raises `CancelledError`; the same rule applies if cancellation interrupts
  approval-row persistence after a streamed interrupt or final response filtering.
  Cancellation persistence is a tenant-scoped atomic `running -> cancelled`
  transition; an existing terminal result must never be overwritten. If
  cancellation races final completion persistence, the run becomes `cancelled`
  before commit or keeps the committed terminal result after commit. A rejected
  late completion transition must not publish a phantom stream completion event
  or record usage for the uncommitted result. Non-streaming invocation returns a
  sanitized `cancelled` result instead of the uncommitted model result. Native
  LangGraph and LangChain-agent resume paths apply the same rule and suppress
  `run.resumed` durable/public lifecycle events when completion loses the race.
  Preflight and early-rejection paths also project durable cancellation instead
  of returning or streaming an uncommitted rejected/failed result, including
  research profiles whose framework-required RAG tool is removed by tool policy.
  Cancellation
  during final model-visible token event or post-interrupt approval event
  persistence also records terminal `cancelled` state before re-raising. Explicit
  client stream closure after the started event also records terminal `cancelled`
  state before the async generator closes. The same rule applies when the client
  closes immediately after receiving the final model-visible token but before
  completion persistence, or after receiving a durable post-interrupt approval
  event. The successful `running -> cancelled` transaction also changes all
  tenant/run-scoped pending approvals to `cancelled`, preventing later approval
  of a cancelled run. The same transaction cancels only unexecuted `started`
  tool-invocation claims carrying the `approval_required` marker. Other `started`
  claims retain their ambiguous-outcome reconciliation path. Explicit cancel APIs
  use the same conditional transaction for `running` or `interrupted` runs and
  return conflict when the run is no longer active.
- If a native resume runtime is unavailable before the atomic resume claim, return
  a resume-operation failure and preserve the durable `interrupted` run unchanged;
  do not fabricate a terminal run result or consume the approval claim.
- Checkpoint fork/replay may select `checkpoint_id` only through a typed internal
  capability created after the fork API authorizes access to the source run.
  Request metadata never grants replay authority; provenance-shaped user fields are
  stripped and trusted provenance is regenerated from that capability. Same-scope
  replay may pin the checkpoint directly. Cross-scope fork reads it through the configured
  LangGraph saver and materializes the source checkpoint into an empty
  tenant-scoped target root before invocation. The saver read must return the
  requested physical source scope and checkpoint ID, and the checkpoint payload's
  own `id` must match that pinned ID. Mismatches, missing sources, pending writes,
  unavailable savers, non-empty targets, and saver write results whose physical
  scope differs from the requested target fail closed. When the fork body omits
  `checkpointId`, the fork API may derive trusted provenance from the source run's
  persisted `last_checkpoint_id`. User-supplied checkpoint metadata keys outside
  that contract are ignored. Fork APIs strip generic checkpoint metadata keys
  (`checkpointId` and `checkpoint_id`) before creating the child run. Explicit fork
  `checkpointId` values are trimmed before becoming trusted provenance or
  LangGraph `checkpoint_id` config.
- Checkpoint-bearing forks preserve the source runtime and graph profile. A target
  runtime/profile mismatch fails before any saver read or write; switching execution
  contracts requires a fresh unpinned run.
- Applied checkpoint replay metadata records both `checkpointId` for the actual
  LangGraph pin and `requestedCheckpointId` for the normalized trusted request so
  applied and ignored replay decisions have comparable audit evidence.
- Chat metadata is user-controlled and must strip checkpoint provenance keys:
  `source`, `checkpointId`, `checkpoint_id`, `forkedFrom*`, and `forkTarget*`.
  Chat metadata must never replay-pin or mislabel a run as a trusted fork.
- Fork APIs scrub stale fork provenance from source and request metadata before
  writing the new trusted provenance. A stale `forkedFromCheckpointId` from an
  earlier fork must never replay-pin a later fork, and stale target metadata must
  never mislabel the new `forkTargetThreadId` or `forkTargetCheckpointNs`.
- Message state uses `MessagesState` or `Annotated[list[AnyMessage], add_messages]`
  so node updates append/merge messages instead of replacing the list.
- Human approval uses LangGraph interrupts and resume commands, with approval records
  also stored in application-owned tables.
- Tool results are `ToolMessage(tool_call_id=...)` values, including tool errors.
- Graph state schemas are versioned. Breaking state changes require migration or an
  explicit checkpoint invalidation plan.
- `langgraph.json` is required for local `langgraph dev` and Studio workflows, but it
  is not the production serving contract.

## Python Composition Model

The Python app needs explicit wiring, but it should not recreate the old framework's
extension system. Reactor can expose product extension surfaces for users and teams,
but those surfaces must route through the central policy layer. Start with
framework-native composition and add registries only where they solve a real product
problem.

Default composition:

- Use Pydantic settings for configuration.
- Use FastAPI lifespan startup to create shared clients, database pools, compiled
  graphs, stores, and protocol servers.
- Use plain typed factories for graph profiles, tools, retrievers, memory stores,
  guards, and hooks.
- Use FastAPI dependencies at the HTTP boundary only.
- Keep graph nodes as small async functions that call services/tools, not global
  service locators.

Create a registry only when at least one condition is true:

- multiple implementations must be selected by tenant, graph profile, or runtime
  setting
- admins need runtime enable/disable, ordering, or policy inspection
- third-party plugins are intentionally supported
- tests need to verify a stable contract independent of a concrete implementation

Candidate registries:

- provider/model routing registry
- graph profile registry
- tool and MCP catalog registry
- guard/hook ordered registry
- retriever profile registry
- memory policy registry
- scheduler/job registry

Rules:

- Ordering is explicit for guards, hooks, retrieval stages, and policy checks.
- Optional subsystems fail disabled if their required settings are missing.
- No dynamic import path from user input is allowed.
- A plugin boundary is added only with a smoke test and a concrete use case.
- Avoid large dependency-injection frameworks until measured complexity justifies one.

## Storage

| Area | Decision | Version |
| --- | --- | --- |
| Primary database | PostgreSQL with pgvector image | pgvector/pgvector:0.8.3-pg18-trixie |
| PostgreSQL engine | PostgreSQL | 18.4 |
| Vector extension | pgvector | 0.8.3 |
| Python vector helper | pgvector | 0.3.6, transitive through langchain-postgres |
| ORM | SQLAlchemy | 2.0.51 |
| Migrations | Alembic | 1.18.5 |
| PostgreSQL driver | psycopg | 3.3.4 |
| Object storage client | boto3 | 1.43.36 |

PostgreSQL is the source of truth for:

- tenants, users, auth metadata
- run records and run state
- LangGraph checkpoints
- run events and streaming replay
- approvals
- audit logs
- usage ledger and cost records
- prompt/tool/model registry
- long-term memory metadata
- document chunks and embeddings through pgvector
- eval datasets and eval results
- durable job, lease, outbox, inbox, and idempotency records
- artifact metadata, checksums, retention, and access policy

Candidate application schema areas:

Create only the tables required by selected product workflows, retained migration
data, and framework gaps. Do not create every area below by default.

- `tenants`, `users`, `api_keys`, `user_identities`
- `sessions`, `conversation_messages`, `conversation_summaries`
- `agent_runs`, `agent_run_events`, `agent_run_steps`, `agent_run_errors`
- `run_queue`, `run_leases`, `job_attempts`, `dead_letter_jobs`
- `outbox_events`, `inbox_events`, `idempotency_records`
- `langgraph_threads` plus LangGraph checkpoint tables managed by the saver
- `pending_approvals`, `tool_policies`, `tool_invocations`
- `mcp_servers`, `mcp_server_status`, `mcp_tool_snapshots`, `mcp_access_policies`
- `a2a_peer_agents`, `a2a_agent_cards`, `a2a_tasks`, `a2a_task_events`
- `a2a_push_subscriptions`, `a2a_access_policies`
- `rag_sources`, `rag_documents`, `rag_chunks`, `rag_embeddings`, `rag_ingestion_jobs`
- `user_memories`, `task_memories`, `memory_facts`, `memory_proposals`
- `memory_namespaces`, `memory_items`, `memory_embeddings`, `memory_consolidation_jobs`
- `artifact_blobs`, `artifact_references`, `artifact_exports`
- `prompt_templates`, `prompt_versions`, `prompt_releases`, `personas`
- `model_registry`, `model_routes`, `embedding_models`, `graph_profiles`
- `context_manifests`, `runtime_settings`
- `scheduled_jobs`, `scheduled_job_executions`, `scheduled_job_dead_letters`
- `feedback`, `eval_datasets`, `eval_cases`, `eval_judges`, `eval_runs`, `eval_results`
- `admin_audits`, `token_revocations`, `usage_ledger`, `model_pricing`

Use `psycopg` as the default driver because LangGraph's Postgres checkpoint path is
aligned with psycopg. Do not add `asyncpg` unless a benchmark shows a real bottleneck.

Use pgvector for v1 retrieval and memory. Do not add Qdrant, Weaviate, Milvus, or
Chroma to the initial architecture. Add a dedicated vector database only if pgvector
fails on measured recall, latency, or operational isolation requirements.

## Durable Execution And Background Work

LangGraph checkpoints are required, but they are not the whole durable execution
system. Checkpoints persist graph state at graph boundaries. The application also needs a
durable queue, leases, retries, side-effect records, and replayable events for work
that outlives an HTTP request or touches external systems.

| Area | Decision | Version |
| --- | --- | --- |
| Durable run queue | application-owned Postgres queue | no external default |
| Optional Postgres queue helper | pgqueuer with psycopg extra | 1.0.2, evaluate only |
| Durable workflow candidate | DBOS | 2.25.0, graduation path only |
| Durable workflow candidate | Temporal Python SDK | 1.29.0, graduation path only |
| Redis job queues | arq/RQ/Celery | not default for durable agent work |

Default design:

- API writes `agent_runs`, `run_queue`, initial `agent_run_events`, and the first
  LangGraph thread metadata in one Postgres transaction.
- Workers claim queued work with `FOR UPDATE SKIP LOCKED`, a lease expiration, and a
  monotonic fencing token.
- Workers heartbeat the lease while executing and persist every status transition.
- On process crash, expired leases return to `queued` or `retryable_failed` according
  to the attempt policy.
- Backoff is exponential with jitter and a maximum-attempt cap.
- Non-retryable errors go to `dead_letter_jobs` with structured reason, trace id, and
  the last checkpoint id.
- Redis may wake workers or fan out cancellation/resume signals, but Postgres remains
  the replayable work log.

Outbox and inbox contract:

- All external side effects are represented as `outbox_events` before dispatch.
- Incoming webhooks/events are represented as `inbox_events` before processing.
- Handlers are at-least-once and idempotent; exactly-once delivery is not assumed.
- Each side-effecting tool call has an idempotency key, risk level, approval id if
  applicable, request checksum, and result checksum.
- If a destructive or external-side-effect tool times out after the request left the
  process, the run moves to `requires_reconciliation`; the graph must not blindly
  retry unless the upstream API provides idempotency guarantees.
- Vector-store sync, webhook delivery, Slack/event ingestion, artifact export, email,
  and scheduled jobs use outbox/inbox tables.

LangGraph execution rules:

- Use graph-wide `RetryPolicy`, `TimeoutPolicy`, and error handlers for safe nodes.
- Interrupts are not normal errors; approval/resume paths persist both the LangGraph
  interrupt state and the Reactor approval row.
- Side effects before `interrupt()` must be idempotent because interrupted nodes can
  resume through persisted state.
- A graph node may call external systems only through a Reactor tool or repository
  that writes invocation/audit/idempotency records first. Native LangGraph and
  LangChain tool execution share the same durable pre-execution claim primitive:
  claim failure or an unresolved started row fails closed before the handler,
  while an existing succeeded row reuses its stored result. Approval resume
  atomically binds the previously unbound `approval_required` started row to the
  durable approval id only when tenant, idempotency key, and request checksum
  match, and preserves the original invocation identity.
- Long-running background runs resume from `thread_id` and `checkpoint_ns`, never
  from in-memory worker state.

Use DBOS or Temporal only if the Postgres queue/outbox design cannot satisfy measured
requirements such as multi-day workflows, complex compensation, high fanout, or
cross-service orchestration. If one is adopted, remove the equivalent custom queue,
lease, retry, and scheduler code from the plan instead of running both systems.

## Data Migration And Cutover

The Python service owns a new Alembic migration history. The prior schema is an
inventory source only. Build a migration bridge only for data that must survive into
the new product; otherwise start from a clean schema and drop obsolete concepts.

Use this decision rule before writing migration code:

- Keep data that is needed for active users, audit/legal retention, billing, approved
  memories, prompts, evals, tool policy, or production operations.
- Re-map data whose old shape is useful but whose old schema does not fit the
  LangGraph/LangChain architecture.
- Drop data tied only to retired implementation details, deprecated endpoints,
  transient caches, old build/runtime settings, or superseded framework behavior.

Migration phases when retained data exists:

1. Inventory every existing table, endpoint, setting, and feature flag.
2. Mark each item `keep`, `remap`, `drop`, or `defer`.
3. Define new Python-owned tables and versioned Pydantic DTOs.
4. Write idempotent export readers into newline-delimited JSON for `keep`/`remap`.
5. Write idempotent import jobs into the new Alembic schema.
6. Backfill in staging and compare counts, checksums, and sample records for retained
   data only.
7. Freeze writes, run final export/import, validate, then switch traffic.
8. Keep rollback snapshots and old-read tooling until production burn-in completes.

Migration gates:

- 100% row-count parity for retained critical datasets.
- Checksum parity for immutable audit and ledger records.
- Random sample parity for retained sessions, messages, approvals, jobs, MCP servers,
  memories, and RAG chunks.
- Cutover readiness must use a reviewed retained-table manifest, not a hand-built
  partial CLI table list, for full backup DB dress rehearsal evidence.
- Cutover readiness records `migrationPersistence` evidence: SQLAlchemy ORM,
  Alembic migration ownership, psycopg driver, retained-table manifest
  requirement, checksum parity, rollback snapshots, idempotent import ledger, and
  immutable migration history. Release evidence cannot close full-backup DB dress
  gates without this facet.
- No destructive migration without a restore rehearsal.
- Alembic migrations are immutable after merge; corrections require a new migration.
- No endpoint or table is recreated only for historical symmetry.

## RAG Architecture Decision

LangGraph is not RAG. LangGraph is the graph/state-machine runtime that can
orchestrate RAG steps. RAG itself is the retrieval pipeline:

```text
ingest source -> split documents -> embed chunks -> store vectors and metadata
user query -> retrieve relevant chunks -> build grounded prompt -> generate answer
```

LangChain provides the retrieval building blocks: document loaders, text splitters,
embedding models, vector stores, and retrievers. LangGraph decides when and how those
retrievers run inside the agent loop.

Reactor will support two RAG modes:

- 2-step RAG: always retrieve before generation. Use for docs, FAQs, support answers,
  and low-latency product flows.
- Agentic RAG: expose retrieval as a tool and let the graph decide whether to search.
  Use for research flows, multi-tool reasoning, and cases where retrieval may need to
  happen multiple times.

Default v1 implementation:

- Store source documents, chunks, embeddings, and metadata in Postgres.
- Split managed documents through `reactor.rag.text_splitters`, backed by LangChain
  text splitter packages; do not hand-roll generic chunking loops in feature code.
- Use pgvector for semantic similarity search.
- Apply tenant and ACL filters inside SQL before vector/full-text ranking and before
  final `LIMIT`; never retrieve cross-tenant candidates and filter after ranking.
- Treat missing or malformed ACL state as private and unreadable. A company document
  is searchable only when its stored ACL explicitly permits the authenticated user,
  authenticated group, tenant visibility, or public visibility.
- Derive user/group ACL inputs only from authenticated execution context. For chat
  entrypoints the flow is `AuthPrincipal.groups -> RunService trusted_user_groups ->
  ReactorState.trusted_user_groups -> ToolExecutionRequest.trusted_user_groups ->
  Postgres retriever ACL predicate`; model-visible payloads cannot set these groups.
- Treat ACL data as authorization state, not answer context. RAG tool outputs must
  redact raw `acl`, `acl_hash`, `acl_visibility`, `acl_users`, `acl_groups`, and
  internal `acl_user_*`/`acl_group_*` marker metadata from model-visible chunk
  payloads, including nested metadata and case/whitespace variants of those keys;
  stored audit records and context manifests may carry only bounded proof fields
  such as `acl_hash`. Native LangGraph ToolMessages, LangChain ToolNode results,
  and response-filter tool insights must use the same recursive model-visible
  projection and retain citation/source labels without ACL proof. LangChain tools
  use `response_format="content_and_artifact"`: content is labeled and sanitized,
  while the artifact contains only sanitized metadata/text and remains valid when
  oversized output is truncated; raw results belong only in the audited invocation
  record. Both `ainvoke` results and `astream_events` `on_tool_end` events aggregate
  known sanitizer findings into run metadata and a checksum-only `tool_outputs`
  context-manifest section; neither manifest nor public run metadata carries the
  sanitized output text. The actual `ToolMessage.content` is the authoritative
  model-visible value. If artifact `model_visible_text` differs, invoke and stream
  both fail closed with count-only evidence and discard any success response.
  Unlabeled `ToolMessage` content is never ignored as out of scope: it is rejected
  with the same invoke/stream parity and no raw content in metadata. Streaming
  `on_tool_end` also normalizes LangChain message-state mappings such as
  `{"messages": [...]}` before applying the same guard; framework-native wrapping
  cannot bypass tool-output policy. LangGraph `Command(update={"messages": [...]})`
  tool returns use that same narrow normalization path; resume, goto, and graph
  control fields do not become tool-output data.
  Successful `Rag:hybrid_search` artifacts retain only
  length-bounded citation id, source URI, document id, chunk index, content hash,
  and ACL hash evidence. Invoke and stream paths merge that evidence into the RAG
  manifest before structured-output schema validation so valid runtime citations
  are accepted and unknown or malformed citations still fail closed. Invalid or
  oversized runtime citation ids are omitted from evidence, recorded only as a
  numeric invalid count, and rejected consistently by invoke and stream boundaries;
  the public run projection may expose the count but never the rejected id value.
  Citation evidence cardinality uses the same 20-item maximum as RAG retrieval.
  Overflow ids are omitted from the artifact and manifest, represented only by an
  omitted count, and cause structured output to fail closed in invoke and stream.
  Citation promotion additionally requires the versioned Reactor tool-result artifact
  contract: succeeded status, exact RAG tool id, non-empty idempotency key, labeled
  sanitized model output, and known sanitizer findings. Failed or foreign-schema
  artifacts contribute only an invalid-artifact count and fail closed without copying
  their claimed citation values into the context manifest or public run metadata.
  The same schema is present in sanitized tool content so HITL checkpoints remain
  verifiable when LangChain middleware removes the optional `ToolMessage.artifact`.
  On interrupt, Reactor reads the latest messages through `BaseCheckpointSaver.aget_tuple`,
  reconstructs only bounded evidence from the versioned sanitized envelope, and
  records tool output as checksum-only manifest data. The read uses the invocation
  config unless trusted replay/fork provenance pinned a source checkpoint; in that
  case it removes only `checkpoint_id` from a copied read config to resolve the
  newly written latest child checkpoint.
  Invoke/resume message state is a complete snapshot and replaces the prior runtime
  contribution; `astream_events` tool events are deltas and accumulate. This preserves
  initial assembled RAG counts while preventing repeated HITL resume inflation.
  When invocation is pinned to trusted replay/fork provenance, keep `checkpoint_id`
  on the graph invocation. After an interrupt writes a child checkpoint, remove the
  pin only from a copied evidence-read config before `aget_tuple`; otherwise the
  source checkpoint would be reread and current interrupt evidence lost. Preserve
  the original trusted config byte-for-byte for audit and subsequent runtime use.
  This evidence read is supplemental after LangGraph has already produced the
  interrupt: ordinary read failures must preserve the approval pause, fall back to
  `GraphOutput` messages, and emit only fixed status/operation/fallback metadata
  without exception details. `CancelledError` must propagate. Repeated HITL cycles
  must resume the same durable thread, execute each approved action exactly once,
  expose only the newest pending action on the next interrupt, and complete only
  after the last pending action is approved.
- Context manifest metadata is review/eval evidence, not an authorization surface.
  It must drop raw `acl`, `acl_proof`, `acl_visibility`, `acl_users`, `acl_groups`,
  and internal `acl_user_*`/`acl_group_*` marker keys while retaining safe proof
  handles such as `acl_hash`, citation id, source URI, document id, chunk index,
  and content hash.
- Use Postgres metadata filters for collection, document type, source, freshness, and
  version.
- Enable Postgres row-level security for RAG source/document/chunk tables through
  Alembic policies that enforce tenant isolation plus the same authenticated
  user/group ACL semantics used by the application retriever.
- Use Postgres full-text search for keyword fallback and hybrid retrieval.
- Use `langchain-postgres` as the default LangChain Postgres vector-store package.
  Wrap it behind a Reactor retriever boundary so tenant/ACL filters, diagnostics,
  citations, and fallback behavior stay under Reactor control.
- Online agentic RAG is exposed through `Rag:hybrid_search`, which enters the agent
  runtime as a LangChain `StructuredTool`. Query embeddings are created through
  LangChain `init_embeddings`; retrieval still runs through the application-owned
  Postgres retriever so ACL filtering happens before vector/full-text ranking.
- Do not directly pin standalone `pgvector==0.4.2` in the default dependency group.
  `langchain-postgres 0.0.17` currently requires `pgvector<0.4` and resolves to
  `pgvector 0.3.6`. This is a Python helper package constraint, not a PostgreSQL
  engine or pgvector extension constraint.
- If Reactor needs Python `pgvector 0.4.x` helper features before
  `langchain-postgres` widens its dependency range, implement the affected query path
  in an application-owned SQL retriever and keep the LangChain retriever interface at
  the boundary.
- Keep ingestion separate from online answer generation. Indexing is a background
  pipeline, not part of the hot request path. Release readiness preserves a
  `ragIngestionLifecycle` facet from the hardening suite. A passed gate must show
  `langchain-postgres`/PGVector use, embedding boundary ownership, source/MIME/size
  policy, checksum idempotency, background retries, quarantine or human review
  before indexing captured candidates, ACL metadata, ACL-before-ranking, raw ACL
  redaction, retriever-result reauthorization and result-limit enforcement before
  model output, reindex audit, diagnostics fields, and the source-controlled RAG
  poisoning eval case ids.

Postgres/pgvector is the right default because Reactor already needs relational
state, tenancy, audit, approvals, checkpoints, and metadata filtering. Keeping vectors
beside operational data gives one backup/restore path, one transaction model, SQL
joins, and simpler local development.

Graduate from Postgres/pgvector to a dedicated vector database only when benchmarks
show one of these failures:

- p95 retrieval latency misses the product SLO after proper indexes and query tuning
- vector index build/maintenance interferes with core transactional workloads
- recall quality is materially worse than a dedicated vector store on the eval set
- hybrid search, reranking, multi-vector, or payload-filter performance becomes the
  bottleneck
- data volume or tenant isolation requires independent vector-store scaling

If that happens, Qdrant is the first external vector-store candidate because it has
strong Python support and is commonly paired with LangGraph agentic RAG workflows.
Do not add it before the eval/latency evidence exists.

External vector DB graduation contract:

- Postgres remains canonical for documents, chunks, ACLs, metadata, source checksums,
  ingestion jobs, and audit records.
- External vector stores receive vectors through an outbox/backfill pipeline.
- External vector indexes must be rebuildable from Postgres.
- Query results from an external vector store must be re-checked against Postgres
  tenant and ACL policy before prompt injection.
- Cutover requires recall, latency, cost, and operational rollback evidence.

Retrieval features:

Initial required:

- hybrid retrieval: vector similarity + Postgres full-text search with RRF
- citation builder: source/chunk provenance survives response filtering
- retrieval diagnostics: expose query, transformed queries, filters, selected chunks,
  scores, rerank scores, and token budget usage to admins
- ingestion policy: source allowlist, file size limits, MIME allowlist, checksum-based
  idempotency, background retries, and poisoning tests

Eval-gated extensions:

- query transformer: HyDE or decomposition
- adaptive routing: simple vs complex query profile
- parent retrieval: chunk hit can expand to parent/neighbor context
- contextual compression: optional LLM/reranker compression before prompt injection
- reranking hook: interface-first, provider optional

## Memory Architecture

Memory is separate from RAG. RAG grounds answers in documents. Memory preserves user,
task, and conversation state across runs.

Do not delegate memory policy entirely to LangChain, LangGraph, or a hosted memory
service. The application owns tenancy, lifecycle, deletion, evals, promotion, and
conflict policy. Frameworks should own store interfaces and extraction helpers when
they fit those requirements.

Memory stack decision:

| Layer | Default | Role |
| --- | --- | --- |
| Working memory | LangGraph state | Current run state and scratch context |
| Short-term memory | `AsyncPostgresSaver` + conversation tables | Per-thread resumability and session history |
| Long-term store API | LangGraph `BaseStore` contract | Cross-thread memory access from graph nodes |
| Long-term storage | LangGraph store or application-owned Postgres tables + pgvector | Canonical facts, namespaces, ACLs, embeddings |
| Memory extraction/consolidation | LangMem | Propose, update, dedupe, and consolidate memories |
| External memory frameworks | Mem0/Zep/Graphiti/Letta/Cognee | Graduation candidates only |

Prefer LangGraph's built-in store implementation if its schema, tenancy model,
deletion behavior, and ACL hooks satisfy the product requirements. Implement a custom
`ReactorMemoryStore` only when the built-in store cannot support audit, deletion,
promotion, conflict handling, or tenant isolation. Any custom store must satisfy the
LangGraph `BaseStore` async contract (`aput`, `aget`, `adelete`, `asearch`,
`alist_namespaces`).

Required layers:

- working memory: current graph state and prompt context
- thread memory: LangGraph checkpoint state scoped by `thread_id`
- session memory: conversation messages and summaries scoped to a product session
- semantic memory: durable user/task facts, preferences, constraints, and profile data
- episodic memory: prior task traces, successful/failed examples, tool-use outcomes
- procedural memory: prompt or workflow improvement proposals
- retrieval memory: memories retrievable by semantic, keyword, and metadata filters

Memory write policy:

- Hot path may write explicit user-requested memories and lightweight proposals only.
- Background jobs use LangMem to extract, merge, dedupe, and score memories from
  conversation windows, feedback, tool outcomes, and completed tasks.
- LLM-generated memories start as `memory_proposals`; promotion requires policy checks
  and, for sensitive/procedural memory, eval or human approval.
- Memory promotion is the application-owned consolidation boundary. A reviewer can
  approve a LangMem proposal as a new active item, or approve it as replacing a
  prior active item in the same namespace; replaced items become `superseded` and
  are excluded from active model context.
- Procedural memory never auto-edits production prompts. It creates prompt-change
  proposals that go through prompt registry eval gates.
- Memory writes include source ids, source ranges, extraction prompt version, model,
  confidence, validity window, and redaction decisions.

Rules:

- Memory writes never block the final response; failed writes are queued for retry.
- Facts that can change carry `valid_from`, optional `valid_until`, confidence,
  source, and extraction run id.
- Conflicting facts are not overwritten silently; retrieve the current fact by
  validity window and retain historical records.
- Conversation summaries are a view over original messages, not a destructive
  replacement.
- User memory deletion deletes or tombstones embeddings and source facts.
- Memory retrieval always applies tenant/user/task filters before vector search.
- Memory namespaces include tenant id, subject type, subject id, memory type, and
  visibility scope. Never use a raw user-controlled namespace tuple.
- Search returns source/provenance with each memory so the context assembler can label
  memory content as data.
- Store only useful memories. Reject trivial, duplicate, unsupported, or sensitive
  facts that fail policy.
- Retention, export, deletion, and tombstone behavior are API-visible product
  features, not storage implementation details.
- Memory metrics track proposal acceptance rate, retrieval hit rate, conflict rate,
  stale-memory rate, deletion lag, and token savings.

Initial memory types:

- Semantic: user preferences, stable project facts, tenant settings, task constraints.
- Episodic: solved task examples, failed tool plans, approval decisions, recovery
  traces. Use for few-shot retrieval and agent self-improvement evals.
- Procedural: candidate prompt/tool-routing/workflow improvements. Store as proposals,
  not active instructions.

External memory framework policy:

- LangMem is included because it is lightweight, compatible with LangGraph, and can use
  a LangGraph-compatible store boundary.
- Mem0 is not the default because `mem0ai 2.0.8` brings a separate memory layer and
  Qdrant-oriented defaults that overlap with Reactor's Postgres/pgvector plan.
- Zep/Graphiti is not the default because temporal graph memory adds Neo4j/graph
  infrastructure and should be adopted only when vector + metadata memory fails
  temporal/entity evals.
- Letta is not the default because it is a full stateful agent runtime; Reactor's
  primary runtime is LangGraph.
- Cognee is not the default because it is a heavier graph/knowledge pipeline; evaluate
  it for document/entity graph workloads only after RAG and memory evals show need.

Defer temporal knowledge graph infrastructure until memory evals show vector +
metadata retrieval is insufficient for relationship or time-travel queries.

## Context, Prompt, And Model Governance

Context management is a product contract, not a prompt convention. Every model call
must be reproducible from database records and artifact references.

Required governance metadata:

- prompt registry: prompt template, semantic version, owner, release status, rollback
  target, eval gate, and changelog
- model registry: provider, model id, context window, output limits, tool-calling
  support, structured-output support, streaming support, reasoning controls, region,
  data-retention policy, price, and default timeout
- embedding registry: provider, model id, vector dimension, tokenizer, distance
  metric, index version, and reindex plan
- graph profile registry: graph id, prompt release, model route, tool allowlist,
  memory policy, retrieval profile, budgets, and fallback policy

Every model call stores a `context_manifest` containing:

- graph profile and graph state schema version
- prompt template version and rendered prompt checksum
- selected model, provider, temperature, max output tokens, and structured-output mode
- messages included, summaries included, memory ids, retrieved chunk ids, artifact ids
- exposed tools and tool schema versions
- token budget by context band
- redaction decisions and sensitive-field policy
- trace id, run id, checkpoint id, and eval tags

Context assembly order:

1. system/developer policy and safety constraints
2. graph profile instructions
3. latest user request and active task objective
4. approval state and deterministic policy decisions
5. relevant session summary and pinned user/task memories
6. retrieved RAG context with source labels; bounded ACL proof stays in the context manifest
7. recent conversation messages trimmed on valid message-pair boundaries
8. tool outputs needed for the next decision
9. optional examples or rubrics for the specific graph profile

Rules:

- Retrieved documents, tool output, MCP resources, web pages, uploads, and user files
  are untrusted data. They are labeled as data and cannot override system/developer
  instructions.
- Context trimming is deterministic and stores before/after token counts.
- Summaries include source message ranges and are never treated as authoritative over
  the original messages.
- Prompt changes require eval comparison before release. Release readiness preserves a
  `promptReleaseLifecycle` facet from the hardening suite. A passed gate must show
  prompt version content hashes, rendered prompt checksums, PromptLab/LangSmith
  baseline comparison, prompt-write permission, release audit, rollback target,
  release metadata fields, and no dynamic prompt deserialization.
- Model fallback must not cross tenant data-retention requirements or region policy.
- After a side-effecting tool succeeds, fallback may continue only from persisted
  state and recorded tool results; it must not reissue the tool call.
- Structured outputs use Pydantic/JSON-schema validation plus bounded repair retries.
  Validation failures are run metadata, not silent string parsing.

## Redis Decision

Final decision: use Redis in the production profile, but keep Reactor correct without
Redis in the single-node profile.

Redis is a common production companion for agent systems, but not the agent
runtime's durable brain. Enable it only for shared ephemeral coordination. Redis is
required when any of these are true:

- more than one API or worker replica is running
- rate limits must be shared across processes
- live SSE/WebSocket streaming can reconnect to a different node
- run cancellation/resume/approval events must fan out across workers
- distributed locks are needed for run ownership
- short-lived response, retrieval, or provider metadata cache is enabled
- background work needs low-latency cross-process wakeups

Redis is not the source of truth for:

- LangGraph durable checkpoints
- audit logs
- approval decisions
- usage ledger
- long-term memory
- user/session records

Redis may store only ephemeral or rebuildable data:

- rate-limit counters
- run ownership locks with TTL
- short cache entries with TTL
- pub/sub notifications
- SSE fanout hints
- idempotency keys with bounded TTL

Redis Pub/Sub is at-most-once and non-durable. All replayable run, approval, scheduler,
and streaming events come from Postgres.

Do not use Redis-backed queues for durable agent runs, ingestion, approval, or
side-effect dispatch. arq/RQ/Celery may be evaluated only for best-effort ephemeral
jobs whose loss is acceptable and documented.

Do not use `langgraph-checkpoint-redis` as the primary checkpoint store. Keep
`langgraph-checkpoint-postgres` as the default. Redis checkpointer can be evaluated
only for low-risk ephemeral graphs or benchmark-specific workloads.

Recommended Docker image:

- `redis:8.8.0-alpine`

Failure policy:

- Development/single-node: app starts without Redis.
- Production single replica: Redis can be optional if rate limiting and fanout are disabled.
- Production multi-replica: Redis is required; readiness must fail if unavailable.
- Redis outage must not lose completed runs, checkpoints, approvals, or audit records.
- Multi-replica rate-limit Redis failures fail closed or pull the node out of readiness.
- Redis locks require a Postgres fencing token or monotonic run-owner version so stale
  workers cannot commit after lock expiry.
- Release hardening and readiness preserve this contract as `redisCoordination`.

## Product/API Scope Contract

The new API can use `/v1`, and it does not need to mirror previous endpoints. Prior
APIs are inventory for product discovery, not compatibility obligations. Keep an old
endpoint shape only when an active client, migration window, or external contract
requires it; otherwise design the API around the Python/LangGraph product model.

Candidate user-facing domains:

- chat: non-streaming and streaming runs
- sessions: list, read, delete, ownership checks
- models: available model list, default model, provider metadata
- auth: login/exchange/API keys, token revocation, tenant scoping
- personas and prompt templates
- tools: listing, dry-run, policy, audit, approval
- MCP: server CRUD, status, preflight, access policy, catalog sync
- A2A: agent card, peer registry, task send/stream/resume/cancel, push notifications
- RAG/admin: source registration, ingestion job status, retrieval diagnostics
- memory: user memory, task memory, summaries, deletion
- scheduler: job CRUD, trigger, dry-run, execution history
- multi-agent: graph/agent profile CRUD and delegation policy
- feedback/eval: feedback capture, eval cases, eval runs, review workflow
- admin: runtime settings, capabilities, health/doctor summary, audits
- integrations: Slack/event ingestion if product scope keeps it

API rules:

- All request/response bodies are Pydantic models with explicit version fields.
- Streaming event names are versioned and documented.
- Every admin write emits an immutable audit event.
- Any old behavior kept for compatibility must be listed with owner, expiry, adapter
  path, and removal criteria.
- Any old behavior dropped because the new framework or product scope supersedes it
  should be recorded in the migration inventory, not reimplemented.
- Legacy metric ingestion routes are retained during migration because external
  collectors may still post MCP health, tool-call, and eval-result events. They map
  to `/api/admin/metrics/ingest/*` and `/v1/admin/metrics/ingest/*`, require admin
  settings-write permission, and must publish to the observability ingestion boundary
  instead of writing durable agent state to Redis.
- Legacy input guard stats routes are retained during migration for the admin console.
  `/api/admin/input-guard/stats` and `/v1/admin/input-guard/stats` require guard-read
  permission, clamp the requested period to 1..168 hours, and delegate aggregation to
  an observability-backed query boundary.
- Legacy intent definition routes are retained for classifier/profile governance.
  `/api/intents` and `/v1/intents` expose admin-only CRUD over durable
  `intent_definitions` records. The registry is product policy data, not LangGraph
  checkpoint state. Runtime intent resolution is fail-open: a classifier miss, low
  confidence result, missing profile, or classifier error keeps the default graph
  profile instead of blocking the request. A confident match may select a registered
  `GraphProfile`, which then controls prompt version, model route, tool allowlist,
  temperature, and tool budget through normal LangGraph state.
- Legacy tool-call history routes are retained during migration for admin diagnostics.
  `/api/admin/tool-calls` and `/v1/admin/tool-calls` expose tenant-scoped invocation
  history with run/period filters; `/ranking` exposes tenant-scoped tool usage
  summaries from the durable tool invocation store.
- Legacy platform user admin routes are retained during migration for operator
  workflows. `/api/admin/platform/users/by-email` exposes admin user lookup, and
  `/api/admin/platform/users/{id}/role` updates roles with audit logging and
  self-downgrade protection.
- Legacy RBAC user role update routes are retained for admin console compatibility.
  `/api/admin/rbac/users/{userId}/role` and `/v1/admin/rbac/users/{userId}/role`
  require `user:write`, update the durable user store, return the legacy
  `userId`/`role` body, and emit `rbac` `UPDATE_ROLE` audit events.
- Legacy agent spec routes are retained for multi-agent governance.
  `/api/admin/agent-specs` and `/v1/admin/agent-specs` expose admin CRUD over
  durable `agent_specs` records. List/get responses only expose
  `systemPromptPreview`; the full system prompt is available through
  `/{id}/system-prompt` and emits a read audit event.
- Legacy persona routes are retained for prompt/persona governance. `/api/personas`
  and `/v1/personas` expose admin-only list/create/update/delete over durable
  `personas` records; individual `GET /{id}` remains readable without admin headers
  for legacy selector flows. Stores must preserve at most one default persona, support
  `activeOnly`, and keep prompt-template linkage as nullable product metadata.
- Legacy client error-report ingestion is retained for admin/frontend diagnostics.
  `POST /api/error-report` accepts bounded optional client error fields and returns
  204; `GET /api/error-report` intentionally returns 405 for reachability probes.
- Legacy retention policy routes are retained for operator data governance workflows.
  `/api/admin/retention` reads default/session/conversation/audit/metric retention
  days from runtime settings, and `PUT /api/admin/retention` updates only provided
  keys with audit logging.
- Legacy debug replay routes are retained for operator diagnostics.
  `/api/admin/debug/replay` lists recent failed-request captures from an optional
  replay store; `/api/admin/debug/replay/{id}` returns the replay payload or a
  legacy-compatible 404 when unavailable.
- Legacy task memory maintenance routes are retained for operator cleanup workflows.
  `/api/admin/task-memory/maintenance/purge-expired` removes expired task memory
  through the optional maintenance service boundary; `/purge-terminal` removes
  terminal task memory older than the requested day window. Both require settings-write
  permission and record delete audit events.
- Legacy RAG ingestion policy routes are retained for runtime capture governance.
  `/api/rag-ingestion/policy` and `/v1/rag-ingestion/policy` expose admin-only
  get/update/delete over a singleton JSON policy stored in `runtime_settings`.
  Missing stored policy means the effective policy falls back to config defaults;
  updates normalize channels/patterns, validate blocked regexes, invalidate policy
  cache, and record admin audit events.
- Legacy RAG ingestion candidate routes are retained for human review of captured
  Q&A candidates. `/api/rag-ingestion/candidates` and
  `/v1/rag-ingestion/candidates` expose admin-only list/approve/reject over durable
  `rag_ingestion_candidates` records. Approval ingests Q/A content into the
  application-owned Postgres RAG sink with tenant ACL metadata; rejection only updates
  review state. Both review paths record admin audit events.

## API Surface

Initial v1 API candidate:

- `GET /healthz`
- `GET /readyz`
- `GET /metrics`
- `POST /api/error-report`
- `POST /v1/runs`
- `GET /v1/runs/{run_id}`
- `GET /v1/runs/{run_id}/events`
- `POST /v1/runs/{run_id}/resume`
- `POST /v1/runs/{run_id}/cancel`
- `GET /v1/tools`
- `POST /v1/tools/{tool_name}/dry-run`
- `GET /v1/approvals`
- `POST /v1/approvals/{approval_id}/approve`
- `POST /v1/approvals/{approval_id}/reject`
- `GET /v1/mcp/servers`
- `POST /v1/mcp/servers`
- `PATCH /v1/mcp/servers/{server_id}`
- `DELETE /v1/mcp/servers/{server_id}`
- `GET /.well-known/agent-card.json`
- `POST /a2a`
- `GET /v1/a2a/supported-interfaces`
- `GET /v1/a2a/agents`
- `POST /v1/a2a/agents`
- `GET /v1/a2a/access-policy`
- `PUT /v1/a2a/access-policy`
- `POST /v1/a2a/tasks`
- `GET /v1/a2a/tasks/{task_id}`
- `POST /v1/a2a/tasks/{task_id}/resume`
- `POST /v1/a2a/tasks/{task_id}/cancel`
- `GET /v1/a2a/tasks/{task_id}/events`
- `GET /v1/sessions`
- `GET /v1/sessions/{session_id}`
- `DELETE /v1/sessions/{session_id}`
- `GET /v1/models`
- `GET /v1/intents`
- `POST /v1/intents`
- `GET /v1/intents/{intent_name}`
- `PUT /v1/intents/{intent_name}`
- `DELETE /v1/intents/{intent_name}`
- `GET /v1/personas`
- `POST /v1/personas`
- `GET /v1/personas/{persona_id}`
- `PUT /v1/personas/{persona_id}`
- `DELETE /v1/personas/{persona_id}`
- `GET /v1/rag-ingestion/policy`
- `PUT /v1/rag-ingestion/policy`
- `DELETE /v1/rag-ingestion/policy`
- `GET /v1/rag-ingestion/candidates`
- `POST /v1/rag-ingestion/candidates/{candidate_id}/approve`
- `POST /v1/rag-ingestion/candidates/{candidate_id}/reject`
- `GET /v1/rag/sources`
- `POST /v1/rag/sources`
- `POST /v1/rag/ingestion-jobs`
- `GET /v1/rag/ingestion-jobs/{job_id}`
- `POST /v1/retrieval/query`
- `GET /v1/memory/users/{user_id}`
- `PUT /v1/memory/users/{user_id}`
- `GET /v1/memory/search`
- `GET /v1/memory/facts/{memory_id}`
- `POST /v1/memory/proposals/{proposal_id}/approve`
- `POST /v1/memory/proposals/{proposal_id}/reject`
- `DELETE /v1/memory/facts/{memory_id}`
- `GET /v1/runtime/settings`
- `PUT /v1/runtime/settings/{key}`
- `GET /v1/scheduler/jobs`
- `POST /v1/scheduler/jobs`
- `POST /v1/scheduler/jobs/{job_id}/trigger`
- `POST /v1/feedback`
- `GET /v1/admin/capabilities`
- `GET /v1/admin/agent-specs`
- `POST /v1/admin/agent-specs`
- `GET /v1/admin/agent-specs/{id}`
- `PUT /v1/admin/agent-specs/{id}`
- `GET /v1/admin/agent-specs/{id}/system-prompt`
- `DELETE /v1/admin/agent-specs/{id}`
- `GET /v1/admin/audits`
- `GET /v1/admin/debug/replay`
- `GET /v1/admin/debug/replay/{id}`
- `GET /v1/admin/input-guard/stats`
- `PUT /v1/admin/rbac/users/{user_id}/role`
- `GET /v1/admin/platform/users/by-email`
- `POST /v1/admin/platform/users/{id}/role`
- `GET /v1/admin/retention`
- `PUT /v1/admin/retention`
- `POST /v1/admin/task-memory/maintenance/purge-expired`
- `POST /v1/admin/task-memory/maintenance/purge-terminal`
- `GET /v1/admin/tool-calls`
- `GET /v1/admin/tool-calls/ranking`
- `POST /v1/admin/metrics/ingest/mcp-health`
- `POST /v1/admin/metrics/ingest/tool-call`
- `POST /v1/admin/metrics/ingest/eval-result`
- `POST /v1/admin/metrics/ingest/batch`
- `POST /v1/admin/metrics/ingest/eval-results`

Implement this list incrementally. A route enters the required set only when its
product workflow, auth policy, persistence model, and contract test are defined.

Streaming uses SSE first. WebSocket can be added later if bidirectional UI latency
requires it. Every streamed event must also be written to Postgres so clients can
reconnect and replay.

## Request Pipeline And Graph Shape

The FastAPI request handler handles API validation and authorization, then delegates
to the graph runner. The graph runner owns agent semantics.

Baseline request pipeline:

```text
authn/authz
  -> concurrency gate
  -> input guard
  -> before-start hooks
  -> intent/profile resolution
  -> cache lookup
  -> conversation + memory load
  -> RAG retrieval or retrieval-tool exposure
  -> tool selection
  -> LangGraph run
  -> fallback policy
  -> output guard
  -> fail-open response filters + citations
  -> output boundary check
  -> conversation/memory save
  -> after-complete hooks
```

Output guards are security gates and fail-close on blocked content. Response filters
are post-processing quality transforms and fail-open: cancellation propagates, but a
filter error logs and preserves the last valid response text. Built-in filters such
as max-length truncation run after output guard so they cannot weaken guard policy.
Output boundary enforcement is a deterministic final response policy: max length
violations truncate and record `output_too_long`; min length violations record
`output_too_short` and follow WARN, RETRY_ONCE, or FAIL policy.
Structured output validation strips Markdown code fences and verifies requested JSON
or YAML before final delivery. YAML must parse to a mapping or sequence, not a bare
scalar. Repair attempts are bounded to 8 KiB of invalid input and must return only
the requested structured format; failed repair marks `INVALID_RESPONSE`. Release
readiness validates `structuredOutput.repairBoundary` with the max invalid-input
size and `rawInvalidInputIncluded=false` so repair evidence does not expose model
content.

The production graph should start simple and explicit:

```text
input_guard
  -> before_start_hooks
  -> context_assembler
  -> model_step
  -> route_model_output
      -> final_output_guard -> after_complete_hooks -> complete
      -> approval_gate -> tool_executor -> tool_output_guard -> model_step
      -> error_handler
```

Baseline graph state fields:

- `tenant_id`
- `user_id`
- `run_id`
- `messages`: `MessagesState` or `Annotated[list[AnyMessage], add_messages]`
- `active_tools`
- `tool_call_count`
- `max_tool_calls`
- `approval_policy`
- `budget`
- `retrieved_context`
- `guard_decisions`
- `tools_used`
- `trace_id`
- `intent_profile`
- `selected_model`
- `selected_tools`
- `retrieval_mode`
- `retrieval_results`
- `approval_state`
- `cache_decision`
- `fallback_attempts`
- `citations`
- `response_filters`

LangGraph config fields:

- `thread_id`
- `checkpoint_ns`
- `checkpoint_id` when resuming from a specific checkpoint
- tenant/user/run identifiers duplicated only when required by checkpointer metadata

Default limits:

- request timeout: 45 seconds for synchronous API calls
- background run timeout: configurable, default 15 minutes
- tool timeout: 15 seconds
- max tool calls: 10
- max tools exposed per request: 60
- input max chars: 10,000
- max output tokens: 4,096
- default temperature: 1.0 unless a graph profile overrides it

Loop invariants:

- Assistant tool calls and tool responses are stored as ordered pairs.
- Tool result messages always include the original `tool_call_id`.
- Parallel tool execution preserves model-declared tool-call order in state.
- When `max_tool_calls` is reached, tools are removed and the graph asks for a final
  answer.
- Context trimming never drops the latest user message.
- Context trimming walks back to a valid message-pair boundary.
- Stop reasons such as max tokens, safety filtering, recitation, or provider refusal
  are mapped to structured run metadata.
- Fallback is explicit and records provider/model, reason, latency, and cost.

## Tool, MCP, And A2A Policy

Tools are model-facing APIs. Keep the set small and unambiguous.

Rules:

- Prefer 10-20 active tools per graph profile.
- Use namespaced tool names.
- MCP tools must use fully qualified names: `ServerName:tool_name`.
- A2A peers are external agents, not local tools; expose them through delegation
  services or graph profiles, not as unreviewed tool lists.
- Every tool has Pydantic input and output schemas.
- Every tool declares risk level: `read`, `write`, `external_side_effect`, `destructive`.
- Write/destructive tools require approval unless a tenant policy explicitly allows them.
- Tool errors return structured `"Error: ..."` payloads that enable model recovery.
- Tool output is sanitized before it re-enters model context.
- Tool execution has timeout, idempotency key, audit event, and cost/latency metrics.
- Terminal tool invocation records validate their terminal payloads: succeeded
  records carry output payloads and failed records carry recovery-friendly error
  payloads.

Do not implement many narrow wrappers if one workflow-level tool is clearer. If a
human cannot tell which tool should be used, the model will not reliably do better.

MCP runtime requirements:

- Use the official Python SDK `mcp==1.28.1` for server/client protocol handling.
- Use `langchain-mcp-adapters==0.3.0` only behind Reactor's tool boundary.
- Convert Reactor MCP registrations into official adapter connection dictionaries for
  `stdio` and `streamable_http`; load normal multi-server runtime tools with
  `MultiServerMCPClient.get_tools()` and use `load_mcp_tools(...)` for explicit
  session-managed adapters, then normalize model-visible names to
  `ServerName:tool_name`.
- Fail closed when an MCP registration requires auth but no credential-binding layer is
  present. Do not silently connect without required credentials.
  This is an executable preflight contract: `auth_type != "none"` is rejected until
  the caller proves scoped credential binding is available.
- Target MCP specification `2025-11-25`; unsupported negotiated protocol versions
  must be rejected or marked degraded before tool exposure.
- Support stdio and streamable HTTP transports.
- WebSocket transport support is optional through `mcp[ws]`; do not enable it by
  default unless a specific server requires it.
- Track the negotiated MCP protocol version; HTTP transports send the required
  `MCP-Protocol-Version` header after negotiation.
- MCP adapter readiness evidence records `adapterToolLoading`: connection
  dictionary transports, `MultiServerMCPClient.get_tools`, `load_mcp_tools`,
  structured-content artifact support, and configurable tool-error propagation.
- Server registration is runtime data, not static config.
- Each server has status, last connection error, reconnect policy, and tool snapshot.
- Connection attempts use exponential backoff with jitter.
- Preflight checks validate command/URL, transport, auth, timeout, and tool listing.
- OAuth-capable MCP servers use OAuth 2.1 security requirements, PKCE when applicable,
  resource indicators, token audience validation, and least-privilege scopes.
- Token passthrough is forbidden; Reactor stores scoped MCP credentials per server and
  never forwards unrelated provider/user tokens to MCP servers.
- Block private-address and link-local targets unless explicitly allowed by admin
  policy.
- Enforce max tool output length before tool output reaches the graph.
- Cache tool lists with version/hash and refresh on reconnect.
- Channel-specific write denial and write allowlists are policy data.
- Tool routing supports keyword, semantic, and explicit profile allowlists.
- Structured tool output is preferred when the server provides it; text output remains
  model-visible data and is sanitized.
- Slack MCP tools are model-facing workspace tools only. Keep Slack gateway ingress,
  assistant/thread UX, slash/interaction ACKs, response URL delivery, and current
  thread product replies in the native Slack gateway.

A2A runtime requirements:

- Use the official Python SDK `a2a-sdk[fastapi,telemetry]==1.1.0` and target A2A
  protocol version `1.0`. A2A negotiation uses `Major.Minor`; do not put patch
  versions in request headers, responses, or agent cards.
- Live A2A smoke evidence records `protocolNegotiation`: outbound probes send
  `A2A-Version: 1.0`, diagnostics response versions remain Major.Minor-only,
  agent-card interface versions are checked, task IDs are server-generated, and
  the serving surface is the SDK FastAPI plus telemetry integration.
- A2A is for agent-to-agent interoperability. It is not Reactor's internal graph
  runtime, tool protocol, memory layer, or queue.
- Internal multi-agent behavior remains LangGraph graph/profile/delegation policy.
- Publish an agent card at `/.well-known/agent-card.json`; it must be versioned,
  tenant-aware where applicable, and free of secrets, internal prompts, private tool
  names, and non-public infrastructure details.
- Mount the SDK protocol endpoint under `/a2a`; keep application-owned peer registry,
  task admin, audit, and diagnostics under `/v1/a2a/*`. Peer registry management
  is admin-gated; unauthenticated callers must not register or enumerate configured
  external agents.
- Manage tenant-wide and peer-specific A2A access policy through admin-gated
  `/v1/a2a/access-policy`; policy writes must use the same PostgreSQL store that
  runtime delegation enforcement reads.
- Outbound A2A delegation checks peer-specific access policy first, then the
  tenant-wide default policy before task creation, persistence, or push outbox enqueue.
  An explicit `allow_outbound=false` policy denies with `403`; non-empty
  `allowed_skills` lists deny requested `skillId` values outside the allowlist.
- Incoming A2A messages pass through the same authn/authz, rate limit, input guard,
  approval, tool policy, budget, and audit layers as first-party runs.
- A2A task, context, and message identifiers map to Reactor run, thread, session, and
  idempotency records; never rely only on SDK in-memory state.
- SDK protocol task-store saves persist app-owned `a2a_task_events` entries for task
  creation and status transitions so protocol-routed tasks remain auditable and
  replayable through the same timeline contract as REST-created tasks.
- Streaming task events are persisted to `agent_run_events` and `a2a_task_events`
  before delivery so reconnect and replay work across replicas.
- Push notifications use the outbox pattern with destination allowlists, signing or
  bearer-token validation, retries, and dead-letter handling.
- REST-created A2A tasks that request `pushDestination` persist that destination with
  the durable task input and enqueue lifecycle push events for creation, cancellation,
  and resume without losing peer, skill, user, or metadata context.
- Artifacts received from A2A peers are stored as artifact references with source,
  checksum, MIME, ACL, and retention metadata; do not store blob bodies in graph state.
- gRPC support is optional through `a2a-sdk[grpc]`; default production profile is
  HTTP/JSON plus SSE because it matches FastAPI and browser/admin tooling.
- Do not use `google-adk[a2a]` in the default stack until it supports the current
  A2A SDK 1.x line; its current extra pins an older incompatible A2A SDK range.

## Artifact And Sandbox Policy

Artifacts prevent long outputs and subagent work from being copied through the model
conversation. Graph state stores references; blobs live outside the graph state.

| Area | Decision | Version |
| --- | --- | --- |
| Production blob storage | S3-compatible API through boto3 | 1.43.36 |
| Local blob storage | filesystem-backed dev adapter | internal |
| PDF extraction | pypdf | 6.14.2, ingestion extra |
| MIME sniffing | python-magic | 0.4.27, ingestion extra |
| XML parsing safety | defusedxml | 0.7.1, ingestion extra |
| Broad document parsing | unstructured | 0.23.1, optional only |

Artifact rules:

- Store artifact metadata, ownership, ACL, MIME, size, checksum, encryption policy,
  retention, and source run id in Postgres.
- Store blob bytes in local dev storage or S3-compatible production storage.
- Never put large binary or document bodies in LangGraph state.
- Artifacts created by tools/subagents return lightweight references to the graph.
- Downloads use short-lived signed URLs or authenticated streaming endpoints.
- Document ingestion enforces MIME allowlist, size limits, checksum idempotency,
  parser allowlists, and parser sandboxing for risky formats.
- Artifact deletion follows tenant retention policy and removes or tombstones derived
  embeddings.
- Hardening and release readiness preserve an `artifactLifecycle` facet covering
  reference-only graph state, metadata, ACL, signed URL expiry, MIME spoofing,
  parser failure, and retention tombstone evidence.

Sandbox rules:

- Arbitrary shell, browser, Python, or code-execution tools are disabled in v1 unless
  a sandbox profile is explicitly enabled.
- A sandbox profile runs in a separate isolated worker/container, as non-root, with
  CPU, memory, process, wall-clock, disk, and output limits.
- Sandbox filesystem access is per-run and starts from an empty or manifest-defined
  workspace. No host home directory, provider credentials, or database credentials are
  mounted.
- Network egress is denied by default and can be opened only through an allowlist and
  approval policy.
- Secrets are injected by capability, not environment dump; the model never sees raw
  secret values.
- Sandbox outputs are exported as artifacts, scanned by policy, and referenced by id.
- Any MCP server that exposes shell, browser, or file-write capabilities inherits the
  same sandbox and approval policy.

## Security And Safety

Required defaults:

- `LANGGRAPH_STRICT_MSGPACK=true`, set before any LangGraph imports
- no API keys in default config files
- all secrets from environment or secret manager
- tenant isolation enforced at repository layer
- prompt injection tests for all retrieval/tool-output paths
- input guards before model calls
- output guards before user-visible response
- tool-output guards before model-visible ToolMessage or prompt context: label as
  `[tool_output:data]`, redact canary secrets, and record guard findings in
  response metadata, context manifest evidence, and release readiness
  `toolOutputGuard`
- `ToolRetryMiddleware` exhaustion uses a fixed `[tool_output:data]` failure
  envelope. Raw exception types, messages, and tool names must not cross into the
  model-visible `ToolMessage`. Automatic retry is allowlisted to enabled,
  approval-free `read` tools. Write, destructive, and external-side-effect handler
  exceptions or timeouts produce `requires_reconciliation` without automatic replay.
- input and output guard block exceptions expose structured, raw-content-free metadata such as
  stage, reason, run id, tenant id, and graph node; completed run metadata
  preserves this as `guardBlock` when a guard rejects a run, and release
  readiness preserves and validates the same facet
- public run API responses expose projected, allowlisted metadata only; approval
  request metadata keeps recovery/HITL identifiers, risk, timeout, and
  idempotency fields but omits raw tool input payloads
- API dress smoke records `apiBoundary` evidence from FastAPI `/openapi.json`:
  OpenAPI version, route/schema counts, required public paths, Pydantic validation,
  request/response model coverage, metadata allowlisting, and secret-free schema
  metadata. Release readiness fails closed when this facet is missing or malformed.
- cancellation must propagate: `asyncio.CancelledError` is re-raised
- all generic exception handlers emit structured errors and metrics
- No untrusted LangChain object deserialization.
- no dynamic loading of user-provided LangChain prompt/config objects
- no custom msgpack hooks unless explicitly allowlisted and tested
- no LangChain `load()`/prompt deserialization on untrusted payloads
- no `secrets_from_env=True` or equivalent secret access for untrusted configs
- release readiness must preserve `langchainSerializationBoundary` evidence for
  forbidden load/loads APIs, env-secret revival, user-config deserialization, and
  trusted JSON-only parsing
- `tests/unit/test_module_architecture.py` rejects forbidden LangChain load imports,
  forbidden literal dynamic imports, and non-literal dynamic imports so the
  serialization boundary has a static sensor in addition to release evidence
- No user-controlled checkpoint metadata keys or retrieval filter keys.
- No SQLite checkpointer in production.
- No in-memory graph/checkpointer fallback when production or `database_required`
  startup lacks `database_url`.
- No LangGraph cache backend with pickle fallback enabled; hardening/readiness
  evidence must expose the custom-key-function requirement for any allowed
  LangGraph cache path.
- trusted-host validation is required at the ASGI/proxy boundary. FastAPI installs
  Starlette `TrustedHostMiddleware` from `Settings.trusted_hosts`; local defaults cover
  `localhost`, `127.0.0.1`, and test clients, while production must configure the
  canonical API hosts.
- external content is tainted until sanitized and labeled in the context manifest
- model-visible traces and logs redact secrets, credentials, PII, and private tool
  payloads by default

Authentication and authorization:

- JWT/API key auth for API clients. API key records are configured as hashed
  tenant-scoped records, not raw secrets: `key_id:tenant_id:user_id:role:sha256_hex[:groups]`.
- tenant-scoped API keys resolve directly to `AuthPrincipal` after verified bearer
  JWTs. Unsigned `X-Reactor-*` identity headers are a local/test convenience only;
  production ignores user, tenant, role, admin, and group identity headers and
  requires a verified JWT or API key for trusted identity.
- role checks for admin, tool registry, MCP server management, approvals
- 403 responses include structured error bodies. FastAPI `HTTPException(403)` responses
  preserve `detail` and also include `error`, `statusCode`, and stable `code`.

Additional required controls:

- token revocation store: Postgres source of truth, Redis cache optional
- security headers on all HTTP responses
- CSRF protection for browser-admin flows if cookie auth is introduced
- global request body size limits through `Settings.request_body_max_bytes`, plus
  upload-specific file size limits and MIME allowlists
- host header allowlist through `REACTOR_TRUSTED_HOSTS`/`Settings.trusted_hosts` and
  canonical external URL settings through `REACTOR_EXTERNAL_BASE_URL`/
  `Settings.external_base_url`; public A2A metadata must use the configured canonical
  endpoint instead of request Host headers.
- SSRF defense for MCP, web fetch, and document ingestion
- immutable admin audit records
- Slack or external webhook signature validation if integrations are enabled
- event de-duplication for external event sources
- tenant-scoped encryption policy for stored secrets
- separate secret scopes for model providers, MCP servers, and integration tokens

OWASP LLM Top 10 coverage is required before launch:

- LLM01 prompt injection: input, retrieval, tool-output, MCP, and artifact-injection tests
- LLM02 sensitive information disclosure: redaction, logging, trace, and output guards
- LLM03 supply chain: dependency audit, lockfile, model/provider provenance, artifact checksums
- LLM04 data/model poisoning: ingestion provenance, quarantine, reindex, and eval gates
- LLM05 improper output handling: structured validation before downstream use
- LLM06 excessive agency: tool allowlists, approvals, sandbox, and least privilege
- LLM07 system prompt leakage: no secrets in prompts and prompt-leak hardening tests
- LLM08 vector/embedding weaknesses: ACL-before-ranking, poisoning tests, and reindex audit
- LLM09 misinformation: citations, groundedness eval, refusal/fallback policy
- LLM10 unbounded consumption: token, tool, time, queue, and cost budgets

## Observability

| Area | Decision | Version |
| --- | --- | --- |
| Structured logs | structlog | 26.1.0 |
| Metrics | prometheus-client | 0.25.0 |
| Tracing API | opentelemetry-api | 1.43.0 |
| Tracing SDK | opentelemetry-sdk | 1.43.0 |
| FastAPI instrumentation | opentelemetry-instrumentation-fastapi | 0.64b0 |
| Agent traces/evals | LangSmith | 0.9.3 |
| Error tracking | sentry-sdk | 2.63.0, optional |

Tracing exporter options:

- `console`: local OpenTelemetry span export.
- `otlp_http`: OpenTelemetry OTLP/HTTP export using configured endpoint and headers.
- `langsmith`: LangSmith tracing through LangChain environment variables
  (`LANGSMITH_TRACING`, `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT`,
  `LANGSMITH_API_KEY`). Reactor also enables LangSmith privacy env defaults
  (`LANGSMITH_HIDE_INPUTS`, `LANGSMITH_HIDE_OUTPUTS`, `LANGSMITH_HIDE_METADATA`)
  unless explicitly disabled. This is an LLM trace/eval destination, not a replacement
  for Reactor's product metrics, cost ledger, audit logs, or compliance retention stores.

Every run must produce:

- run-level trace id
- model call spans
- tool call spans
- guard decision events
- approval events
- token/cost usage records
- final status and error category

Metric families:

- `reactor_runs_total{status,graph,tenant}`
- `reactor_run_duration_seconds{graph,model,status}`
- `reactor_model_tokens_total{provider,model,direction}`
- `reactor_model_cost_total{provider,model,tenant}`
- `reactor_tool_calls_total{tool,risk,status}`
- `reactor_guard_decisions_total{stage,decision}`
- `reactor_rag_retrieval_duration_seconds{collection,mode}`
- `reactor_rag_chunks_returned_total{collection,mode}`
- `reactor_checkpoint_writes_total{status}`
- `reactor_approval_wait_seconds{tool,risk}`
- `reactor_job_queue_depth{queue,tenant}`
- `reactor_job_attempts_total{queue,status}`
- `reactor_outbox_dispatch_total{destination,status}`
- `reactor_context_tokens_total{graph,band,model}`
- `reactor_artifact_bytes_total{tenant,mime}`
- `reactor_eval_regressions_total{suite,graph}`

Compatibility metric ingestion accepts legacy MCP health, tool-call, and eval-result
events through FastAPI. Production adapters should normalize those events into
Prometheus/OpenTelemetry/product stores; the HTTP compatibility buffer is not a
durable source of truth.

SLOs must be defined before production launch for:

- run creation availability
- streaming first-event latency
- model/tool timeout rate
- retrieval latency
- checkpoint write failure rate
- approval resume success rate
- queue claim latency
- outbox dispatch lag
- artifact upload/download latency
- context assembly latency and token budget overrun rate

Tracing rules:

- Traces include decision metadata, not raw secrets.
- Sensitive payload capture is disabled by default and can be enabled only per tenant
  with documented retention.
- Every fallback, approval, retry, queue reclaim, and outbox dispatch links to the
  same root trace id.

## Testing And Evaluation

| Area | Decision | Version |
| --- | --- | --- |
| Unit/integration tests | pytest | 9.1.1 |
| Async tests | pytest-asyncio | 1.4.0 |
| Coverage | pytest-cov | 7.1.0 |
| Property tests | hypothesis | 6.155.7 |
| HTTP mocking | respx | 0.23.1 |
| Container tests | testcontainers | 4.14.2 |
| Lint/format | ruff | 0.15.20 |
| Type check | pyright | 1.1.411 |
| Secondary type check | mypy | 2.1.0, optional |

Required test lanes:

- unit: pure graph nodes, guards, tool schemas, cost accounting
- integration: Postgres checkpoint, pgvector retrieval, Redis profile, MCP server registry
- hardening: prompt injection, malicious tool output, approval bypass, token/cost limits
- eval: golden task set through LangSmith datasets and local pytest assertions
- smoke: health, ready, create run, stream events, resume interrupted run, cancel run
- migration: export/import count and checksum parity
- contract: API schema snapshot, API boundary readiness facet, and streaming event snapshot
- retrieval eval: recall@k, faithfulness, groundedness, citation accuracy
- load: concurrent stream, checkpoint, Redis lock, and Postgres pool behavior
- security: SSRF, prompt injection, malicious tool output, approval bypass, secret leak
- durability: queue reclaim, fencing token, outbox idempotency, inbox de-duplication
- artifact: MIME spoofing, parser failure, retention deletion, signed URL expiry
- sandbox: filesystem escape, network egress denial, secret isolation, resource limits
- context: manifest reproducibility, message-pair trimming, summary source ranges
- model routing: fallback constraints, provider outage, budget exhaustion, region policy

No feature is complete without at least one focused regression test. Safety-sensitive
features require paired malicious and safe inputs.

Iteration strategy:

- Do not run full `pytest` after every small TDD slice by default.
- During implementation, run the single RED/GREEN test first, then the nearest affected
  unit/integration files.
- Commit granularity checklist: commit at reviewable product or safety
  boundaries, not every RED/GREEN micro-step. A commit should normally contain
  one coherent behavior, policy, workflow, or evidence-sensor change plus its
  tests. Batch adjacent fixture, CLI wording, report-shape, and readiness-surface
  edits when they only support the same behavior; split commits when rollback,
  review ownership, migration risk, or verification scope would become
  ambiguous.
- Version bump boundary: patch tags are for verified hardening batches; minor tags
  require a user-visible product/runtime capability boundary, not just additive
  evidence fields, diagnostics, docs, or focused tests; major tags require an
  incompatible product, API, data, or deployment contract.
- Long-running hardening goal stop condition: do not mark a goal complete merely
  because one coherent slice landed or a commit was pushed. After each stable
  slice, continue with the next highest-risk gap; stop only when the requested
  release, parity, or hardening boundary is met; memory or context pressure is a
  handoff condition, not a completion condition.
- Before a small or batched coherent commit, run static gates and the affected lane
  tests.
- Run the full release gate after a meaningful batch, after cross-boundary changes,
  before marking a parity ledger area `verified`, and before release or cutover evidence.
- Keep agent harness improvements executable. Repeated model or coding-agent mistakes
  should become focused tests, architecture checks, smoke/eval gates, typed policy
  surfaces, or clearer local scripts before they become longer prompt prose.

Evaluation requirements:

- Start with small but representative golden sets before scaling to large eval suites.
- Store every eval example with tenant-safe fixtures, expected behavior, rubric, and
  required tool/retrieval permissions.
- Treat LangSmith as managed observability/evaluation infrastructure, not as the
  product source of truth. Reactor keeps tenant policy, redaction, release gates,
  and eval case ownership in code and Postgres-backed stores.
- Source-controlled eval suites are the product-owned source of truth. Use
  `reactor-langsmith-eval-sync` to publish enabled cases into LangSmith `kv`
  datasets for managed experiments, comparison, and release review. Published
  examples use deterministic case-derived ids and the `regression` split so
  repeated syncs are idempotent and release review can verify split coverage.
- RAG metrics include context precision, context recall, faithfulness/groundedness,
  answer relevance, citation accuracy, latency, and cost.
- Agent metrics include task success, final-state correctness, tool efficiency,
  approval correctness, recovery quality, and budget adherence.
- LLM-as-judge rubrics are versioned and spot-checked by humans.
- Evals compare old vs new prompt/model/graph releases before promotion.
- Production feedback can create eval candidates, but human review is required before
  a case becomes a release gate.

Release gates:

- `uv lock --check`
- `ruff check`
- `ruff format --check`
- `pyright`
- `pytest`
- integration tests with Postgres/pgvector
- Redis profile integration tests when Redis is configured
- MCP and A2A protocol contract tests for enabled transports
- LangGraph pause/resume/checkpoint smoke
- RAG eval baseline does not regress beyond the agreed tolerance
- dependency audit has no untriaged high/critical advisories

## Dependency Policy

Use exact pins in `uv.lock`. `pyproject.toml` may use compatible ranges for libraries,
but release builds must come from the lockfile.

Initial dependency groups:

```text
default:
  fastapi, uvicorn, pydantic, pydantic-settings, langgraph, langchain,
  langchain-openai, langchain-anthropic, langchain-google-genai,
  langgraph-checkpoint-postgres, sqlalchemy, alembic, psycopg,
  langchain-postgres, langmem, redis, mcp, langchain-mcp-adapters,
  a2a-sdk[fastapi,telemetry], langsmith,
  structlog, prometheus-client, opentelemetry-*, sse-starlette,
  orjson, tenacity, croniter

dev:
  pytest, pytest-asyncio, pytest-cov, hypothesis, respx,
  testcontainers, ruff, pyright, mypy, typer, rich, types-croniter

optional:
  langchain-community, mcp[cli], mcp[ws], fastmcp,
  a2a-sdk[grpc], a2a-sdk[postgresql], a2a-sdk[signing],
  sentry-sdk, deepeval, ragas,
  qdrant-client, langgraph-checkpoint-redis, pgvector,
  pgqueuer[psycopg], dbos, temporalio, arq,
  mem0ai, zep-cloud, graphiti-core, letta, cognee, google-adk

ingestion:
  pypdf, python-magic, defusedxml, unstructured

artifact-production:
  boto3
```

Compatibility note: Python 3.13 runtime dependencies resolve with
`langchain-postgres 0.0.17` in the default group as long as standalone
`pgvector==0.4.2` is not also pinned. `langchain-postgres 0.0.17` depends on
`pgvector<0.4` and currently resolves to `pgvector 0.3.6`. If direct `pgvector 0.4.x`
features become required, isolate that code path or wait for `langchain-postgres` to
widen its dependency range.

Protocol compatibility note: the default dependency group resolves with
`mcp==1.28.1`, `langchain-mcp-adapters==0.3.0`, and
`a2a-sdk[fastapi,telemetry]==1.1.0` on Python 3.13.14. `a2a-sdk[all]==1.1.0`
also resolves, but it is intentionally not the default because it pulls optional SQL,
gRPC, and database-client extras that Reactor should enable only by profile. Do not
combine `google-adk[a2a] 2.3.0` with the default A2A stack; that extra currently
requires an older incompatible `a2a-sdk` range.

Scheduler compatibility note: use `croniter==6.2.2` for dynamic scheduled-job due
calculation, with Spring-style six-field cron expressions interpreted as
seconds-first. The scheduler still uses Postgres leases as the authority for
ownership; croniter only computes whether an enabled job is due.

PromptLab scheduled auto-optimization is an opt-in FastAPI lifespan runner separate
from arbitrary dynamic jobs. It resolves configured template IDs or all tenant prompt
templates, then delegates to the PromptLab auto-optimizer and LangGraph-backed
`RunService`; experiment status, trials, reports, and failures stay in Postgres.

Avoid adding framework-level guardrail packages to the core until they prove value.
Reactor's primary guardrails are deterministic code, explicit schemas, tests, and
approval policy.

Do not add a second agent framework to the serving path. OpenAI Agents SDK,
Claude/Anthropic SDK patterns, Vercel AI SDK patterns, DBOS, Temporal, Restate, and
similar systems are useful references, but the core runtime remains FastAPI +
LangGraph + LangChain unless a specific graduation gate is met.

When those references expose a stronger generic capability than Reactor's code, port
the idea through LangGraph/LangChain primitives first. Add standalone libraries only
when they are compatible with the pinned Python 3.13 stack, have current security
advisory posture checked, and do not create a second serving-path agent runtime.

## Python Module Architecture

Use a `src/` layout and one importable package: `reactor`. The package is organized by
product capability, not by framework layer. The layout below is a starting map; omit
or defer packages for workflows that are not selected yet.

Why this structure:

- LangGraph projects need graph definitions, node functions, state schemas, tools, and
  persistence/config separated enough for Studio/dev server and production serving.
- FastAPI scales cleanly when routers, dependencies, and request/response schemas are
  grouped by API domain.
- Python packaging recommends `src/` layout to keep installed-package behavior honest
  and prevent accidental imports from the repository root.
- Agent systems need deterministic policy boundaries around prompts, tools, memory,
  retrieval, and side effects. Those boundaries should be Python modules, not prompt
  conventions.

Module rules:

- `api` is only the HTTP boundary: routers, dependencies, request/response DTOs,
  auth extraction, SSE adapters. It calls application services, not SQL directly.
- `agents` owns LangGraph state, graph factories, nodes, routers, graph profiles, and
  graph-level policies. Nodes should call services/tools, not raw repositories.
- `context`, `prompts`, `providers`, `tools`, `rag`, `memory`, `guards`, and `hooks`
  are first-class packages because they change independently and have different eval
  gates.
- `response` owns model-visible finalization after output guards: response filters,
  structured output validation/repair, output boundary enforcement, and delivery-safe
  formatting. Keep it separate from `guards` so policy decisions and presentation
  normalization can evolve independently.
- `prompt_lab` owns prompt experiments, trials, recommendations, and report contracts.
  It may call `prompts`, `evals`, and application services, but production graph nodes
  should not depend on experiment-only helpers.
- `cache` owns ephemeral cache contracts and adapters. Redis-backed implementations
  must stay cache/coordination only; durable agent state remains in Postgres.
- `persistence` owns SQLAlchemy models, Alembic migrations, database sessions, and
  repository base helpers. Domain services import repositories through typed
  interfaces or concrete repository classes, never raw sessions scattered through code.
- `jobs` owns durable queue, leases, outbox/inbox dispatch, and retry policy.
- `workers` wires process entrypoints only. Business logic stays in feature packages.
- `core` owns typed settings, lifespan startup, container construction, feature flags,
  and shared exception mapping.
- `kernel` is the tiny shared kernel: ids, clocks, pagination, result/error primitives,
  tenant/user identity value objects. Do not turn it into a utility dump.
- `observability` owns logs, metrics, tracing, LangSmith/OpenTelemetry integration, and
  redaction policy.
- `evals` owns datasets, judges, rubrics, and release gates; production code may emit
  eval candidates but cannot depend on eval-only helpers.

Dependency direction:

```text
api -> application services -> feature packages -> persistence/providers
workers -> jobs/agents/rag/memory/tools/a2a
agents -> context/prompts/providers/tools/rag/memory/guards/hooks
feature packages -> kernel/observability
persistence -> kernel
```

Forbidden dependencies:

- Feature packages do not import FastAPI routers or request objects.
- Repositories do not import LangGraph, LangChain chat models, or FastAPI.
- Graph nodes do not open database sessions directly.
- API routers do not assemble prompts, retrieve chunks, or execute tools directly.
- `kernel` does not import feature packages.
- No dynamic imports from user-controlled strings.

LangChain/LangGraph boundaries:

- LangGraph imports are allowed in `agents`, `memory`, and graph-specific tests.
- LangChain model/provider imports live behind `providers` or feature-specific
  adapters. Do not import provider SDKs throughout the codebase.
- LangChain `Document`, retriever, embedding, and vector-store interfaces are allowed
  at `rag` and `memory` boundaries.
- LangMem is used from `memory` jobs/services only.
- MCP adapters are wrapped by `tools.mcp`; graph nodes see Reactor tool contracts.
- A2A SDK objects are wrapped by `a2a`; graph nodes see Reactor delegation services,
  task references, and persisted events, not raw protocol handlers.

Testing layout:

- Tests mirror the package path under `tests/unit`, `tests/integration`,
  `tests/hardening`, `tests/evals`, and `tests/contract`.
- A narrow change starts with the closest unit test. Cross-boundary changes add an
  integration or contract test.
- Graph tests assert state transitions, checkpoint/resume behavior, tool-call/message
  pair integrity, and interrupt/resume paths.
- Tool tests assert schema validation, recovery-friendly errors, output sanitization,
  idempotency, and approval policy.

## Repository Layout

```text
src/
  reactor/
    __init__.py
    core/
      settings.py
      container.py
      lifespan.py
      errors.py
    kernel/
      ids.py
      time.py
      pagination.py
      tenancy.py
    api/
      routers/
      schemas/
      dependencies.py
    agents/
      graphs/
      state.py
      nodes/
      policies/
    context/
      assembler.py
      manifests.py
    prompts/
      registry.py
    providers/
      registry.py
      routing.py
      embeddings.py
      rerankers.py
    jobs/
      queue.py
      outbox.py
      inbox.py
    tools/
      registry.py
      mcp/
      builtins/
      schemas.py
    a2a/
      agent_card.py
      server.py
      client.py
      registry.py
      tasks.py
    artifacts/
      storage.py
      repository.py
    guards/
      input.py
      output.py
      tool_output.py
    sandbox/
      policy.py
    hooks/
    memory/
      store.py
      service.py
      proposals.py
      consolidation.py
      retrieval.py
      embeddings.py
    persistence/
      models.py
      repositories/
      migrations/
    observability/
      logging.py
      metrics.py
      tracing.py
    workers/
      run_worker.py
      outbox_worker.py
      ingestion_worker.py
    evals/
      judges.py
tests/
  unit/
  integration/
  hardening/
  evals/
  contract/
langgraph.json
pyproject.toml
uv.lock
.python-version
```

## Deployment Profiles

Local:

- FastAPI app
- Postgres/pgvector
- Redis optional
- local filesystem artifact adapter
- LangSmith optional

Production single replica:

- FastAPI app
- Postgres/pgvector required
- Redis optional only if shared rate limits/fanout are disabled
- S3-compatible artifact storage required if uploads or generated artifacts are enabled
- LangSmith or OpenTelemetry exporter required

Production multi replica:

- API replicas
- worker replicas
- Postgres/pgvector required
- Redis required
- S3-compatible artifact storage required
- readiness fails if Redis is configured but unavailable
- run ownership uses Redis TTL locks plus Postgres status checks and fencing tokens
- queue ownership uses Postgres leases and fencing tokens

## Runtime And Deployment

Process model:

- API: ASGI app served by Uvicorn workers.
- Worker: separate process type for background graph runs, ingestion, scheduler jobs,
  and retries.
- Outbox worker: separate process type for webhooks, vector sync, artifact exports,
  and external event dispatch.
- Migration: one-shot Alembic job before application rollout.
- Scheduler: single active scheduler lease per job, backed by Postgres row lease
  and fencing token. Redis may be used for ephemeral wakeups or pub/sub, but it is
  not authoritative for scheduler ownership or replay.
- PromptLab scheduler: opt-in periodic runner for auto-optimization only; it must be
  non-reentrant per process and use Postgres-backed PromptLab records for durable
  experiment state.

Startup checks:

- settings parse and secret presence
- database connectivity and migration head
- pgvector extension availability
- LangGraph checkpointer setup
- durable queue/outbox tables ready
- Redis connectivity if configured as required
- artifact storage connectivity if configured as required
- provider key presence for enabled providers
- MCP server preflight for required servers
- A2A agent card validation and required peer preflight

Shutdown:

- stop accepting new runs
- close SSE streams with retryable event
- cancel in-process model/tool calls through `asyncio.CancelledError`
- release Redis locks
- flush final run events and metrics
- stop queue claims and drain/park in-flight outbox dispatches

Docker baseline:

- base image: Python 3.13.14 slim
- install with `uv sync --frozen`
- run as non-root user
- healthcheck hits `/healthz`
- readiness checks `/readyz`

Database upgrade:

- v1 target is PostgreSQL 18.4 with pgvector 0.8.3.
- If importing from older PostgreSQL versions, rehearse logical dump/restore into the
  target image and validate extensions before cutover.
- Do not upgrade production database and application runtime in the same irreversible
  step without rollback rehearsal.

## Migration Plan

1. Add ADR stating greenfield Python/LangGraph scope and prior-structure non-goals.
2. Inventory prior features/data as `keep`, `remap`, `drop`, or `defer`.
3. Add Python project skeleton, `pyproject.toml`, `uv.lock`, `.python-version`, and
   `langgraph.json`.
4. Add FastAPI health/readiness/metrics endpoints.
5. Add minimal async LangGraph run with Postgres checkpointer.
6. Add Postgres/Alembic baseline schema only for kept/remapped product data.
7. Add SSE event persistence and replay.
8. Add guard, approval, max tool call, timeout, and usage-ledger policy using
   LangGraph-native interrupts/messages where possible.
9. Add context manifest, prompt/model profile, and provider routing only where the
   framework does not already provide enough traceability.
10. Add durable queue/outbox/inbox/idempotency tables unless a durable executor
    replaces them.
11. Add tool catalog, artifact references, and approval gate.
12. Add MCP server registry and MCP tool adapter.
13. Add A2A agent card, peer registry, task mapping, push notification outbox, and
    protocol contract tests.
14. Add LangMem-backed memory extraction and pgvector-backed RAG for selected product
    workflows.
15. Add selected sessions, scheduler, feedback, eval, admin, and integration APIs only
    when their product workflow is confirmed.
16. Add eval harness, hardening tests, and release gates.
17. Add Redis production profile for rate limit, locks, pub/sub, and cache wakeups.
18. Add artifact storage and ingestion parser profile.
19. Run data cutover only for retained data, then remove obsolete modules and adapters.

## Validation Notes

Current validation performed on 2026-06-26 and rechecked on 2026-06-27 Asia/Seoul
(2026-06-26 in US time):

- PyPI metadata confirmed the pinned LangChain, LangGraph, FastAPI, MCP, A2A,
  Postgres, Redis, observability, and test package versions exist.
- PyPI metadata confirmed `mcp 1.28.1`, `langchain-mcp-adapters 0.3.0`,
  `a2a-sdk 1.1.0`, and optional `fastmcp 3.4.2`.
- Slack integration recheck confirmed `slack-sdk 3.42.0` and `aiohttp 3.14.1` are
  the current package baselines as of the 2026-06-26 cutoff. `slack-bolt 1.28.0`
  remains a reference implementation dependency, not a Reactor default dependency,
  because Reactor owns HTTP ingress, durable outbox, and Socket Mode lifecycle through
  FastAPI plus the Slack SDK boundary.
- PyPI metadata also confirmed added candidate versions for `boto3`, `pypdf`,
  `python-magic`, `defusedxml`, `unstructured`, `pgqueuer`, `dbos`, `temporalio`,
  and `arq`.
- PyPI metadata confirmed `langmem 0.0.30`, `mem0ai 2.0.8`, `zep-cloud 3.23.0`,
  `graphiti-core 0.29.2`, `letta 0.16.8`, and `cognee 1.2.2` exist; only LangMem
  is included in the default dependency group.
- Local setup now has `uv 0.11.24` installed under `~/.local/bin`, uv-managed
  CPython `3.13.14`, and repo-level `.python-version` pinned to `3.13.14`.
- Runtime dependency resolution for CPython 3.13 target succeeds with
  `langchain-postgres 0.0.17`, `langmem 0.0.30`, `mcp 1.28.1`,
  `langchain-mcp-adapters 0.3.0`, and `a2a-sdk[fastapi,telemetry] 1.1.0` in the
  default group when standalone `pgvector==0.4.2` is not directly pinned.
- `a2a-sdk[all] 1.1.0` resolves but is excluded from the default group because
  optional database and gRPC dependencies should be profile-specific.
- `google-adk[a2a] 2.3.0` conflicts with the current A2A baseline because it pins an
  older incompatible `a2a-sdk` range; keep it out of the default stack.
- Adding direct `pgvector==0.4.2` alongside `langchain-postgres 0.0.17` is
  unsatisfiable because `langchain-postgres` currently requires `pgvector<0.4`.
- A document scan found no previous backend framework/language runtime terms in this
  specification.
- Initial repository setup required `pyproject.toml`, `uv.lock`, `langgraph.json`,
  and the package layout above; these files are now serving-path contracts and must
  remain aligned with this specification.
- Community and production-agent references added missing contracts for durable job
  execution, context manifests, artifact handoff, sandbox isolation, and eval gating.

## Sources Checked

- Python downloads: https://www.python.org/ftp/python/
- LangChain Python docs: https://docs.langchain.com/oss/python/langchain/overview
- LangGraph Python docs: https://docs.langchain.com/oss/python/langgraph/overview
- LangGraph persistence docs: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph checkpointer docs: https://docs.langchain.com/oss/python/langgraph/checkpointers
- LangGraph fault tolerance docs: https://docs.langchain.com/oss/python/langgraph/fault-tolerance
- LangGraph interrupts docs: https://docs.langchain.com/oss/python/langgraph/interrupts
- LangGraph subgraphs docs: https://docs.langchain.com/oss/python/langgraph/use-subgraphs
- LangGraph thinking guide: https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph
- LangGraph graph API docs: https://docs.langchain.com/oss/python/langgraph/graph-api
- LangGraph application structure docs: https://docs.langchain.com/oss/python/langgraph/application-structure
- LangGraph low-level concepts docs: https://docs.langchain.com/oss/python/langgraph/graph-api
- LangGraph functional API docs: https://docs.langchain.com/oss/python/langgraph/functional-api
- LangGraph subgraphs docs: https://docs.langchain.com/oss/python/langgraph/use-subgraphs
- LangGraph durable execution docs: https://docs.langchain.com/oss/python/langgraph/durable-execution
- LangChain context engineering docs: https://docs.langchain.com/oss/python/langchain/context-engineering
- LangChain middleware docs: https://docs.langchain.com/oss/python/langchain/middleware
- LangChain retrieval docs: https://docs.langchain.com/oss/python/langchain/retrieval
- LangChain RAG docs: https://docs.langchain.com/oss/python/langchain/rag
- LangGraph agentic RAG docs: https://docs.langchain.com/oss/python/langgraph/agentic-rag
- LangGraph memory docs: https://docs.langchain.com/oss/python/langgraph/add-memory
- LangGraph stores docs: https://docs.langchain.com/oss/python/langgraph/stores
- LangMem docs: https://langchain-ai.github.io/langmem/
- LangMem conceptual guide: https://langchain-ai.github.io/langmem/concepts/conceptual_guide/
- LangMem SDK launch: https://www.langchain.com/blog/langmem-sdk-launch
- LangChain PGVector docs: https://docs.langchain.com/oss/python/integrations/vectorstores/pgvector
- LangChain tools docs: https://docs.langchain.com/oss/python/langchain/tools
- LangChain security policy: https://docs.langchain.com/oss/python/security-policy
- LangChain security advisories: https://github.com/langchain-ai/langchain/security/advisories
- LangGraph security advisories: https://github.com/langchain-ai/langgraph/security/advisories
- LangGraph msgpack advisory: https://github.com/advisories/GHSA-g48c-2wqr-h844
- LangChain unsafe deserialization advisory: https://github.com/advisories/GHSA-pjwx-r37v-7724
- Starlette security advisories: https://github.com/Kludex/starlette/security/advisories
- pgvector docs: https://github.com/pgvector/pgvector
- Qdrant LangChain docs: https://qdrant.tech/documentation/frameworks/langchain/
- Redis Pub/Sub docs: https://redis.io/docs/latest/develop/pubsub/
- Redis distributed lock docs: https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/
- MCP latest specification: https://modelcontextprotocol.io/specification/2025-11-25
- MCP SDK docs: https://modelcontextprotocol.io/docs/sdk
- MCP authorization spec: https://modelcontextprotocol.io/specification/draft/basic/authorization
- MCP authorization security considerations: https://modelcontextprotocol.io/specification/draft/basic/authorization/security-considerations
- Slack agent development: https://docs.slack.dev/ai/developing-agents
- Slack MCP server: https://docs.slack.dev/ai/slack-mcp-server
- Slack Events API: https://docs.slack.dev/apis/events-api/
- Slack Socket Mode for Bolt Python: https://docs.slack.dev/tools/bolt-python/concepts/socket-mode/
- Slack agent governance: https://docs.slack.dev/ai/agent-governance
- Slack agent context management: https://docs.slack.dev/ai/agent-context-management
- A2A latest specification: https://a2a-protocol.org/latest/specification/
- A2A project: https://github.com/a2aproject/A2A
- A2A Python SDK: https://github.com/a2aproject/a2a-python
- PyPI `mcp`: https://pypi.org/project/mcp/
- PyPI `langchain-mcp-adapters`: https://pypi.org/project/langchain-mcp-adapters/
- PyPI `a2a-sdk`: https://pypi.org/project/a2a-sdk/
- PyPI `fastmcp`: https://pypi.org/project/fastmcp/
- PyPI `google-adk`: https://pypi.org/project/google-adk/
- OWASP LLM Top 10 2025: https://genai.owasp.org/llm-top-10/
- Anthropic Building effective agents: https://www.anthropic.com/research/building-effective-agents
- Anthropic multi-agent research system: https://www.anthropic.com/engineering/multi-agent-research-system
- OpenAI Harness engineering for agentic coding:
  https://openai.com/index/harness-engineering/
- HumanLayer 12-factor agents: https://github.com/humanlayer/12-factor-agents
- LangSmith observability docs: https://docs.smith.langchain.com/observability
- LangSmith evaluation docs: https://docs.smith.langchain.com/evaluation
- OpenAI Agents SDK guardrails: https://openai.github.io/openai-agents-python/guardrails/
- OpenAI Agents SDK tracing: https://openai.github.io/openai-agents-python/tracing/
- OpenAI Agents SDK running agents: https://openai.github.io/openai-agents-python/running_agents/
- Vercel tool reduction case study: https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools
- Vercel filesystem/bash agent pattern: https://vercel.com/blog/how-to-build-agents-with-filesystems-and-bash
- Vercel agent security boundaries: https://vercel.com/blog/security-boundaries-in-agentic-architectures
- Temporal durable AI agents: https://temporal.io/blog/from-ai-hype-to-durable-reality-why-agentic-flows-need-distributed-systems
- LangSmith RAG evaluation docs: https://docs.langchain.com/langsmith/evaluate-rag-tutorial
- Ragas metrics docs: https://docs.ragas.io/en/stable/concepts/metrics/
- DeepEval faithfulness docs: https://deepeval.com/docs/metrics-faithfulness
- Mem0 docs: https://docs.mem0.ai/introduction
- Mem0 paper: https://arxiv.org/html/2504.19413v1
- Zep Graphiti: https://www.getzep.com/platform/graphiti/
- Graphiti GitHub: https://github.com/getzep/graphiti
- Zep temporal knowledge graph paper: https://arxiv.org/abs/2501.13956
- Letta memory docs: https://docs.letta.com/guides/core-concepts/memory/archival-memory
- Cognee docs: https://docs.cognee.ai/
- Cognee long-term knowledge guide: https://www.cognee.ai/blog/deep-dives/long-term-knowledge-ai-agents
- FastAPI docs: https://fastapi.tiangolo.com/
- FastAPI bigger applications docs: https://fastapi.tiangolo.com/tutorial/bigger-applications/
- FastAPI deployment version docs: https://fastapi.tiangolo.com/deployment/versions/
- Litestar docs: https://docs.litestar.dev/latest/
- uv docs: https://docs.astral.sh/uv/
- PyPA src layout discussion: https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/
- PyPI package metadata for versions listed above
- Docker Hub tags for `pgvector/pgvector`, `postgres`, and `redis`

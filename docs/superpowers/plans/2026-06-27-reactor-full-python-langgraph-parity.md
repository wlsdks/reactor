# Reactor Full Python/LangGraph Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port every retained Reactor feature from `spring-v6.99.0` into the Python 3.13/FastAPI/LangGraph/LangChain architecture described in `docs/architecture/python-langgraph-replatform-spec.md`.

**Architecture:** Python owns product policy, tenancy, APIs, persistence, evaluation, and operational contracts. LangGraph owns graph execution/checkpoints/interrupts; LangChain owns provider/tool integration boundaries; Postgres/pgvector is the durable source of truth; Redis remains ephemeral coordination only.

**Tech Stack:** Python 3.13, FastAPI, LangGraph, LangChain, LangMem, MCP SDK, A2A SDK, SQLAlchemy, Alembic, PostgreSQL/pgvector, Redis, OpenTelemetry, Prometheus, pytest, pyright, ruff.

---

## File Structure

- `docs/migration/full-replatform-parity-ledger.md`: canonical feature parity status.
- `docs/migration/module-architecture-review.md`: module boundary decisions and gap list.
- `src/reactor/agents/`: LangGraph graph profiles, state, runner, streaming, interrupts.
- `src/reactor/context/`: context manifest, message trimming, prompt assembly inputs.
- `src/reactor/prompts/`: versioned prompt profiles, tool forcing policy, prompt registry.
- `src/reactor/providers/`: model providers, routing, fallback, token/cost accounting.
- `src/reactor/tools/`: first-party tool contracts, execution gate, sanitizer, audit.
- `src/reactor/mcp/`: MCP registry, preflight, protocol negotiation, tool adapter.
- `src/reactor/a2a/`: A2A SDK endpoint, peer registry, task mapping, push outbox.
- `src/reactor/rag/`: ingestion, chunking, hybrid retrieval, citations, diagnostics.
- `src/reactor/memory/`: session memory, LangMem proposals, namespace and deletion policy.
- `src/reactor/guards/`: input/output guard pipeline and hardening rules.
- `src/reactor/hooks/`: fail-open hooks and audit/metrics hooks.
- `src/reactor/auth/`: JWT/IAM, RBAC, revocation, user identity.
- `src/reactor/admin/`: admin analytics and operations APIs.
- `src/reactor/slack/`: Slack event, command, bot, and FAQ integration.
- `src/reactor/scheduler/`: durable scheduled jobs and execution replay.
- `src/reactor/eval/`: eval cases, result store, scenario regression, red-team suites.
- `src/reactor/observability/`: metrics, tracing, SLOs, pricing, cost ledger.
- `src/reactor/persistence/`: SQLAlchemy models/stores and Alembic schema.
- `tests/unit/`: deterministic behavior tests.
- `tests/integration/`: API, DB, Redis, MCP, A2A, RAG, and worker integration tests.
- `tests/hardening/`: prompt injection, malicious tool output, approval bypass, SSRF, secret leak tests.

## Task 0: Freeze Python Module Boundaries

**Files:**
- Create: `docs/migration/module-architecture-review.md`
- Create: `tests/unit/test_module_architecture.py`
- Modify: `src/reactor/core/container.py`
- Create: package scaffolds under `src/reactor/*`

- [x] **Step 1: Compare module structures**

Required behavior:

- use `docs/architecture/python-langgraph-replatform-spec.md` as the primary contract
- inspect an optional sibling `hermes-agent` checkout for runtime responsibility coverage
- check current official LangGraph, OpenAI Agents SDK, and CrewAI docs for agent
  boundary concepts

- [x] **Step 2: Enforce framework import boundaries**

Required behavior:

- LangGraph imports stay in `agents`/`memory`
- FastAPI imports stay in `api`
- SQLAlchemy imports stay in `core`/`persistence`
- scaffolds keep admin/auth/slack/scheduler/jobs/workers/hooks/evals/sandbox/artifacts
  visible until parity work is implemented

## Task 1: Freeze Feature Inventory And Completion Gates

**Files:**
- Modify: `docs/migration/full-replatform-parity-ledger.md`

- [x] **Step 1: Record current audit counts**

Run:

```bash
git ls-tree -r --name-only spring-v6.99.0 modules \
  | awk -F/ '/src\/main\/kotlin/ {count[$1"/"$2]++} END {for (m in count) print count[m], m}' \
  | sort -nr
git grep -n "@\(GetMapping\|PostMapping\|PutMapping\|PatchMapping\|DeleteMapping\|RequestMapping\)" \
  spring-v6.99.0 -- 'modules/**/*.kt' | wc -l
git grep -n "interface .*Store\|class Jdbc.*Store\|class InMemory.*Store" \
  spring-v6.99.0 -- 'modules/**/*.kt' | wc -l
```

Expected: the ledger contains module counts, 332 route annotations, and 155 store entries.

- [x] **Step 2: Expand each feature area into endpoint/store/test rows**

Run:

```bash
git grep -n "@\(GetMapping\|PostMapping\|PutMapping\|PatchMapping\|DeleteMapping\|RequestMapping\)" \
  spring-v6.99.0 -- 'modules/**/*.kt' \
  > /tmp/reactor-route-inventory.txt
git grep -n "interface .*Store\|class Jdbc.*Store\|class InMemory.*Store" \
  spring-v6.99.0 -- 'modules/**/*.kt' \
  > /tmp/reactor-store-inventory.txt
```

Expected: every retained endpoint/store has a row in `docs/migration/full-replatform-parity-ledger.md` before it is implemented.

## Task 2: Agent Runtime Parity

**Files:**
- Modify: `src/reactor/agents/state.py`
- Modify: `src/reactor/agents/graph.py`
- Create: `src/reactor/agents/events.py`
- Create: `src/reactor/agents/streaming.py`
- Create: `src/reactor/agents/interrupts.py`
- Test: `tests/unit/test_agent_graph_policy.py`
- Test: `tests/integration/test_agent_streaming.py`

- [x] **Step 1: Add failing tests for graph node order**

Run:

```bash
uv run pytest tests/unit/test_agent_graph_policy.py -q
```

Expected: tests fail until the graph exposes guard, context, model, approval, tool, output guard, and hook nodes.

- [x] **Step 2: Implement graph profile factories**

Required behavior:

- request flow is guard -> context -> model -> approval -> tool -> output_guard -> hooks
- max tool calls removes active tools and asks for final answer
- approval resume commands use LangGraph `Command(resume=...)`; full graph interrupt wiring remains open until tool approval execution is ported
- stop reasons are persisted in run metadata
- checkpoints use Postgres when configured

Progress:

- [x] graph profile domain/registry validates profile id, prompt version, provider/model,
  checkpoint namespace, tool allowlist size, and max tool-call limits
- [x] `build_reactor_graph(graph_profile=...)` injects profile metadata, default active
  tools, selected model, prompt version, temperature, and max tool-call policy into state
- [x] request-level active tool and max tool-call overrides remain explicit and take
  precedence over profile defaults
- [x] approval gate marks write/external/destructive pending tool requests as
  `approval_required` and keeps tool execution blocked until an approval resume payload
  is present
- [x] approved resume payloads admit the pending tool request, record deterministic
  idempotency keys, increment tool-call count, and preserve approval metadata in state
- [x] rejected resume payloads stop tool execution with `approval_rejected` metadata
- [x] graph state records `reactor.agent.state.v1` schema version in state and run
  metadata so future checkpoint-breaking changes have an explicit migration boundary
- [x] approved tool execution appends an ordered assistant tool-call message and
  `ToolMessage(tool_call_id=...)` pair, preserving the original tool call id in
  `tool_results`
- [x] profile checkpoint namespace is carried in context manifest and response
  metadata so profile-specific checkpoint routing remains observable

- [x] **Step 3: Add streaming event replay**

Required behavior:

- stream start/token/tool/approval/completion events are persisted to `agent_run_events`
- reconnect with `after_sequence` returns only events after that sequence
- event payloads contain run id, sequence, graph node, and trace id

## Task 3: Prompt, Context, And Model Governance

**Files:**
- Create: `src/reactor/context/manifest.py`
- Create: `src/reactor/context/trimming.py`
- Create: `src/reactor/prompts/profiles.py`
- Create: `src/reactor/providers/routing.py`
- Create: `src/reactor/providers/usage.py`
- Test: `tests/unit/test_context_manifest.py`
- Test: `tests/unit/test_provider_routing.py`

- [x] **Step 1: Port context ordering from the spec**

Required context order:

1. system/developer policy
2. graph profile instructions
3. latest user request
4. approval state
5. session summary and memory
6. RAG context with source labels
7. recent messages on valid pair boundaries
8. tool outputs
9. examples/rubrics

- [x] **Step 2: Implement provider routing**

Required behavior:

- model profile selects provider/model
- fallback records provider, model, reason, latency, and cost
- token usage and max output limits are recorded

Progress:

- [x] prompt releases validate profile/system/developer/example payloads and compute
  stable canonical content hashes
- [x] prompt cache keys include tenant, profile, graph profile, version, provider/model,
  and release hash to prevent stale prompt reuse across releases
- [x] prompt drift reports compare expected release hashes against current release content
- [x] prompt template/version/release PostgreSQL schema, Alembic baseline tables, and
  SQLAlchemy store upsert/find builders are ported with tenant/environment scoping
- [x] graph profile tool forcing policy resolves `auto`, `none`, `required`, and
  `force_one` exposure, constrains request overrides, and records `tool_choice` in
  context/model metadata when a deterministic tool choice is active
- [x] system prompt assembly renders PromptRelease policy, graph profile instructions,
  latest user request, approval state, memory/RAG/message/tool/example bands in spec
  order, labels retrieval/tool content as untrusted data, records a stable rendered
  prompt checksum, and injects the checksum into the LangGraph context manifest
- [x] prompt admin API ports template creation, version creation with canonical
  PromptRelease content hash, environment release promotion, released prompt lookup,
  prompt read/write RBAC, and persistence-unavailable failure contracts

## Task 4: Tool Runtime, Approval, And Output Safety

**Files:**
- Modify: `src/reactor/tools/catalog.py`
- Create: `src/reactor/tools/execution.py`
- Create: `src/reactor/tools/sanitizer.py`
- Create: `src/reactor/tools/idempotency.py`
- Create: `src/reactor/guards/input.py`
- Create: `src/reactor/guards/output.py`
- Test: `tests/unit/test_tool_execution.py`
- Test: `tests/hardening/test_tool_output_sanitization.py`
- Test: `tests/hardening/test_approval_bypass.py`

- [x] **Step 1: Implement deterministic tool admission**

Required behavior:

- risk levels are enforced in code
- write/external/destructive tools require approval unless explicit policy permits
- timeout and idempotency keys wrap every side-effecting call
- tool errors return structured `Error` payloads

- [x] **Step 2: Implement output guard**

Required behavior:

- malicious tool output is treated as data
- PII/secret/canary leaks are blocked or redacted
- guard failures are fail-close
- hook failures are fail-open

Progress:

- [x] dynamic input guard rules evaluate tenant regex/keyword rules in runtime
  `InputGuard.check_async`, fail-close on `BLOCK`, and ignore disabled/WARN/FLAG rules
- [x] production graph factory accepts an injected `InputGuard`, and DB-backed
  containers wire `SqlAlchemyInputGuardRuleStore` into the LangGraph guard node
- [x] static secret leak output guard fails closed in the LangGraph output guard node
- [x] dynamic output guard rule domain/evaluator ports legacy `MASK`/`REJECT`
- [x] output guard rule CRUD/audit/simulate API exposes legacy `/api/output-guard/rules`
  and new `/v1/output-guard/rules`
- [x] output guard rule persistence tables are tenant-scoped in PostgreSQL baseline
- [x] dynamic output guard rules are wired into the production graph execution path
- [x] tool result cache stores successful tool results by deterministic idempotency
  key, and the LangGraph tool executor reuses cache hits without incrementing
  `tool_call_count` while preserving assistant/tool message pair integrity
- [x] per-tool timeout wrapper enforces `ToolSpec.timeout_ms`, returns structured
  timeout error payloads, and records timeout metadata in LangGraph tool execution
- [x] admin tool catalog API exposes tenant-scoped list/get/upsert/enable-disable
  endpoints on `/api/admin/tools` and `/v1/admin/tools`, validates `ToolSpec`
  risk/name contracts, preserves timeout/schema/approval fields, and returns 503
  when persistence is not configured
- [x] admin tool stats API ports legacy `/api/admin/tools/stats` and
  `/api/admin/tools/accuracy` plus new `/v1` paths, deriving outcome
  distribution, server/tool rankings, accuracy, invalid-call, timeout, and
  not-found rates from durable Python tool invocation records
- [x] parallel tool orchestration executes independent `ToolExecutionRequest`
  items concurrently with per-tool timeout/cache/idempotency handling, preserves
  input order in results, and emits ordered assistant/tool message pairs from
  LangGraph `pending_tool_requests`
- [x] LangGraph after-complete hooks are injectable, execute fail-open with
  structured hook failure metadata, and rethrow `asyncio.CancelledError` so
  cancellation still propagates

## Task 5: MCP Runtime Parity

**Files:**
- Modify: `src/reactor/mcp/registry.py`
- Modify: `src/reactor/persistence/mcp_store.py`
- Create: `src/reactor/mcp/client.py`
- Create: `src/reactor/mcp/preflight.py`
- Create: `src/reactor/mcp/tool_adapter.py`
- Test: `tests/integration/test_mcp_registry.py`
- Test: `tests/hardening/test_mcp_ssrf.py`

- [x] **Step 1: Implement MCP preflight**

Required behavior:

- reject unsupported transports
- validate command/URL/auth/timeout
- block private/link-local HTTP targets unless admin policy allows them
- persist status and last connection error

- [x] **Step 2: Implement MCP tool sync**

Required behavior:

- negotiate protocol `2025-11-25`
- use official MCP SDK clients
- snapshot tool list with hash
- convert each tool to Reactor `ToolSpec` with fully qualified `ServerName:tool_name`

## Task 6: A2A And Multi-Agent Parity

**Files:**
- Modify: `src/reactor/a2a/agent_card.py`
- Create: `src/reactor/a2a/server.py`
- Create: `src/reactor/a2a/peers.py`
- Create: `src/reactor/a2a/tasks.py`
- Test: `tests/integration/test_a2a_contract.py`

- [x] **Step 1: Mount A2A SDK endpoint**

Required behavior:

- agent card protocol version is `1.0`
- SDK endpoint is mounted under `/a2a`
- app-owned peer registry and diagnostics are under `/v1/a2a/*`

Progress:

- [x] agent card protocol version is `1.0`
- [x] app-owned peer registry and diagnostics are under `/v1/a2a/*`
- [x] SDK request handler is mounted under `/a2a`
- [x] SDK executor delegates text messages into Reactor LangGraph `run_once`
- [x] SDK task store is backed by Reactor `a2a_tasks` instead of SDK in-memory store

- [x] **Step 2: Persist task events**

Required behavior:

- A2A task/context/message ids map to run/thread/session/idempotency records
- task events are persisted before delivery
- push notifications use outbox with retry/dead-letter behavior

## Task 7: RAG And Memory Parity

**Files:**
- Modify: `src/reactor/rag/documents.py`
- Create: `src/reactor/rag/ingestion.py`
- Create: `src/reactor/rag/retriever.py`
- Create: `src/reactor/rag/citations.py`
- Modify: `src/reactor/memory/policy.py`
- Create: `src/reactor/memory/service.py`
- Create: `src/reactor/memory/langmem_jobs.py`
- Test: `tests/integration/test_rag_pgvector.py`
- Test: `tests/integration/test_memory_lifecycle.py`

- [x] **Step 1: Implement pgvector-backed retrieval**

Required behavior:

- tenant and ACL filters are applied before ranking
- vector and full-text results are merged with reciprocal rank fusion
- citations include source, document, chunk, checksum, and ACL proof

Progress:

- [x] tenant and ACL filters are applied before ranking at the Reactor retriever boundary
- [x] vector and keyword candidate lists merge with reciprocal rank fusion
- [x] citations include source, document, chunk, checksum, and ACL proof
- [x] SQLAlchemy/Postgres adapter builds pgvector and full-text candidate queries
- [x] repository execution maps pgvector/full-text rows into Reactor RAG candidates
- [x] repository execution test verifies vector/full-text query execution and RRF merge
- [x] admin RAG diagnostics API reports per-collection source/document/chunk counts,
  embedded chunk counts, and embedding coverage from tenant-scoped PostgreSQL RAG tables
- [x] policy RAG seed API ports legacy `/api/admin/rag/seed-policy` plus new
  `/v1/admin/rag/seed-policy`, preserving admin-only bulk semantics while writing
  policy source/document/chunk records through the Python PostgreSQL RAG sink
- [x] retrieval poisoning hardening labels ranked chunks as untrusted prompt data,
  preserves provenance/ACL proof metadata, and flags common prompt-injection and
  exfiltration directives without dropping the cited content
- [x] hardening test locks the employee-vs-executive-salary incident path so
  private executive documents are denied before vector/keyword ranking can surface them
- [x] Postgres RAG row mapping carries canonical document ACL and a stable ACL hash
  into internal candidate metadata for citation/proof while tool output redacts raw ACL fields
- [x] Docker/Postgres lifecycle integration test executes pgvector and full-text
  retrieval against `pgvector/pgvector:0.8.3-pg18-trixie`

- [x] **Step 2: Implement LangMem proposal flow**

Required behavior:

- memory extraction creates proposals, not direct sensitive facts
- promotion requires policy checks
- deletion tombstones facts and embeddings
- namespaces reject raw user-controlled tuples

Progress:

- [x] memory extraction creates proposal records, not active memory facts
- [x] LangMem extractor job boundary converts extracted candidates into proposals
- [x] promotion requires reviewer/reason policy checks and blocks sensitive candidates
- [x] deletion tombstones active memory and returns embedding deletion intent
- [x] namespaces reject raw user-controlled tuples
- [x] proposal/item persistence adapter writes these state transitions to Postgres
- [x] opt-in Docker/Postgres lifecycle integration test applies Alembic baseline and
  exercises proposal -> promotion -> embedding deletion/tombstone through
  `SqlAlchemyMemoryStore`
- [x] lifecycle integration test has live Postgres execution evidence in a
  Docker-enabled local environment

## Task 8: Auth, Admin, Slack, Scheduler, Eval, And Runtime APIs

**Files:**
- Create: `src/reactor/auth/`
- Create: `src/reactor/admin/`
- Create: `src/reactor/slack/`
- Create: `src/reactor/scheduler/`
- Create: `src/reactor/eval/`
- Create: `src/reactor/runtime_settings/`
- Test: `tests/integration/test_auth_api.py`
- Test: `tests/integration/test_admin_api.py`
- Test: `tests/integration/test_slack_api.py`
- Test: `tests/integration/test_scheduler_api.py`
- Test: `tests/integration/test_eval_api.py`

- [ ] **Step 1: Port API contracts route-by-route**

Required behavior:

- every retained route from `/tmp/reactor-route-inventory.txt` has a FastAPI route
- every route has Pydantic request/response models
- protected routes enforce auth/RBAC
- error responses are structured and tested

Progress:

- [x] runtime settings admin API exposes list/get/set/delete/refresh routes
- [x] runtime settings keeps legacy `/api/admin/settings` path and new `/v1/admin/settings` path
- [x] runtime settings routes use Pydantic request/response models
- [x] runtime settings routes fail closed behind an admin dependency and return structured 403/503/404 errors
- [x] auth/RBAC role model ports ADMIN, ADMIN_MANAGER, ADMIN_DEVELOPER, and USER scope rules
- [x] RBAC permission matrix ports the retained static role permissions
- [x] RBAC roles API exposes legacy `/api/admin/rbac/roles` and new `/v1/admin/rbac/roles`
- [x] runtime settings admin API now requires `settings:read` and `settings:write` permissions
- [x] scheduler jobs API exposes legacy `/api/scheduler/jobs` and new `/v1/scheduler/jobs`
- [x] scheduler API ports CRUD, tag filtering, executions, trigger, and dry-run boundaries
- [x] scheduler routes require `scheduler:read`/`scheduler:write`; ADMIN_MANAGER is denied
- [x] scheduler trigger/dry-run now execute through the same Worker boundary used by background execution
- [x] admin capabilities API ports legacy `/api/admin/capabilities` and new `/v1/admin/capabilities`
- [x] admin audit API ports list/export on legacy `/api/admin/audits` and new `/v1/admin/audits`
- [x] ops dashboard API ports legacy `/api/ops/*` and new `/v1/ops/*` foundation routes
- [x] admin routes enforce any-admin or `audit:read`/`audit:export` permissions
- [x] Slack bot admin API ports legacy `/api/admin/slack-bots` and new `/v1/admin/slack-bots`
- [x] proactive Slack channel API ports legacy `/api/proactive-channels` and new `/v1/proactive-channels`
- [x] Slack admin routes enforce full `slack:write` permission and mask bot/app tokens in responses
- [x] Slack prompt reload API ports legacy `/api/admin/slack/prompts/reload`
  plus new `/v1/admin/slack/prompts/reload`, preserving full-admin guard and
  reload response shape while routing through a Python prompt reload hook when
  configured
- [x] Slack Events API ingress ports legacy `/api/slack/events` and new `/v1/slack/events` with HMAC fail-close verification, URL challenge response, event id dedupe, retry headers, and durable enqueue
- [x] Slack request signing supports active plus previous signing secrets for safe rotation while preserving fail-close mismatch behavior
- [x] Slack slash command ingress ports legacy `/api/slack/commands` and new `/v1/slack/commands` with signed form parsing, invalid-payload ephemeral 400 ACK, processing ACK, idempotency key, and durable enqueue
- [x] Slack slash command worker maps durable payloads into LangGraph run execution metadata and posts response_url replies with user mention fallback semantics
- [x] Slack response_url delivery retries transient 5xx/network failures and does not retry 4xx client errors
- [x] Slack Web API `chat.postMessage` client posts slash-command questions and thread replies, with response_url fallback when channel/thread posting fails
- [x] Slack channel FAQ registration domain, validation, SQLAlchemy schema/store, UPSERT, list/get/delete, and ingest-result update foundations are ported
- [x] Slack channel FAQ admin CRUD API ports legacy `/api/admin/slack/channels/faq` and new `/v1/admin/slack/channels/faq` with full-admin guard, validation, and 404 behavior
- [x] Slack channel FAQ manual ingest API ports legacy `/api/admin/slack/channels/faq/{channelId}/ingest` and new `/v1/admin/slack/channels/faq/{channelId}/ingest` as a durable enqueue contract with immediate `running` status update
- [x] Slack channel FAQ ingest worker maps durable payloads, calls an ingestion service boundary, and records `running`/`ok`/`failed` registration status transitions with counts and bounded error text
- [x] Slack channel FAQ ingestion service fetches Slack `conversations.history`, filters noisy/system/bot messages, normalizes Slack markup for embedding/retrieval, and writes tenant-scoped FAQ documents into PostgreSQL RAG source/document/chunk tables
- [x] Slack channel FAQ fast-path responder ports mention/always/off trigger decisions, confidence threshold fallback, fail-open retrieval behavior, reply formatting, ALWAYS cooldown, and container wiring
- [x] Slack Events API callback worker maps durable event payloads, tries FAQ fast-path before LangGraph execution, posts FAQ hits to Slack threads, and falls back to agent execution on misses
- [x] Durable outbox dispatcher claims pending/retryable Slack outbox events with SKIP LOCKED, routes event/slash/FAQ ingest payloads to workers, marks successful dispatches, and records retryable/dead-letter failures
- [x] Slack channel FAQ admin diagnostics expose channel/overall stats, recent fast-path events, document feedback snapshots, responder probe/dry-run endpoints, and scheduler heartbeat status through FastAPI
- [x] Slack `reaction_added` events now map through the durable event worker and record FAQ answer document feedback for tracked fast-path replies
- [x] Slack Block Kit feedback button interactions now use signed HTTP ingress, durable outbox routing, tracked bot response lookup, feedback save, and in-thread/ephemeral ack behavior
- [x] Feedback persistence foundation ports the legacy feedback row contract into SQLAlchemy metadata, Alembic baseline migration, and an async PostgreSQL store used by Slack feedback handlers
- [x] Feedback API ports submit/list/get/review-update/unreviewed-count/delete on legacy `/api/feedback` and new `/v1/feedback` routes with admin guards and If-Match review versioning
- [x] Feedback stats/export/bulk-review APIs port legacy `/api/feedback/stats`, `/api/feedback/export`, and `/api/feedback/bulk-update` foundations with admin guards
- [x] Slack Socket Mode envelope core ports immediate ACK plus durable outbox normalization for `events_api`, `slash_commands`, and interactive/block action payloads
- [x] Slack Socket Mode SDK runner uses `slack-sdk`/`aiohttp`, validates xapp token configuration, registers SDK message listeners, sends ACK responses, and closes cleanly through the container factory
- [x] Slack Socket Mode lifecycle is opt-in through `REACTOR_SLACK_SOCKET_MODE_ENABLED`, starts from FastAPI lifespan, and closes before container shutdown
- [x] agent eval case API ports legacy `/api/admin/agent-eval/cases` and new `/v1/admin/agent-eval/cases`
- [x] agent eval result API ports legacy `/api/admin/agent-eval/results` and new `/v1/admin/agent-eval/results`
- [x] agent eval run-log API ports legacy `/api/admin/agent-eval/run-logs` and new `/v1/admin/agent-eval/run-logs`
- [x] agent eval promotion API ports legacy `/api/admin/agent-eval/cases/promote` and new `/v1/admin/agent-eval/cases/promote`
- [x] deterministic eval run API evaluates answer/tool/exposed-tool contracts and stores results
- [x] deterministic persisted-run API ports legacy `/api/admin/agent-eval/cases/{caseId}/evaluate-run/{runId}` and new `/v1/admin/agent-eval/cases/{caseId}/evaluate-run/{runId}`
- [x] agent eval replay API ports legacy `/api/admin/agent-eval/cases/{id}/replay` and new `/v1/admin/agent-eval/cases/{id}/replay`
- [x] replay executes the Python LangGraph run boundary with eval metadata and stores deterministic results
- [x] `llmJudge=true` stores an `llm_judge` tier result through a typed judge service contract
- [x] provider-backed LLM judge uses LangChain chat model execution when `REACTOR_EVAL_LLM_JUDGE_ENABLED=true`
- [x] LLM judge provider/model are configured by `REACTOR_EVAL_LLM_JUDGE_PROVIDER` and `REACTOR_EVAL_LLM_JUDGE_MODEL`
- [x] eval routes enforce full `eval:read`/`eval:write` permissions; ADMIN_MANAGER is denied
- [x] source-controlled eval regression suite fixture ports legacy `agent-eval/regression-suite.json`
- [x] eval regression suite runner reports missing run fixtures and deterministic assertion failures
- [x] trace grader ports safety, tool exposure, tool efficiency, grounding, and reliability dimensions
- [x] scenario matrix parser ports legacy defaults, tag filtering, matrix expansion, and template rendering
- [x] scenario matrix expectation evaluator ports status, success, toolsUsed, content, and JSON assertions
- [x] scenario matrix CLI restores `scripts/dev/validate-scenario-matrix.py` with `--validate-only` for CI-safe fixture checks
- [x] legacy `scripts/dev/scenarios` corpus is restored and expands under the Python CLI
- [x] CI hardening suite orchestration ports static gates, pytest suites, and scenario corpus validation into `scripts/ci/run-hardening-suite.py`
- [x] hardening suite runner supports tag selection, dry-run reports, fail-fast execution, and JSON artifacts
- [x] red-team corpus ports legacy probe-bank prompt-safety/tool-selection/output-safety cases into `tests/fixtures/redteam/probes.json`
- [x] red-team evaluator executes runtime `InputGuard`/`OutputGuard` boundaries and is wired into the hardening suite as `pytest-redteam`
- [x] token-cost admin API ports legacy `/api/admin/token-cost/by-session`, `/daily`, and `/top-expensive` plus new `/v1/admin/token-cost/*`
- [x] token-cost admin API enforces admin-only access, tenant-scoped reads, exact Decimal money serialization, and legacy session-prefix lookup
- [x] chat API returns deterministic `tokenUsage` while the foundation graph lacks real provider usage metadata
- [x] run completion records model token usage into the usage ledger as a fail-open observability hook
- [x] run completion increments Prometheus token and estimated-cost counters exposed by `/metrics`
- [x] OpenTelemetry tracing emits run lifecycle spans with tenant/run/thread/model/status/token attributes
- [x] LangGraph policy nodes emit OpenTelemetry spans at guard/context/model/approval/tool/output/hook boundaries
- [x] LangChain `AIMessage.usage_metadata` and OpenAI-style `response_metadata.token_usage` are extracted before deterministic token estimates
- [x] platform alert API ports legacy `/api/admin/platform/alerts/rules`, `/alerts`, `/alerts/{id}/resolve`, and `/alerts/evaluate` plus new `/v1/admin/platform/alerts/*`
- [x] SLO alert foundation supports static threshold evaluation, active-alert de-duplication, resolve lifecycle, and admin-only access
- [x] SLO alert evaluator ports baseline anomaly evaluation with mean/stddev/sample-count guards
- [x] SLO alert evaluator ports error-budget burn-rate evaluation with active-alert de-duplication

- [ ] **Step 2: Port stores schema-by-schema**

Required behavior:

- every retained store from `/tmp/reactor-store-inventory.txt` has a SQLAlchemy model/store
- Alembic renders the schema
- unit tests assert uniqueness, foreign keys, status constraints, and lifecycle transitions

Progress:

- [x] runtime settings table is modeled and rendered in Alembic baseline migration
- [x] runtime settings store supports set/find/list/delete with tenant-scoped keys
- [x] typed runtime settings resolver supports tenant override, global fallback, and typed defaults
- [x] auth users table and token revocation table are modeled and rendered in Alembic baseline migration
- [x] user store supports find-by-email, find-by-id, save, update, exists, and count contracts
- [x] JDBC-style token revocation store supports revoke, upsert refresh, expired cleanup, and is-revoked checks
- [x] JWT service creates and validates HS256 tokens with sub, jti, email, role, tenantId, iat, and exp claims
- [x] password auth uses salted PBKDF2-SHA256 hashing and constant-time verification
- [x] auth API exposes register/login/me/logout on legacy `/api/auth/*` and new `/v1/auth/*` paths
- [x] logout fails closed when token revocation persistence is unavailable or token lacks jti/exp
- [x] scheduled jobs and scheduled job executions are modeled and rendered in Alembic baseline
- [x] scheduler store supports list/find/save/update/delete/update-execution-result and Postgres-backed leases
- [x] scheduler execution store supports save/find-by-job/recent/delete-oldest lifecycle
- [x] scheduler dead-letter table/store captures retry-exhausted failures
- [x] scheduler worker enforces lease, timeout, retry, execution retention, dry-run no-mutation, and dead-letter behavior
- [x] auth API ports change-password with current-password verification and password hash update
- [x] auth API ports demo-login with ADMIN demo account creation/promotion guard
- [x] auth API ports IAM token exchange on legacy `/api/auth/exchange` and new `/v1/auth/exchange`
- [x] bearer-token principal dependency checks token revocation store and rejects revoked JWTs
- [x] security headers middleware ports no-sniff, frame deny, CSP, XSS disable, referrer, HSTS, permissions policy, and auth no-store
- [x] CORS middleware is opt-in and uses configured origins, methods, headers, credentials, and max-age
- [x] auth rate limiter protects login/register pre-auth attempts with 429 Retry-After and resets on success
- [x] IAM exchange service fetches and caches RS256 public keys, validates issuer, maps roles, auto-creates users, and issues Reactor HS256 JWTs
- [x] session API ports list/detail/export/delete on legacy `/api/sessions/*` and new `/v1/sessions/*`
- [x] session API enforces authenticated user context, tenant match, and admin override for cross-user reads
- [x] admin audit table/store are modeled in SQLAlchemy and rendered in Alembic baseline migration
- [x] admin audit list supports tenant, category/action filtering, actor masking, pagination, and CSV export audit recording
- [x] ops dashboard summarizes MCP, scheduler, recent scheduler executions, pending approvals, trust defaults, employee value defaults, and metric placeholders
- [x] Slack bot instance table/store are modeled in SQLAlchemy and rendered in Alembic baseline migration
- [x] Slack proactive channel table/store are modeled in SQLAlchemy and rendered in Alembic baseline migration
- [x] Slack channel FAQ registration table/store are modeled in SQLAlchemy and rendered in Alembic baseline migration
- [x] proactive channel add/remove records fail-open admin audit events
- [x] agent eval case/result tables are modeled in SQLAlchemy and rendered in Alembic baseline migration
- [x] agent eval case store supports save/find/list/delete with tenant, enabled, tag, and source-run metadata
- [x] agent eval result store supports save/list/delete-by-case with tenant, case, and tier filters
- [x] run store exposes tenant-scoped recent run records for eval run-log compatibility
- [x] deterministic eval model covers expected/forbidden answer text, tool use, exposed tools, exposure counts, agent type, model, score, and reasons
- [x] LLM judge parser accepts fenced JSON, infers pass from score, and fails closed on non-JSON responses
- [x] LLM judge prompt explicitly treats user input/final answer as data and requires JSON-only output
- [x] deterministic evaluator now checks `agentType` and `model` assertions instead of only counting them
- [x] model list API ports legacy `/api/models` and new `/v1/models` provider contract
- [x] user memory API ports get/update-fact/update-preference/delete on legacy `/api/user-memory/*` and new `/v1/user-memory/*`
- [x] user memory API preserves self-only access and blocks the legacy anonymous self-impersonation bypass
- [x] user memory store maps legacy facts/preferences onto active semantic memory items with supersede/tombstone lifecycle
- [x] chat API ports legacy `/api/chat` and new `/v1/chat` onto the Python LangGraph run service
- [x] chat stream API ports legacy `/api/chat/stream` and new `/v1/chat/stream` as SSE `message` and `done` events
- [x] chat API preserves web metadata, tenant/user context, sessionId-to-thread mapping, and media URL validation
- [x] multipart chat API ports legacy `/api/chat/multipart` and new `/v1/chat/multipart`
- [x] multipart chat enforces multimodal enablement, max file count, max file size, content type defaults, and media metadata forwarding
- [x] input guard admin API ports pipeline, settings, simulate, stage config, and reorder routes on legacy `/api/admin/input-guard/*` and new `/v1/admin/input-guard/*`
- [x] input guard admin API enforces guard RBAC permissions and persists runtime settings for guard/stage/reorder changes
- [x] input guard custom rule API ports list/get/create/update/delete on legacy `/api/admin/input-guard/rules/*` and new `/v1/admin/input-guard/rules/*`
- [x] input guard custom rule API validates pattern type, action, and regex syntax without leaking regex compiler internals
- [x] input guard rules table/store are modeled in SQLAlchemy and rendered in the Alembic baseline migration
- [x] model pricing domain preserves per-1M pricing semantics, cached-input pricing, reasoning-token pricing, and effective-date lookup
- [x] usage ledger domain records tenant/run/model token usage and produces by-session, daily, and top-expensive summaries
- [x] model pricing and usage ledger tables are modeled in SQLAlchemy and rendered in the Alembic baseline migration
- [x] usage ledger store compiles tenant-scoped PostgreSQL insert/list/daily/top-expensive queries and is exposed through the app container
- [x] platform pricing admin API ports legacy `/api/admin/platform/pricing`
  list/upsert plus new `/v1/admin/platform/pricing`, with manager-readable
  pricing rows, `settings:write` mutation guard, per-1M decimal string
  contract, model pricing validation, and `platform_pricing` audit events
- [x] platform health/vectorstore stats APIs port legacy
  `/api/admin/platform/health` and `/api/admin/platform/vectorstore/stats`
  plus new `/v1` paths, with admin-readable health fields, active alert
  counts, cache hit/miss counters, and PostgreSQL RAG document-count backing
- [x] doctor diagnostics API ports legacy `/api/admin/doctor` and
  `/api/admin/doctor/summary` plus new `/v1` paths, with admin-only access,
  JSON/text/markdown content negotiation, `X-Doctor-Status`, runtime settings
  checks, and RAG store document/chunk diagnostics
- [x] alert rule/instance SQLAlchemy tables are modeled and rendered in the Alembic baseline migration
- [x] alert rule store compiles PostgreSQL save/list/delete/active/resolve queries and is exposed through the app container
- [x] response cache admin API ports legacy `/api/admin/platform/cache/stats`,
  `/invalidate`, `/invalidate-key`, and `/invalidate-by-pattern` plus new
  `/v1/admin/platform/cache/*`, with admin guards, audit events, disabled-cache
  responses, in-memory single-node cache stats, key invalidation, wildcard
  invalidation, and full invalidation
- [x] trace and latency admin APIs port legacy `/api/admin/traces`,
  `/api/admin/traces/{traceId}/spans`, `/api/admin/metrics/latency/summary`,
  and `/api/admin/metrics/latency/timeseries` plus new `/v1` paths, backed by
  tenant-scoped run/event persistence with trace metadata, span timeline,
  percentile summary, and hourly latency series
- [x] platform tenant admin APIs port legacy `/api/admin/platform/tenants`
  list/get/create/suspend/activate plus new `/v1` paths, with ADMIN-only RBAC,
  slug/plan validation, plan-default quotas, audit events, SQLAlchemy tenant
  table/store, and Alembic baseline schema
- [x] tenant-scoped admin APIs port legacy `/api/admin/tenant/quota`,
  `/api/admin/tenant/slo`, and `/api/admin/tenant/alerts` plus new `/v1`
  paths, with current-tenant id/slug resolution, tenant-only alert filtering,
  current-month usage aggregation, quota percentages, and SLO defaults from
  tenant records
- [x] tenant dashboard APIs port legacy `/api/admin/tenant/overview`,
  `/usage`, `/quality`, `/tools`, and `/cost` plus new `/v1` paths, backed by
  tenant-scoped run metadata, usage ledger records, and tool invocation records
  for success rate, latency percentiles, channel/user distribution, tool ranking,
  and model cost aggregation
- [x] tenant CSV export APIs port legacy `/api/admin/tenant/export/executions`
  and `/api/admin/tenant/export/tools` plus new `/v1` paths, with ADMIN-only
  export permission, tenant-scoped run/tool filtering, legacy CSV headers,
  RFC 4180 escaping, execution tool counts, and tool error class export
- [x] eval dashboard APIs port legacy `/api/admin/evals/runs` and
  `/api/admin/evals/pass-rate` plus new `/v1` paths, with ADMIN-only eval
  read permission, tenant-scoped run/pass-rate grouping, and SQLAlchemy-backed
  result-store analytics
- [x] Slack activity APIs port legacy `/api/admin/slack-activity/channels` and
  `/api/admin/slack-activity/daily` plus new `/v1` paths, with ADMIN-only
  Slack permission, tenant-scoped Slack run filtering, usage-ledger token/cost
  aggregation, channel/user counts, latency averages, and daily success/failure
  counts
- [x] RAG analytics APIs port legacy `/api/admin/rag-analytics/status` and
  `/api/admin/rag-analytics/by-channel` plus new `/v1` paths, backed by the
  Python RAG source/document/chunk schema with `INGESTED` status and channel
  grouping from source metadata
- [x] conversation analytics APIs port legacy
  `/api/admin/conversation-analytics/by-channel`, `/failure-patterns`, and
  `/latency-distribution` plus new `/v1` paths, backed by tenant-scoped
  Python run metadata for channel success rates, error-class counts, and
  latency histogram buckets
- [x] follow-up suggestion stats API ports legacy
  `/api/admin/followup-suggestions/stats` plus new `/v1` path, with 1-168h
  window clamping, total impression/click CTR, category CTR ordering, and
  a Python in-memory `FollowupSuggestionStore` SPI foundation
- [x] users usage analytics APIs port legacy `/api/admin/users/usage/top`,
  `/cost`, `/daily`, and `/by-model` plus new `/v1` paths, backed by
  tenant-scoped run metadata and usage ledger joins for top users, per-user
  cost/latency, daily sessions, unique users, and model/provider breakdowns

## Task 9: Data Migration And Cutover

**Files:**
- Create: `src/reactor/migration/export.py`
- Create: `src/reactor/migration/import_.py` (`import` is a Python keyword)
- Create: `src/reactor/migration/parity.py`
- Create: `src/reactor/migration/rollback.py`
- Create: `src/reactor/migration/cutover.py`
- Create: `docs/migration/cutover-rollback-runbook.md`
- Test: `tests/integration/test_data_migration.py`
- Test: `tests/unit/test_migration_cutover.py`

- [ ] **Step 1: Export retained data to NDJSON**

Required behavior:

- export readers are idempotent
- every row includes source table, source primary key, checksum, and exported timestamp
- skipped data is recorded with a reason

Progress:

- [x] canonical NDJSON row export records source table, source primary key, payload checksum, and exported timestamp
- [x] export source reader composition flattens async retained-data readers in deterministic configured order
- [x] skipped legacy rows are exported with an explicit reason
- [x] agent run and run event source readers export DB rows into canonical migration `LegacyRow` payloads with run ownership, checkpoint namespace, status, metadata, responses, errors, event sequence, payload, and timestamps preserved
- [x] run queue, dead-letter, idempotency, outbox, and inbox source readers export DB rows into canonical migration `LegacyRow` payloads with lease state, fencing tokens, retry counters, idempotency status, event payloads, errors, and timestamps preserved
- [x] runtime settings source reader exports DB rows into canonical migration `LegacyRow` payloads
- [x] prompt template/version/release source readers are exposed through the app
  container so source-controlled prompt data participates in retained-data export
- [x] Prompt Lab experiment/trial/report source readers are exposed through the app
  container so optimization/evaluation artifacts participate in retained-data export
- [x] persona, agent spec, and intent definition source readers are exposed through
  the app container so selected agent behavior/config data participates in retained-data export
- [x] Slack bot source reader exports DB rows into canonical migration `LegacyRow` payloads with tenant/name/id ordering
- [x] Slack proactive channel source reader exports DB rows into canonical migration `LegacyRow` payloads with tenant/channel ordering
- [x] Slack FAQ registration source reader exports DB rows into canonical migration `LegacyRow` payloads with ingest status/counter timestamps
- [x] feedback source reader exports DB rows into canonical migration `LegacyRow` payloads with review status, tags, reviewer, and version metadata
- [x] eval case/result source readers export DB rows into canonical migration `LegacyRow` payloads with assertion lists, score gates, tiers, reasons, and timestamps
- [x] scheduler job/execution/dead-letter source readers export DB rows into canonical migration `LegacyRow` payloads with schedule definitions, last status, execution records, and dead-letter reasons
- [x] model pricing and usage ledger source readers export DB rows into canonical migration `LegacyRow` payloads with JSON-safe decimal strings
- [x] alert rule/instance source readers export DB rows into canonical migration `LegacyRow` payloads with tenant/platform scope, severity, status, and resolution metadata
- [x] auth user/token revocation source readers export DB rows into canonical migration `LegacyRow` payloads with password hashes, roles, expiry, and revoked-at timestamps preserved
- [x] input/output guard rule and output guard audit source readers export DB rows into canonical migration `LegacyRow` payloads with policy priority, enabled state, replacement, actor, detail, and timestamps preserved
- [x] admin audit source reader exports DB rows into canonical migration `LegacyRow` payloads with tenant, category, action, actor, resource, detail, and timestamp preserved
- [x] tool catalog, pending approval, and tool invocation source readers export DB rows into canonical migration `LegacyRow` payloads with tool schemas, approval decision state, idempotency keys, checksums, payloads, and timestamps preserved
- [x] MCP server, server status, tool snapshot, and access policy source readers export DB rows into canonical migration `LegacyRow` payloads with transport config, reconnect policy, protocol state, tool schemas, risk levels, and access lists preserved
- [x] A2A peer agent, agent card, task, task event, push subscription, and access policy source readers export DB rows into canonical migration `LegacyRow` payloads with protocol cards, task context, idempotency keys, events, push destinations, permissions, and timestamps preserved
- [x] RAG source, document, and chunk source readers export DB rows into canonical migration `LegacyRow` payloads with source metadata, ACL, embeddings, checksums, and timestamps preserved
- [x] RAG ingestion candidate source reader is exposed through the app container so
  captured-but-not-yet-ingested review records participate in retained-data export
- [x] memory namespace, item, embedding, and proposal source readers export DB rows into canonical migration `LegacyRow` payloads with ownership scope, lifecycle status, validity windows, embeddings, extraction metadata, and timestamps preserved
- [x] input guard metric source reader exports retained `metric_guard_events` rows
  with guard stage, category, reason, output-guard flag, action, tenant/user, and
  event time preserved
- [x] all implemented migration source readers are exposed through the app container
  for full backup DB extraction

- [ ] **Step 2: Import into Python schema**

Required behavior:

- import jobs are idempotent
- count/checksum/sample parity is reported
- rollback snapshots are retained until burn-in is complete

Progress:

- [x] import sink contract de-duplicates by source table/source primary key/checksum
- [x] PostgreSQL migration import ledger table/store preserves imported batch/source/checksum/payload rows idempotently
- [x] agent run and run event target writers restore retained execution history rows through Python persistence records while preserving run IDs, ownership, checkpoint namespace, status, metadata, responses, errors, event sequence, payload, and timestamps
- [x] run queue, dead-letter, idempotency, outbox, and inbox target writers restore retained durable execution/coordination rows through Python persistence records while preserving lease state, fencing tokens, retry counters, idempotency status, event payloads, errors, and timestamps
- [x] auth user/token revocation target writers restore retained identity rows and preserve token revocation timestamps
- [x] input/output guard rule and output guard audit target writers restore retained governance policy rows and audit events through the Python domain records
- [x] admin audit target writer restores retained operational audit rows through the Python audit store with tenant scoping preserved
- [x] tool catalog, pending approval, and tool invocation target writers restore retained execution control rows through Python persistence records while preserving ids, schemas, decision metadata, idempotency keys, payload checksums, and timestamps
- [x] MCP server, server status, tool snapshot, and access policy target writers restore retained MCP registry/control-plane rows through Python persistence records while preserving protocol, reconnect, schema, risk, and authorization metadata
- [x] A2A peer agent, agent card, task, task event, push subscription, and access policy target writers restore retained multi-agent protocol rows through Python persistence records while preserving protocol cards, task context, event sequence, push destinations, permissions, and timestamps
- [x] RAG source, document, and chunk target writers restore retained pgvector RAG rows through Python persistence records while preserving IDs, source metadata, document ACL, embeddings, checksums, and timestamps
- [x] memory namespace, item, embedding, and proposal target writers restore retained memory rows through Python persistence records while preserving IDs, ownership scope, lifecycle status, validity windows, embeddings, extraction metadata, and timestamps
- [x] parity report compares per-table counts, missing/extra primary keys, checksum mismatches, and deterministic samples
- [x] rollback snapshot writer records current target rows before import
- [x] rollback snapshot table/store persists target table/primary key/checksum/payload snapshots before import
- [x] import target dispatcher routes imported rows to registered target writers by source table and fail-fast rejects unregistered tables
- [x] runtime settings target writer maps imported rows into validated `RuntimeSettingUpdate` records
- [x] Slack bot target writer maps imported rows into validated `SlackBotInstanceRecord` records
- [x] Slack proactive channel target writer maps imported rows into validated `ProactiveChannelRecord` records while preserving `added_at`
- [x] Slack FAQ registration target writer maps imported rows into validated `ChannelFaqRegistration` records with enum and ingest metadata restoration
- [x] feedback target writer maps imported rows into validated `Feedback` records with rating enum and review metadata restoration
- [x] eval case/result target writers map imported rows into validated `AgentEvalCaseRecord` and `AgentEvalStoredResultRecord` records
- [x] scheduler job/execution/dead-letter target writers map imported rows into validated scheduler domain records with job/status enum restoration
- [x] model pricing and usage ledger target writers restore decimal money fields into validated observability records
- [x] alert rule/instance target writers restore alert type, severity, status, scope, and resolution metadata into validated observability records
- [x] `reactor-migration-report` staging command writes JSON count/checksum/sample parity reports from exported/imported NDJSON
- [x] `reactor-migration-cutover` fails production cutover on parity mismatch, skipped rows, empty imports, and missing rollback snapshot tables unless explicitly allowed
- [x] cutover rollback runbook defines freeze, export, staging import, parity, readiness, production import, burn-in, no-go gates, and rollback procedure
- [x] app container builds a concrete migration target dispatcher for all DB-backed,
  metric-buffer, RAG, memory, MCP, A2A, prompt, guard, auth, scheduler, and audit target writers
- [x] dress rehearsal can apply imported rows through the target dispatcher before
  recording the import ledger, so target-write failures do not get marked imported
- [x] Docker/Postgres dress rehearsal uses the app container target dispatcher to
  write imported runtime settings into the Python schema while preserving import ledger idempotency
- [x] Docker/Postgres dress rehearsal fixture covers tenant, runtime setting, and
  Slack bot target writes in one batch with rollback table coverage and idempotent rerun
- [x] Docker/Postgres dress rehearsal fixture now includes RAG source, document, and
  pgvector chunk rows with ACL and chunk metadata preserved through target writes
- [x] Docker/Postgres dress rehearsal fixture includes memory namespace, item,
  embedding, and proposal rows with lifecycle, scope, vector, and extraction
  metadata preserved through target writes
- [x] Docker/Postgres dress rehearsal fixture includes MCP server, server status,
  tool snapshot, and access policy rows with transport, protocol, reconnect,
  schema, risk, and authorization metadata preserved through target writes
- [x] Docker/Postgres dress rehearsal fixture includes A2A peer, agent card, task,
  task event, push subscription, and access policy rows with protocol cards,
  idempotency keys, task context, events, push destinations, and permissions
  preserved through target writes
- [x] Docker/Postgres dress rehearsal fixture includes prompt template, prompt
  version, prompt release, persona, agent spec, and intent definition rows with
  policy text, examples, release metadata, persona defaults, tool bindings, and
  routing metadata preserved through target writes
- [x] Docker/Postgres dress rehearsal fixture includes agent run, run event,
  run queue, dead letter, idempotency, outbox, and inbox rows with checkpoint
  namespace, event payloads, leases, fencing tokens, idempotency responses,
  and side-effect envelopes preserved through target writes
- [x] Docker/Postgres dress rehearsal fixture includes auth user, user identity,
  token revocation, input guard rule, output guard rule, output guard audit, and
  admin audit rows with credentials, external subjects, revocation timestamps,
  guard policy, audit actors, resources, and tenant scope preserved through
  target writes
- [x] Docker/Postgres dress rehearsal fixture includes tool catalog, pending
  approval, and tool invocation rows with schemas, risk, approval decision
  metadata, idempotency keys, checksums, payloads, and side-effect results
  preserved through target writes
- [x] Docker/Postgres dress rehearsal fixture includes feedback, eval case,
  eval result, scheduled job, scheduled execution, and scheduled dead-letter
  rows with review state, assertions, scores, cron definitions, execution
  results, and failure envelopes preserved through target writes
- [x] Docker/Postgres dress rehearsal fixture includes model pricing, usage
  ledger, alert rule, and alert instance rows with decimal prices, token/cost
  usage, threshold policy, alert status, metric values, and acknowledgements
  preserved through target writes
- [x] Docker/Postgres dress rehearsal fixture includes Prompt Lab experiment,
  trial, report, and RAG ingestion candidate rows with evaluation config,
  trial metrics, recommendation summaries, and review/ingestion status
  preserved through target writes
- [x] Docker/Postgres dress rehearsal fixture includes tenant SLO config and
  legacy metric agent execution rows with tenant SLO/metadata updates and
  metric ingestion buffer publication preserved through target writes
- [x] Docker/Postgres dress rehearsal fixture includes remaining legacy metric
  session, span, audit, quota, HITL, tool-call, MCP-health, and eval-result
  rows with one-shot metric ingestion buffer publication preserved through
  idempotent target writes
- [ ] additional target-specific writers and full backup DB dress rehearsal remain pending

## Task 10: Final Verification

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `docs/migration/full-replatform-parity-ledger.md`

- [ ] **Step 1: Run full local verification**

Run:

```bash
uv lock --check
uv run ruff format --check
uv run ruff check
uv run pyright
uv run pytest
uv run alembic upgrade head --sql >/tmp/reactor-alembic.sql
```

Expected: all checks pass.

- [ ] **Step 2: Run smoke and parity checks**

Run:

```bash
uv run python scripts/dev/smoke-health.py
```

Expected:

- `/healthz` returns 200
- `/readyz` returns 200 when configured dependencies are healthy
- retained API parity tests pass
- no server process remains after smoke

Progress:

- [x] repeatable uvicorn health/readiness smoke script starts `reactor.main:app`,
  verifies `/healthz` and `/readyz`, and terminates the subprocess with test
  coverage

- [ ] **Step 3: Mark goal complete only after ledger is verified**

Required behavior:

- every retained feature area in `docs/migration/full-replatform-parity-ledger.md` is `verified`
- route inventory and store inventory have no unported retained rows
- hardening and integration suites pass
- data migration parity report passes

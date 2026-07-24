# Reactor Python/LangGraph Retained Capability Ledger

This ledger is the completion gate for the Python/LangGraph replatform. It tracks
retained product capabilities, not a line-by-line Spring/Kotlin clone. The migration
is not complete until every retained capability below has a Python implementation,
tests, and runtime verification aligned with
`docs/architecture/python-langgraph-replatform-spec.md`.

Retention rule:

- The backup Spring/Kotlin implementation is source inventory, not the target
  architecture.
- Old features, routes, tables, settings, and packages must be classified as
  `keep`, `remap`, `drop`, or `defer` before implementation work.
- Keep or remap only capabilities needed for active users, security, audit/legal
  retention, billing, approved memories, prompts/evals, tool policy, RAG, or
  production operations.
- Drop implementation artifacts, stale compatibility paths, transient caches,
  framework-era wrappers, and empty packages when LangChain, LangGraph, LangSmith,
  or the new product model makes them unnecessary.
- Prefer framework-native LangChain/LangGraph/LangSmith behavior over custom code
  unless Reactor policy, tenancy, ACL, audit, idempotency, cost, or compliance needs
  a product-owned boundary.

## Current Audit Snapshot

- Backup source tag: `spring-v6.99.0`
- Working branch: `codex/python-langgraph-migration`
- Backup implementation surface:
  - main source files under `modules/*/src/main`: 1,054
  - test files under `modules/*/src/test`: 681
  - controller route annotations: 332
  - store interfaces / store implementations: 155
- Current Python implementation has reached `ported` or better for every retained
  capability under the local automation policy below. Legacy Spring data cutover is
  intentionally excluded from the Python 2.0 release gate because Python data will
  be accumulated fresh. Migration and dress-rehearsal tooling remains available for
  optional operator validation, not for mandatory release readiness.
- Latest local automation gate:
  - `uv lock --check`: pass
  - `ruff check`: pass
  - `ruff format --check`: pass
  - `pyright`: pass
  - `pytest`: 1,231 passed, 22 Docker/Postgres-gated tests skipped
  - `REACTOR_TEST_POSTGRES=1 pytest tests/integration/*postgres*.py`: 22 passed
  - `reactor-release-smoke-run --plan reports/release/release-smoke-plan.local.json
    --report-file reports/release/local-contract-smoke-report.json`: 5 local
    contract smoke steps passed, 2 manual release evidence steps skipped
  - Optional: `reactor-migration-dress-rehearsal --required-table-file
    docs/migration/retained-table-manifest.txt`: retained-table manifest contract
    smoke requires 70 tables; sample-only rehearsal report correctly fails with
    69 missing required tables in
    `reports/release/dress-rehearsal-manifest-readiness.json`
  - `reactor-live-provider-smoke --output
    reports/release/live-provider-runtime-smoke.json`: writes a scoped live provider
    smoke report through LangChain `init_chat_model` using the configured default
    provider/model unless overridden; missing provider API-key env produces
    `status: "skipped"` and must not be converted into release evidence.
  - `reactor-live-provider-smoke --provider ollama --model gemma4:12b --output
    reports/release/local-ollama-provider-smoke.json`: local LangChain/Ollama
    provider smoke passed against a running local Ollama server with no cloud
    provider API key.
  - Docker-backed local API smoke passed with PostgreSQL/pgvector on host port
    `55432`, Alembic upgraded to head, `REACTOR_DEFAULT_MODEL_PROVIDER=ollama`,
    `REACTOR_DEFAULT_MODEL=gemma4:12b`, and `/api/chat` returning `pong` through
    the LangGraph/FastAPI path.
  - `reactor-local-api-chat-smoke --provider ollama --model gemma4:12b --output
    reports/release/local-api-chat-smoke.json`: repeatable local API smoke for
    health, readiness, and `/api/chat` through the running FastAPI/LangGraph path.
  - `reactor-release-smoke-run --plan reports/release/release-smoke-plan.local.json
    --report-file reports/release/local-ollama-release-smoke-run.json --verified-at
    2026-06-28T00:00:00Z --evidence-output
    reports/release/local-ollama-release-evidence.json`: with
    `REACTOR_RELEASE_SMOKE_PROVIDER=ollama`,
    `REACTOR_RELEASE_SMOKE_MODEL=gemma4:12b`, and
    `REACTOR_RELEASE_SMOKE_TRACE_EXPORTER=console`, provider/runtime,
    scheduled/background provider, and backend/provider integration gates passed
    and were promoted to scoped live evidence.
  - `reactor-live-slack-smoke --output
    reports/live-slack-workspace-smoke.json`: writes a scoped live Slack smoke
    report by verifying the existing Slack request signature path, calling Slack
    `auth.test`, optionally checking `conversations.info`, opening Socket Mode via
    `apps.connections.open` when `REACTOR_SLACK_APP_TOKEN` is configured, and
    posting a root message plus thread reply to `REACTOR_SLACK_CHANNEL_ID`, while
    also verifying the local approval Block Kit contract can be parsed by the
    durable approval interaction handler before the live smoke is accepted.
    Reports do not persist Slack tokens, Socket Mode URLs, or message timestamps;
    missing `conversations.info` scope is recorded as skipped when thread posting
    still proves channel access. Missing Slack env produces `status: "skipped"`
    and must not be converted into release evidence.
  - Slack gateway policy now follows the Hermes/OpenClaw safety baseline for
    channel events: channel messages require an explicit app mention by default,
    DMs are accepted without a mention, configured free-response channels may
    accept unmentioned messages, and optional channel/user allowlists drop
    unauthorized events before rate limit, FAQ, or agent execution. Bot-origin
    Slack message events are parsed without failing the durable outbox and are
    dropped before policy, rate limit, FAQ, or agent execution to prevent
    bot-loop amplification. Slack event workers record successful same-process
    bot participation in a thread and also recover participation after restart
    through tenant-scoped Slack `agent_runs.thread_id` lookup, allowing later
    unmentioned replies in that thread while still enforcing channel and user
    allowlists. First-entry app mentions inside an existing Slack thread hydrate
    prior thread replies through `conversations.replies` and prepend bounded
    thread context to the LangGraph agent input without changing the FAQ query.
    Slack Assistant lifecycle events now persist assistant thread context in the
    worker store, attach that context to LangGraph run metadata for matching
    assistant DM thread messages, and drive best-effort
    `assistant.threads.setStatus` updates around agent execution. Native Slack
    approval requests from slash commands and channel/app-mention events now
    persist pending approval rows and render Block Kit approve/reject buttons in
    the active thread; button interactions route through the durable Slack
    interaction outbox worker, persist `ApprovalDecision` rows, and resume the
    matching LangGraph run through the stored thread/checkpoint namespace, then
    post approved resume output back into the original Slack root thread instead
    of the intermediate approval-button message while replacing the original
    approval-button message with a decided or expired status block.
    Malformed approval button payloads are now fail-closed without persisting a
    decision or resuming a run, while Slack response-url replacement failures
    remain non-blocking after the durable approval decision/resume path.
    Remaining product-depth gaps versus mature Slack agent connectors are live
    QA scenarios for mention gating, allowlist blocking, thread follow-up,
    approval button UX, and richer interaction handling.
  - `reactor-live-a2a-peer-smoke --output
    reports/release/live-peer-network-interoperability-smoke.json`: writes a scoped
    live A2A peer smoke report by checking the deployed agent card and A2A
    diagnostics over HTTP; passing live evidence also requires
    `REACTOR_A2A_API_KEY` so the smoke can probe task creation with redacted
    failures.
  - `reactor-live-backend-provider-smoke --output
    reports/release/live-backend-provider-integration.json`: writes a scoped live
    backend/provider integration report by enabling Reactor tracing settings and
    invoking the configured LangChain provider inside a Reactor trace span;
    missing provider or LangSmith env produces `status: "skipped"`.
  - Optional: `reactor-dress-api-smoke --output reports/release/full-backup-db-api-smoke.json`:
    writes a scoped dress-rehearsal API smoke report by checking `/healthz`,
    `/readyz`, and admin capabilities against `REACTOR_API_BASE_URL` with
    `REACTOR_API_KEY`.
- Release-readiness tracking command:
  - `reactor-replatform-readiness --output /path/to/replatform-readiness.json`
    exits non-zero while live/deferred release gates remain.
  - Provide `--evidence /path/to/release-evidence.json` to satisfy deferred gates.
    The evidence file is a JSON object keyed by gate code, with `status: "passed"`,
    required `scope`, `evidence_uri`, and `verified_at`. Current Python 2.0 release
    gates require `scope: "live"` because legacy data cutover is excluded.
    Local-only smoke evidence must not close a live release gate.
  - Build that file from one or more smoke report JSON files with
    `reactor-release-evidence --scope <live|dress_rehearsal> --verified-at <timestamp> --gate-result
    <gate_code>=<smoke_report_path>=<evidence_uri> --output
    /path/to/release-evidence.json`. A smoke report is accepted as passed only when
    it contains `ok: true` or `status: "passed"`.
  - DB+API dress rehearsal evidence is optional operator evidence only; it is not
    part of the Python 2.0 release gate.
  - Or build live evidence directly from the release smoke run report with
    `reactor-release-evidence --verified-at <timestamp> --smoke-run
    /path/to/smoke-run.json --output /path/to/release-evidence.json`. Only passed
    steps with `release_gate_closer: true` are promoted; skipped/manual and
    local-contract steps are ignored.
  - Use `reactor-release-evidence --input /path/to/existing-evidence.json ...`
    to merge additional live gate results into the same evidence
    file without hand-editing JSON.
  - The generated readiness JSON includes `release_evidence_requirements` with
    one suggested command and expected evidence shape per remaining live gate.
  - Generate an execution plan from readiness output with
    `reactor-release-smoke-plan --readiness /path/to/replatform-readiness.json --output
    /path/to/release-smoke-plan.json`. The plan separates executable live gate
    closers from local-contract checks.
    Each release-gate step includes `required_env` metadata with required variables,
    supported any-of alternatives, and optional variables so operators can resolve
    missing live configuration before running the smoke plan.
    Set `REACTOR_RELEASE_SMOKE_PROVIDER` and `REACTOR_RELEASE_SMOKE_MODEL` to add
    `--provider` and `--model` to provider smoke commands. Set
    `REACTOR_RELEASE_SMOKE_TRACE_EXPORTER` to override backend/provider smoke
    tracing, for example `console` for local Ollama validation without LangSmith
    credentials.
    Optional full-backup dress rehearsal steps become automated only when these environment
    variables are present: `REACTOR_FULL_BACKUP_EXPORTED_NDJSON`,
    `REACTOR_FULL_BACKUP_ROLLBACK_NDJSON`,
    `REACTOR_FULL_BACKUP_RETAINED_TABLE_MANIFEST`,
    `REACTOR_FULL_BACKUP_DRESS_IMPORTED_OUTPUT`,
    `REACTOR_FULL_BACKUP_DRESS_READINESS_OUTPUT`, and
    `REACTOR_FULL_BACKUP_DRESS_BATCH_ID`.
    The DB+API dress rehearsal step additionally requires
    `REACTOR_API_BASE_URL` and `REACTOR_API_KEY`; it writes the API smoke report
    to `REACTOR_FULL_BACKUP_API_SMOKE_OUTPUT` when set, otherwise to
    `reports/release/full-backup-db-api-smoke.json`.
    Automated local contract smoke steps carry `evidence_scope: "local_contract"`
    and `release_gate_closer: false`; they must not be converted into live release
    evidence.
    The current local live evidence file is
    `reports/release/local-live-release-evidence.json`; it satisfies provider,
    backend/provider, A2A peer-network, and Slack workspace gates when their live
    smoke reports are current.
  - Run automated local contract smoke steps with
    `reactor-release-smoke-run --plan /path/to/release-smoke-plan.json --report-file
    /path/to/local-contract-smoke-report.json`. Manual live/staging steps are
    skipped in that report and still require scoped release evidence.
    Add `--preflight-file /path/to/preflight.json --preflight-only` to check
    required, any-of, and optional environment variables without executing live
    commands. Add `--preflight-env-template /path/to/preflight.env` to emit a
    secret-free `.env` template containing only missing variable names and blank
    values. Add repeatable `--env-file /path/to/preflight.env` after filling the
    template to re-run preflight checks and execute smoke commands with those
    values. Values loaded from `--env-file` are redacted from smoke-run
    stdout/stderr before reports are written.
    Add `--verified-at <timestamp> --evidence-output /path/to/release-evidence.json`
    to write release evidence for passed gate-closing steps in the same run; add
    repeatable `--evidence-input /path/to/existing-evidence.json` to accumulate
    evidence across multiple live/dress smoke runs.
  - Add `--allow-deferred-release-gates` to confirm local automation readiness
    without claiming production release readiness.
- Latest normalized legacy route parity pass: 0 actionable missing routes remain after
  porting admin session management, legacy MCP/approval aliases, and MCP server
  management detail/update/delete/connect/disconnect APIs plus MCP access-policy
  management APIs, DB-backed dynamic tool-policy APIs, and platform tenant analytics.
  The remaining scheduler inventory entries are duplicate legacy controller/stub
  base-path artifacts; the Python scheduler API and stub behavior are already covered
  by `tests/integration/test_scheduler_api.py`.

## Route And Store Inventory Summary

Detailed unclassified inventories:

- `docs/migration/route-inventory.md`
- `docs/migration/store-inventory.md`
- `docs/migration/module-architecture-review.md`

Routes by module:

| Module | Route Annotations |
| --- | ---: |
| `modules/web` | 212 |
| `modules/admin` | 96 |
| `modules/slack` | 23 |
| `modules/autoconfigure` | 1 |

Stores by module:

| Module | Store Entries |
| --- | ---: |
| `modules/api` | 20 |
| `modules/memory` | 18 |
| `modules/autoconfigure` | 15 |
| `modules/admin` | 12 |
| `modules/observability` | 11 |
| `modules/auth` | 10 |
| `modules/mcp` | 9 |
| `modules/guard` | 9 |
| `modules/scheduler` | 8 |
| `modules/promptlab` | 8 |
| `modules/rag` | 6 |
| `modules/prompts` | 6 |
| `modules/agent` | 6 |
| `modules/tool` | 5 |
| `modules/slack` | 4 |
| `modules/approval` | 4 |
| `modules/eval` | 2 |
| `modules/cache` | 2 |

## Capability Status Legend

- `not_started`: no Python equivalent exists.
- `foundation`: schema, DTO, or minimal API exists, but behavior is incomplete.
- `in_progress`: retained behavior is being implemented or remapped with tests.
- `ported`: Python behavior and tests exist.
- `verified`: focused tests, full checks, and smoke/integration evidence exist.

External live verification policy:

- Live provider smoke tests, live Slack workspace smoke tests, and full backup
  database/API dress rehearsals are release-readiness gates, not blockers for
  marking a retained capability `ported`.
- A retained capability can be `ported` when the Python implementation is wired to
  the selected framework/runtime boundary and has focused unit, integration, or
  Docker-backed contract tests that can be run locally or in controlled staging.
- A retained capability becomes `verified` only after the wider static/test gate
  and any required live/staging evidence have been captured.

## Feature Areas

| Area | Backup Scope | Current Python Status | Required Completion Gate |
| --- | --- | --- | --- |
| Agent graph/runtime | ReAct, streaming, plan-execute, retry, timeout, checkpoints, fallback | verified | LangGraph graph implements guard -> context -> model -> approval -> tools -> output guard -> hooks, profile factories inject prompt/model/tool/max-call defaults with request overrides, graph model node can invoke an injected LangChain chat model while preserving deterministic no-key fallback for local/CI tests, AppContainer-built graph runtimes can receive LangChain chat models through the provider factory boundary, approval gate supports LangGraph `interrupt()` plus `Command(resume=...)` when checkpointing is enabled, checkpoint-resumed pending tool specs are reconstructed from safe structured payloads instead of requiring live Python objects, RunService prevents user metadata from overriding the persisted checkpoint namespace, `/api/chat/stream` uses LangGraph `astream_events(..., version="v2")` through RunService and emits persisted `run.stream.*` SSE events while preserving response-format and response-schema state, projecting both graph state `on_chain_stream` chunks and native chat-model `on_chat_model_stream` chunks into the same filtered token contract, rejecting unknown runtime values before graph execution, emitting sanitized SSE error events without raw exception detail, recording final run completion and usage ledger data, exposing tenant/user-scoped `/v1/runs/{run_id}` detail plus `/resume` and `/cancel` APIs backed by stored thread/checkpoint identity and `run.resumed`/`run.cancelled` audit events, publishing optional Redis-backed lifecycle fanout only after durable resume/cancel/approval audit events with fail-open publisher behavior, and exposing `/v1/runs/{run_id}/stream-events` replay filtered by stream event type and sequence after run tenant/user ownership checks plus tenant-scoped event store queries, LangChain-native `runtime=langchain_agent` opt-in harness uses `create_agent` with model/tool call limits, retries, PII, HITL middleware, concrete `responseSchema` structured-output schema passthrough, Pydantic/dataclass structured-response serialization, enabled DB/builtin model-facing tools only, model-facing-tool-only integration context rendering, native `astream_events(..., version="v2")` streaming through the same persisted `run.stream.*` contract, shared run timeout policy, and the same LangGraph checkpointer passed through product RunService/container surfaces while preserving run/thread/usage contracts, with checkpoint resume tests ported; live provider/runtime smoke deferred to release-readiness verification |
| Prompt/context/model governance | system prompt builder, context budgeter, tool forcing rules, prompt drift, model routing | verified | versioned graph profiles, governed context manifest ordering, LangChain Core `trim_messages` for message-count trimming with Reactor tool-call pair preservation, PromptRelease-based system prompt assembly through LangChain `ChatPromptTemplate` with rendered checksum, model router, LangChain standard chat model factory boundary for provider swaps, prompt release hashes, prompt cache keys, drift tests, prompt template/version/release persistence, API/admin prompt template-version-release management, legacy `/api/prompt-templates` CRUD plus DRAFT/ACTIVE/ARCHIVED version lifecycle compatibility API, PromptLab experiment CRUD/status/trials/report/activate APIs, feedback-driven analyze/auto-optimize service with candidate prompt version generation, PostgreSQL tables/store, Docker-backed PostgreSQL API proof for PromptLab experiment run/status/trial/report/activate/delete persistence and cascade cleanup, LangGraph RunService-backed trial execution/report generation service, and provider-backed PromptLab LLM judge tier using LangChain structured output when available, persona CRUD/default-selection API and PostgreSQL table, released prompt lookup, graph-profile tool forcing policy, and `/api/admin/models` plus `/api/models` model registry contracts backed by settings/Postgres model pricing ported |
| Tool runtime | exposure policy, argument parser, orchestration, parallel calls, idempotency, result cache, approval | verified | Pydantic tool contracts, execution admission, sanitizer, audit, idempotency keys, per-tool timeout wrapper, LangGraph result cache hit/miss handling, checkpointed approval interrupt/resume path with principal-tenant-scoped approval create/list/decision APIs, LangChain `StructuredTool` adapter for `runtime=langchain_agent` that preserves Reactor admission/timeout/idempotency/result contracts, RunService supplies tenant enabled DB ToolSpec catalog into the LangChain-native harness, admin tool catalog API parity, runtime-settings-backed dynamic tool-policy API parity, admin tool call history/ranking APIs, admin tool outcome stats/accuracy APIs, reserved model-facing Slack and SlackMCP namespaces fail closed unless an explicit handler is registered, parallel tool orchestration with preserved result/message order, and hardening tests ported |
| Guards/hooks/output filters | input guard, output guard, intent registry, hooks, response filters, structured repair | verified | deterministic guard pipeline, input guard stats compatibility API, input guard runtime metric sink, prompt-injection hardening corpus, Docker-backed PostgreSQL API proof for intent definition CRUD persistence, intent definition CRUD API and PostgreSQL table, rule-based intent resolution wired into LangGraph with fail-open behavior and dynamic GraphProfile selection, Docker-backed PostgreSQL graph proof for intent registry dynamic GraphProfile selection and disabled-intent exclusion, Docker-backed PostgreSQL graph proof for input guard custom keyword/regex block rules with tenant isolation and disabled/warn exclusions, fail-open response filter chain with max-length truncation, Slack raw user-id masking, internal stack/brand/org masking wired after output guard plus create/resume non-streaming, persisted streaming, emitted streaming token, and non-token streaming tool payload RunService paths, and graph deterministic fallback/system-policy text kept vendor/company/old-stack neutral before filters run, output boundary max/min enforcement with WARN/RETRY_ONCE/FAIL policies, retry-once final-output expansion metadata, and violation recording wired into LangGraph final output, LangChain agent native `response_format` for concrete Pydantic/dataclass/JSON-schema structured outputs plus graph-side structured JSON/YAML/JSON-Schema validator and repairer for non-native/fallback paths before response filters, repaired-output-based response filter audit status, static service-token/canary/high-risk-PII output hardening corpus, Docker-backed PostgreSQL API proof for dynamic output guard CRUD/simulate/audit persistence, Docker-backed PostgreSQL graph proof for dynamic output guard mask/reject/tenant/disabled rules, fail-close/fail-open behavior, and repair/filter ordering tests ported; live provider/runtime smoke deferred to release-readiness verification |
| RAG | ingestion, chunking, adaptive routing, verified sources, relevance classifier, vector stats | verified | pgvector ingestion, hybrid retrieval, citations, admin diagnostics/vector stats API, dynamic RAG ingestion policy singleton API backed by runtime settings, RAG ingestion candidate review API/store with approve-to-Postgres-RAG sink, admin document list/add/batch/search/delete APIs backed by app-owned Postgres RAG tables, first-class admin document ACL input with private group validation, document ingestion chunking through LangChain text splitter packages, document ingestion embedding enrichment through the LangChain embedding-provider boundary, app-owned RAG chunks convertible to LangChain `Document` with canonical tenant/ACL/citation metadata, manual document ingestion overwrites untrusted source URI, source type, content hash, and flattened ACL metadata with canonical values, fail-closed tenant/collection/public-or-tenant PGVector filter helper and authorized wrapper for vector-store-native paths, candidate retriever ACL checks deny missing/malformed ACL state instead of defaulting to tenant-visible access, LangChain `langchain-postgres` PGVector factory exposed through the app container, model-facing RAG tool schema excludes caller groups, caps retrieval limit in schema and runtime before embedding/retrieval, and uses trusted execution-context groups only, API auth groups propagate through `AuthPrincipal.groups -> RunService -> ReactorState.trusted_user_groups -> ToolExecutionRequest.trusted_user_groups` so chat metadata/tool arguments cannot grant RAG ACL groups, Alembic-managed Postgres row-level-security policies for RAG source/document/chunk tenant isolation and document ACL reads, Postgres retriever transaction-local RLS context from trusted query tenant/user/groups, policy RAG seed API, `Rag:hybrid_search` LangChain tool exposure for agentic RAG using LangChain `init_embeddings` plus the ACL-before-ranking Postgres retriever, poisoning tests, full static/test gate, and live Docker-backed PostgreSQL/pgvector full-text/vector retrieval proof with embedded chunk coverage and private group ACL denial/allowance |
| Memory | conversation/session/user/task memory, summaries, ownership, hierarchical memory | verified | LangGraph checkpoint plus session history, LangMem `create_memory_manager` adapter feeding Reactor proposal review, user-memory API, task memory maintenance API, namespace policy, active namespace memory retrieval store boundary, deletion/tombstone tests, and live Docker-backed PostgreSQL lifecycle proof covering proposal, promotion, active retrieval, embedding deletion, and tombstone persistence |
| MCP | server registry, preflight, status, security, access policy, metrics, tool adapter | verified | official MCP SDK client handling, negotiation, live stdio and streamable HTTP transport smoke tests against FastMCP servers, `langchain-mcp-adapters` loader boundary for LangChain-native MCP tools with Reactor `ServerName:tool_name` normalization and fail-close credential binding, tool snapshot sync, SSRF/auth policy tests, legacy admin preflight proxy API with scoped admin token/HMAC forwarding plus audit logging, MCP security policy state/update/delete API backed by runtime settings, principal-tenant-scoped server register/list/detail/update/delete/connect/disconnect management APIs, DB-backed MCP access-policy management APIs, and Swagger/OpenAPI spec source lifecycle proxy APIs with HMAC/audit coverage ported |
| A2A/multi-agent | agent card, registry, supervisor, shared context, message bus | verified | A2A SDK endpoint, SDK `AgentCard` as the single source for the well-known card and mounted protocol routes, canonical public `supportedInterfaces` endpoint derived from `Settings.external_base_url`, task mapping, admin-gated peer registry management scoped to principal tenant instead of request-provided tenant, agent spec CRUD/system-prompt admin API and PostgreSQL table, admin-gated peer-specific and tenant-wide access-policy management API scoped to principal tenant plus outbound/skill allowlist enforcement before principal-tenant-scoped task creation with principal-tenant idempotency keys, A2A task metadata trust-boundary filtering so request metadata cannot spoof tenant, peer, skill, user, run, thread, session, event, status, or idempotency control fields, inbound tenant-wide, peer-specific, and skill allowlist access-policy enforcement before SDK message execution, unsigned inbound A2A headers cannot grant trusted user groups, peer agent and skill identity propagation into run metadata for audit, persisted task events with principal-tenant-scoped admin REST detail/timeline APIs, SDK protocol task-store status timeline events, principal-tenant-scoped task resume/cancel APIs with `task.resumed` and `task.cancelled` timeline events, push outbox request and lifecycle event contracts preserving peer, skill, user, and metadata context, Docker-backed PostgreSQL proof covering task idempotency plus durable outbox idempotency without invalid agent-run FK coupling, Docker-backed PostgreSQL proof for create/cancel/resume lifecycle push outbox persistence, and Docker-backed PostgreSQL REST API proof for peer registration/listing plus task create/get/resume/cancel/idempotent push outbox persistence ported; live peer-network interoperability smoke is deferred to release-readiness verification |
| Auth/identity/security | users, roles, JWT/IAM, token revocation, external issue identity mapping, headers/CORS | verified | FastAPI auth middleware, JWT/IAM, hashed tenant-scoped API key principal resolution with spoofed-header rejection tests and invalid-key fail-close before unsigned header fallback, tenant/provider/external-subject scoped user identity mapping store with baseline `user_identities` schema, migration source/target coverage including Spring legacy Slack/email/Jira/Bitbucket identity row expansion into generalized external-subject records, RBAC-protected admin upsert/lookup/list APIs, tenant-wide identity mapping list API/store covering legacy identity `findAll`, generalized external-subject delete API/store covering legacy Slack identity removal, Docker-backed PostgreSQL proof for user identity upsert/find/list/delete API persistence with user FK enforcement, structured FastAPI 403 error bodies preserving `detail` plus `error`/`statusCode`/`code`, RBAC role matrix and user role update APIs, revocation, Docker-backed PostgreSQL proof for auth register/login/me/change-password/logout token revocation persistence, platform user lookup/role update admin APIs, chat metadata trust-boundary tests preventing user metadata from overriding response/audit tenant, user, channel, run, thread, checkpoint, runtime, model-routing, prompt, structured-output, fallback-model, and trusted-group fields, security header tests, ASGI trusted-host allowlist enforcement with configured host rejection tests, global request body size limit middleware with 413 rejection tests, and canonical external base URL settings used by public A2A metadata ported |
| Admin/analytics | dashboards, usage, trace, latency, eval, RAG, Slack activity, cache, tenant admin | verified | capabilities, doctor report/summary, audit list/export, ops dashboard plus metric-name discovery, client error-report ingestion API, tenant-scoped debug replay diagnostics API, retention policy API, task memory maintenance API, RBAC user role update API, agent spec CRUD/system-prompt APIs, platform user lookup/role update APIs, tool call history/ranking APIs, tool outcome stats/accuracy APIs, token-cost usage queries with Docker-backed PostgreSQL API proof for by-session/daily/top-expensive tenant-scoped aggregation, cache stats/invalidation APIs, trace/latency APIs with tenant-scoped span event store queries, platform health/vectorstore stats APIs, principal-tenant-scoped legacy metric ingestion compatibility APIs, platform pricing list/upsert APIs, platform tenant list/get/create/suspend/activate and tenant analytics APIs, admin session overview/list/detail/export/delete/user-session/tag compatibility APIs, tenant-scoped quota/SLO/alert rule/list/resolve APIs, tenant overview/usage/quality/tools/cost dashboards, tenant execution/tool CSV exports, tenant SQLAlchemy store/schema, eval case/result API foundations, eval runs/pass-rate dashboard analytics, Slack activity channel/daily analytics, RAG analytics status/channel APIs, conversation analytics channel/failure/latency APIs, follow-up suggestion CTR stats API/store, and users usage top/cost/daily/by-model APIs ported |
| Slack/integrations | Events API, Socket Mode, slash commands, FAQ, proactive channels, multibot | verified | multibot/proactive admin storage/APIs, signed Events API with active/previous signing-secret rotation, slash-command HTTP ingress with missing-trigger idempotency disambiguation, Events API durable enqueue with in-memory duplicate marking only after successful durable outbox write so Slack retries cannot be lost after transient enqueue failures, redacted Events API gateway enqueue audit records with tenant/event/channel/user/idempotency/outbox metadata and no raw message text, event callback worker, response_url retry client, Slack Web API chat.postMessage client preserving 429 `Retry-After` metadata, outbox dispatcher propagation of worker retry delay into durable retry scheduling, slash-command thread-first LangGraph response delivery, Slack slash intent parsing for help plus brief/my-work prompt rewrites with intent metadata, Slack response formatter for non-completed run warnings, blank responses, and generic refusal fallback rewrites, Slack reminder slash commands with in-memory per-user add/list/done/clear, time parsing, due collection, agent-bypass response_url handling, due-reminder DM poller, and opt-in FastAPI lifespan runner, in-memory per-user sliding-window slash-command and event-worker rate limiting with shared AppContainer lifecycle and agent/FAQ-bypass on limit, in-process Slack backpressure limiter for command and event workers with fail-fast/queue settings and permit release on completion, Slack prompt reload compatibility API, FAQ registration domain/schema/store, FAQ admin CRUD API, manual FAQ ingest enqueue API, FAQ ingest worker state-transition contract, Slack Web API history client, normalized FAQ document builder, PostgreSQL RAG sink wiring, FAQ ingestion embedding enrichment through the LangChain embedding-provider boundary, FAQ fast-path responder decision logic, event-worker FAQ fast-path integration, durable outbox dispatcher with retry/dead-letter status transitions, FAQ stats/events/probe/feedback/scheduler-health admin APIs, FAQ reaction feedback tracking, signed Block Kit interaction/button feedback ingestion, PostgreSQL feedback table/store foundation, feedback submit/list/get/review-update/unreviewed/delete/stats/export/bulk-review APIs with prompt/template/model/tool metadata preservation for PromptLab analysis, model/template/domain/intent feedback analytics API for negative-rate triage, Socket Mode envelope ACK/outbox normalization for events/slash/interactions including missing-trigger slash-command idempotency disambiguation, Slack SDK runner factory with app-token validation, Spring legacy tenantless Slack bot and channel FAQ row expansion into tenant-scoped Python records, opt-in lifespan start/close lifecycle, native gateway vs Slack MCP integration boundary from Slack official AI/MCP/Event/Socket guidance plus Hermes gateway/plugin separation, Slack integration metadata propagation into LangGraph/LangChain prompt context with Slack thread timestamp and tool-availability disclaimers, Slack Assistant `assistant_thread_*` lifecycle payload parsing/ignore-safe worker behavior, and optional Redis-backed multi-replica Slack user rate limiting with tenant-scoped keys, fail-closed default, and async worker await coverage ported; live Slack workspace smoke proof deferred to release-readiness verification; full handler parity covered by unit/integration handler contract tests |
| Scheduler/background jobs | scheduled jobs, executions, prompt lab scheduler, alerts | verified | durable scheduler tables, Postgres lease, durable outbox dispatch leases with expired-dispatching reclaim and lease clear on dispatch/failure, worker retry/timeout/dead-letter tests, croniter-backed due-job sweep with Spring six-field cron compatibility, API/domain cron syntax validation rejects invalid schedules before durable store writes, persisted scheduled jobs are revalidated on read/worker paths so corrupted cron rows fail closed, opt-in FastAPI lifespan scheduler runner wiring, opt-in FastAPI lifespan alert scheduler wiring, PromptLab run accepted/status transition API, PromptLab LangGraph RunService execution service, PromptLab LLM judge integration, async alert evaluation scheduler with new-alert dispatch/failure tracking, opt-in PromptLab auto-optimization scheduler with configured/all-template resolution plus non-reentrant lifespan runner, durable `PROMPT_LAB_AUTO_OPTIMIZE` scheduler job execution through SchedulerWorker into the PromptLab auto optimizer, and Alembic/SQLAlchemy/Postgres API proof that the durable `scheduled_jobs.job_type` constraint accepts `PROMPT_LAB_AUTO_OPTIMIZE` ported; live provider smoke proof deferred to release-readiness verification |
| Eval/quality/hardening | eval cases/results, red-team, scenario validation, hardening suites | verified | eval case/result storage with API-level domain validation before store writes, run-log listing, run promotion, executor replay, deterministic evaluation, provider-backed LLM judge tier execution with LangChain structured output when available, eval runs/pass-rate dashboard analytics, source-controlled regression suite, LangSmith `kv` dataset export adapter with deterministic case-derived example ids plus packaged `reactor-langsmith-eval-sync` dry-run proof, trace grading, packaged `reactor-scenario-matrix` CLI, legacy scenario corpus, packaged `reactor-hardening-suite` CI orchestration CLI, and red-team probe corpus ported; live provider proof deferred to release-readiness verification |
| Observability/cost/SLO | metrics, tracing, model pricing, token/cost usage, SLO alerts | verified | model pricing and usage ledger domain, PostgreSQL schema/store, admin model pricing list/upsert APIs with audit, admin token-cost query APIs with Docker-backed PostgreSQL usage-ledger aggregation proof, chat token usage responses, run-completion usage ledger hook, client error-report ingestion API, tenant-scoped debug replay diagnostics API, Prometheus token/cost counters and metric-name discovery API, principal-tenant-scoped legacy MCP/tool/eval metric ingestion buffer API, input guard stats query API plus `metric_guard_events` runtime sink, SLO alert domain/API foundation with alert-rule enum/domain validation mapped to 400 before persistence, tenant-scoped alert rule and instance SQLAlchemy persistence, baseline/burn-rate evaluators, async alert evaluation cycle with dispatch and consecutive-failure tracking, opt-in lifespan alert scheduler wiring, OpenTelemetry run/graph-node spans, configurable console/OTLP HTTP trace exporter wiring in FastAPI lifespan, optional LangSmith tracing exporter environment setup with official hide-inputs/hide-outputs/hide-metadata privacy env defaults, LangChain/OpenAI-style provider usage metadata extraction from message objects or serialized dict messages, and streaming LangGraph/LangChain direct or wrapped event usage metadata precedence for usage ledger records ported; live backend/provider integration proof deferred to release-readiness verification |
| Runtime settings/config | feature flags, tenant settings, dynamic policies | verified | DB-backed runtime settings with typed Settings adapter for tenant/global `Settings` overrides, AppContainer effective settings lookup, admin effective-settings diagnostics endpoint for applied/ignored/error override visibility, principal-tenant-scoped non-global settings CRUD/list queries, retention policy API, replica-count-aware Redis readiness policy that requires Redis for production multi-replica API/worker deployments while preserving local/single-node operation without Redis, Docker-backed PostgreSQL proof for admin settings CRUD persistence plus Alembic-migrated runtime setting overrides applied through `AppContainer.effective_settings`, and full static/test gate |
| Data migration/cutover | optional legacy data tools only; Python 2.0 starts with fresh data | verified | Optional migration utilities remain available for operator validation, rollback planning, and future one-off imports, but legacy Spring data cutover is not required for Python 2.0 release readiness. Existing NDJSON export/import, parity, rollback snapshot, retained-table manifest, file-backed dress rehearsal, and Docker-backed PostgreSQL proof stay as non-blocking compatibility tooling. New production data should be accumulated directly in the Python/PostgreSQL runtime. |

## Guard And Output Safety Detail

| Feature | Legacy Contract | Python Status | Remaining Gate |
| --- | --- | --- | --- |
| Input guard admin settings | pipeline, stage config, reorder, simulate, stats | verified | stage config feeds input guard runtime for guard enabled, validation lengths, injection detection enabled, sensitivity, and pipeline reorder execution in both graph/runtime and admin simulate paths; `metric_guard_events` PostgreSQL model, Alembic migration, principal-tenant-scoped legacy stats query, runtime metric sink, graph identity propagation, and prompt-injection hardening/false-positive regression tests ported |
| Input guard custom rules | tenant-scoped CRUD for regex/keyword rules | verified | Docker-backed PostgreSQL graph integration test covers keyword and regex `BLOCK` rules, tenant isolation, disabled rule exclusion, and non-blocking `WARN` behavior |
| Intent registry API | `/api/intents` admin CRUD for classifier/profile definitions | verified | DB-backed registry table, Docker-backed PostgreSQL API CRUD persistence test, and Docker-backed PostgreSQL LangGraph runtime integration through rule-based profile selection ported |
| Output guard static secret leak block | fail-close output guard stage | verified | service-token, GitHub-token, canary-secret, SSN, and Luhn-valid payment-card hardening corpus ported |
| Output guard dynamic rule API | `/api/output-guard/rules` CRUD, audits, simulate | verified | Docker-backed PostgreSQL API integration test covers CRUD, priority-ordered listing, simulation, delete, and audit persistence |
| Output guard dynamic rule runtime | priority-ordered `MASK`/`REJECT` evaluation | verified | Docker-backed PostgreSQL graph integration test covers tenant-scoped enabled rules, disabled-rule exclusion, `MASK` modification metadata, and `REJECT` fail-close behavior |

## Non-Completion Rules

- A table or DTO alone does not count as a migrated feature.
- Empty package scaffolding alone does not count as a migrated feature.
- A smoke test alone does not count as retained capability completion.
- A feature is not complete until equivalent Python tests cover the retained behavior
  or the old behavior is explicitly classified as `drop`/`defer`.
- The full goal is not complete while any retained feature area is below `verified`.
- Module additions must preserve the import boundaries enforced by
  `tests/unit/test_module_architecture.py`.

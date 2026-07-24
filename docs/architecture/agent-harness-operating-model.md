# Reactor Agent Harness Operating Model

Last reviewed: 2026-06-29.

This document turns current agent-engineering practice into Reactor rules. It is
the long-form companion to `AGENTS.md`, `CLAUDE.md`, and
`docs/architecture/python-langgraph-replatform-spec.md`.

## Source Basis

Reactor follows the strongest ideas from these public references while preserving
the project contract: FastAPI + LangGraph + LangChain, PostgreSQL as durable
truth, Redis only for ephemeral coordination, and local focused verification
before broad gates.

- As of 2026-06-29, OpenAI's
  ["Harness engineering for agentic coding"](https://openai.com/index/harness-engineering/)
  is the primary harness reference:
  keep instruction files concise, treat repository docs as the system of record,
  add deterministic scripts/tests instead of relying only on prompts, and feed
  agent failures back into harness improvements.
- OpenAI's
  ["Unrolling the Codex agent loop"](https://openai.com/index/unrolling-the-codex-agent-loop/),
  ["Unlocking the Codex harness: how we built the App Server"](https://openai.com/index/unlocking-the-codex-harness/),
  and ["Symphony"](https://openai.com/index/open-source-codex-orchestration-symphony/)
  inform the product-runtime split:
  the core agent loop, persistence, tool protocol, and orchestration contract are
  reusable runtime surfaces, while client apps and issue/workflow systems remain
  edge adapters.
- OpenAI Agents SDK docs for
  [guardrails](https://openai.github.io/openai-agents-python/guardrails/) and
  [tracing](https://openai.github.io/openai-agents-python/tracing/) reinforce the
  same separation Reactor uses: generic agent instrumentation is useful, but
  product safety decisions need explicit input/output/tool guard surfaces and
  trace metadata that can be inspected outside chat logs.
- Anthropic's
  ["Building effective agents"](https://www.anthropic.com/research/building-effective-agents)
  informs the control-flow bias:
  start with simple composable patterns, use frameworks when they buy durable
  execution and observability, and keep agent control flows understandable.
- Anthropic's
  ["Writing effective tools for AI agents"](https://www.anthropic.com/engineering/writing-tools-for-agents)
  informs tool-profile policy:
  evaluate tools with realistic tasks, collect tool-call/error/latency/token
  metrics, keep high-impact tools discoverable, and reduce redundant wrappers
  that waste model context.
- The 2026 Agentic Harness Engineering paper,
  ["Observability-Driven Automatic Evolution of Coding-Agent Harnesses"](https://arxiv.org/abs/2604.25850),
  informs harness-improvement discipline:
  track editable harness components, compress experience into evidence the next
  agent can consume, and pair each harness edit with an expected outcome that can
  later be checked.
- The 2026 evidence-provenance survey,
  ["From Agent Traces to Trust"](https://arxiv.org/abs/2606.04990), reinforces
  that final-answer quality is not enough for enterprise agents. Reactor records
  how tool outputs, retrieval, memory, policy decisions, and ignored settings
  influenced execution so failures can be audited and replayed.
- Tool-output guard wiring sanitizes every model-visible ToolMessage and rendered
  prompt tool-output line as `[tool_output:data]`, redacts canary secrets, and
  records guard findings without treating tool text as instructions. Context
  manifests preserve tool-output guard counts and findings for replay/eval review.
  Release readiness derives a `toolOutputGuard` facet from that manifest metadata
  so release review can inspect sanitizer counts and findings directly.
- RAG tool-output projection recursively removes ACL proof from native LangGraph
  ToolMessages, LangChain ToolNode results, and response-filter insights while
  preserving bounded `acl_hash` evidence only in audit records and context
  manifests. The `ragIngestionLifecycle.toolOutputBoundary` readiness sensor keeps
  those framework paths aligned. LangChain adapters use native
  `content_and_artifact` tool responses so labeled/redacted content and sanitized,
  truncation-safe artifacts share one boundary without copying raw tool results
  into checkpoints. Invoke and stream paths aggregate only known sanitizer findings
  into run metadata and checksum-only context-manifest evidence; release artifacts
  never copy the sanitized ToolMessage content. Runtime RAG artifacts keep only
  bounded citation proof fields and promote them into the manifest before structured
  output validation in both invoke and stream execution. Invalid or oversized runtime
  citation ids are replaced by a count-only signal, fail closed in both paths, and
  never enter public run metadata or context-manifest evidence as raw values. The
  citation evidence list shares the RAG search maximum of 20 items; overflow values
  are omitted, count-only, and fail closed with invoke/stream parity. Runtime RAG
  evidence is promoted only from the versioned Reactor tool-result artifact contract
  with succeeded status, idempotency, and sanitizer labeling. Failed or foreign-schema
  citation claims are count-only failures and their values are never persisted.
  LangChain HITL interrupts recover the full message state through the configured
  `BaseCheckpointSaver` because middleware may intentionally drop `ToolMessage.artifact`.
  The versioned sanitized content envelope restores bounded RAG evidence and a
  checksum-only tool-output section. Invoke/resume treats checkpoint messages as a
  complete runtime snapshot while stream events remain deltas, preventing evidence
  loss and repeated-resume count inflation without persisting raw tool output.
  A trusted replay/fork `checkpoint_id` remains pinned for graph invocation, but
  post-interrupt evidence recovery removes that pin from a copied read config so
  `aget_tuple` resolves the newly written latest child checkpoint. The trusted
  invocation config itself is never mutated. If that supplemental checkpoint
  read fails after the graph has already returned an interrupt, preserve the
  approval pause and fall back to the messages in `GraphOutput`; expose only a
  fixed, raw-error-free recovery status in response metadata. Cancellation still
  propagates so shutdown and caller abort semantics are not weakened. Repeated
  HITL resumes stay on the same durable thread: each approval executes only its
  current pending tool once, a later tool request produces a new interrupt with
  the latest action, and the graph completes only after the final approval.
- LangChain [agents](https://docs.langchain.com/oss/python/langchain/agents) and
  [middleware](https://docs.langchain.com/oss/python/langchain/middleware) docs:
  use middleware for generic model/tool controls such as call limits, retries,
  PII handling, fallback, tool selection, context editing, and HITL before adding
  custom equivalents.
- LangGraph docs for [durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution),
  [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts),
  [stores](https://docs.langchain.com/oss/python/langgraph/stores), and
  [subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs):
  use framework runtime semantics instead of ad-hoc orchestration.
- LangSmith docs for [observability](https://docs.smith.langchain.com/observability)
  and [evaluation](https://docs.smith.langchain.com/evaluation): use traces,
  datasets, evaluators, and experiment comparison for agent observability and
  release review, with redaction and tenant policy owned by Reactor.
- HumanLayer
  ["12-factor agents"](https://github.com/humanlayer/12-factor-agents):
  keep prompts, context, tools, control flow, and human contact explicit and
  testable rather than hidden in opaque chains.

These references do not override Reactor invariants. If a public pattern conflicts
with tenant isolation, approvals, ACL-before-ranking, idempotency, redaction,
partial-test strategy, or PostgreSQL as source of truth, keep the Reactor invariant
and document the reason.

Reference freshness is part of the harness; reference freshness means rechecking
the public source basis when LangChain/LangGraph/LangSmith major APIs change,
when `AGENTS.md` or `CLAUDE.md` gain a new class of rule, before a release that
changes agent runtime behavior, or when an agent failure suggests the written rule
is no longer aligned with current framework behavior. Treat external posts as
dated input, not live authority; the durable Reactor rule must still land in this
document, the canonical spec, a test, or a machine-readable gate.

## Source-Of-Truth Hierarchy

Use the narrowest durable source that can own the decision:

1. `docs/architecture/python-langgraph-replatform-spec.md` owns stack, module,
   storage, runtime, security, retention, and verification policy.
2. This file owns harness operating rules and how agent failures become executable
   feedback loops.
3. `AGENTS.md` and `CLAUDE.md` are session maps. They point to source-of-truth docs
   and list invariants agents must remember every run.
4. Tests, smoke reports, eval datasets, migrations, OpenAPI snapshots, and release
   artifacts are stronger evidence than prose.
5. PR descriptions, chat history, and dated plans are supporting context only.

When two documents conflict, prefer the canonical spec for architecture, this file
for harness operations, and executable tests or generated artifacts for current
behavior. Then update the stale document in the same change.

## Harness Definition

The harness is everything around the model that makes work repeatable:

- repository-local instructions and architecture docs
- typed state, request, response, tool, and event contracts
- LangGraph graph/subgraph composition, checkpoints, stores, interrupts, and
  streaming
- LangChain middleware, tool adapters, provider routing, structured output, and
  retriever integrations
- deterministic policy: tenancy, RBAC, approval, budgets, idempotency, ACLs,
  redaction, cost ledger, and loop exit
- focused tests, hardening tests, eval datasets, smoke reports, release evidence,
  and observability traces

Do not solve a repeated production or agent failure only by adding prompt prose.
Translate the lesson into the narrowest executable harness layer that can own it.

## Agent Runtime Governance Baseline

Baseline scope: `v1.0.9..v1.0.17-3-ga6d8fe2a4`, checked from `main` on
2026-07-01. This baseline closes the generic agent-runtime governance phase that
started after the Python/LangGraph replatform. Future work should use this as the
decision boundary between core runtime safety and product or quality delivery.

### Closed baseline

- `durable_operations`: durable queue lease remediation, dead-letter lease expiry,
  approval lifecycle, outbox/inbox lifecycle, usage/cost lifecycle, checkpoint
  diagnostics, checkpoint replay/fork provenance, Redis ephemeral coordination,
  artifact lifecycle, and migration persistence are covered by focused tests,
  hardening evidence, or release-readiness facets.
- `privacy_observability`: LangSmith trace privacy, OpenTelemetry/LangSmith SDK
  evidence, observability target redaction, PII middleware scope, trace exception
  redaction, cost/token validation, and secret-free release payloads are covered by
  smoke/readiness contracts.
- `provider_runtime`: provider usage metadata, backend provider smoke evidence,
  provider runtime smoke payloads, provider fallback policy, pricing/token
  validation, and live backend usage metadata are governed by typed evidence and
  release readiness.
- `protocol_boundaries`: MCP auth/preflight and adapter loading, A2A protocol
  negotiation, agent card, task API, diagnostics, operational evidence, API
  boundary evidence, migration dress evidence, and Slack gateway/MCP surface
  separation are explicit release facets.
- `rag_memory_grounding`: RAG ACL redaction, poisoning coverage, citation boundary,
  structured citation diagnostics, memory status reconciliation, active-only memory
  admission, LangMem maintenance, RAG ingestion lifecycle, and grounded structured
  answer contracts are pinned in context manifests and release readiness.
- `tool_governance`: tool schema validation, reserved arguments, high-risk
  approvals, tool timeouts, sanitized tool output, tool invocation lifecycle,
  active tool profile budgets, deterministic `dropped_tools` reasons, and
  Slack/MCP write-surface separation are covered by policy tests and evidence
  facets.
- `langgraph_runtime`: durable database fail-close behavior, checkpoint stores,
  graph store runtime, resume/fork/replay provenance, streaming events and
  interrupts, loop budget, node defaults, cache serialization, fault tolerance,
  subgraph topology, and LangChain middleware policy resolution are baseline
  runtime contracts.
- `release_readiness`: release readiness aggregates hardening, observability,
  LangSmith eval sync, API, protocol, provider, Slack, migration, RAG/memory/tool,
  and graph-runtime evidence with named gate identity, required-report handling,
  skipped-gate visibility, and malformed-report fail-close behavior.

### Remaining high-risk gaps

- User-facing vertical slices are still thinner than the runtime: CLI, Slack,
  RAG/memory, and admin diagnostics need product workflows that exercise the
  governed runtime through real user paths.
- Online-to-offline quality loops exist as evidence contracts, but failed trace to
  eval-case promotion is not yet a strong day-to-day product workflow.
- Prompt/context/tool-selection quality has governance metadata, but needs
  task-level eval pressure tied to product workflows rather than more schema
  expansion.
- Live deployment/operator proof remains release-batch work: broad live provider,
  Slack, MCP/A2A, migration, and release-smoke runs should be refreshed before
  external rollout, not after every focused slice.

### Generic hardening stop condition

Generic hardening is closed when a proposed change only adds another evidence
field, duplicate validator, taxonomy variant, or readiness facet for an already
covered category above and does not protect a new user-facing workflow, a new
runtime surface, a newly discovered failure class, or a framework-version change.
At that point, prefer product or quality work over not another generic
evidence-field expansion.
Decision shorthand: not another generic evidence-field expansion.

### Future hardening rule

Add new hardening only when a new user-facing workflow, new runtime surface, new
external protocol/provider behavior, new persistence/migration path, new
model-visible context/tool surface, or repeated verified failure creates a concrete
risk not covered by the closed baseline. The default next move is a small vertical
slice with focused RED/GREEN tests, affected lane tests, and the existing static
gates; hardening follows the slice instead of preceding it indefinitely.

Reactor applies three observability layers to every harness improvement:

- **Component layer:** every editable harness component has a file-level owner,
  test/eval owner, and rollback path. Examples: prompts, AGENTS/CLAUDE maps,
  LangChain middleware policy, tool schemas, MCP adapters, graph nodes,
  context manifests, eval rubrics, and smoke scripts.
- **Experience layer:** raw traces, logs, tool transcripts, and eval output are
  compressed into source-labeled evidence a future agent can inspect. The durable
  artifact is a failing test, smoke report, eval case, trace reference, or dated
  plan; not an isolated chat conclusion.
- **Decision layer:** each harness edit states what failure class it should reduce
  and how the next run will verify that prediction. If the prediction is wrong,
  update the harness component or retire the rule instead of accumulating prose.

The default escalation path is:

```text
instruction ambiguity
-> source-of-truth doc update
-> focused regression or architecture test
-> static/smoke/eval gate
-> typed policy or runtime boundary
```

Skip directly to a typed policy/runtime boundary when the failure can leak data,
execute an unsafe tool, break tenancy, corrupt durable state, or create unbounded
cost.

### Rules-to-sensors matrix

Every durable agent instruction needs a feedback sensor. A feedforward rule is the
instruction, API contract, prompt release, or policy that tells the next agent what
to do. A feedback sensor is the local command, test, eval, smoke report, trace
shape, or release artifact that proves the rule still works.

| Feedforward rule | Feedback sensor |
| --- | --- |
| Use CodeGraph for structural exploration | `tests/unit/test_agent_harness_docs.py` keeps `codegraph_context`, `codegraph_trace`, `codegraph_impact`, `codegraph_status`, and `rg for literal` guidance in the session maps |
| Keep docs as maps, not manuals | `tests/unit/test_agent_harness_docs.py` plus stale-detail cleanup in the owning doc |
| Use LangChain middleware for generic model/tool controls | LangChain-agent unit tests proving policy metadata, limits, retries, fallback, PII, and HITL wiring |
| Forbid untrusted LangChain object deserialization | `tests/unit/test_module_architecture.py` static import and dynamic-import sensors plus `langchainSerializationBoundary` readiness evidence |
| Use LangGraph checkpoints, stores, interrupts, streaming, and subgraphs | focused graph tests for resume/replay/fork, stream events, subgraph topology, and state schema versioning |
| Keep RAG/memory grounded and tenant-scoped | ACL-before-ranking, citation, poisoning, tombstone, and context-manifest tests |
| Keep LangSmith useful without leaking data | observability smoke reports with privacy evidence plus offline eval sync reports |
| Preserve release gate identity metadata | `tests/unit/test_release_readiness_evidence.py` readiness checks for canonical `scope`, `owner`, `mode`, and artifact |
| Preserve local confidence without remote CI | focused RED/GREEN, affected lane tests, static gates, and release evidence artifacts |

If a feedforward rule has no feedback sensor, either add one or remove the rule
from the always-loaded instruction files.

## Instruction File Policy

`AGENTS.md` and `CLAUDE.md` are maps, not manuals.

- Keep them short enough to be read every session.
- Put durable detail in canonical docs and link to it.
- Prefer invariant phrasing over task history.
- Remove or consolidate stale rules once an executable test or policy owns them.
- Update both files when architecture, safety policy, verification policy, or
  command contracts change.

## Agent Work Loop

Every non-trivial change should leave this evidence trail:

1. Identify the owning package and canonical spec section.
2. Use CodeGraph for structural questions: `codegraph_context` for broad context,
   `codegraph_trace` for flow, `codegraph_impact` for blast radius, and
   `codegraph_status` for index health. Use `rg for literal` text only.
3. State the behavior gap as an executable test, smoke, eval, or static check.
3. Run RED and confirm the failure is the missing behavior.
4. Implement the smallest change inside the owner boundary.
5. Run GREEN, then the nearest affected lane.
6. Widen only when risk crosses graph/runtime, persistence, auth/security, RAG
   ACL, durable jobs, dependency versions, or release evidence.
7. Update docs only for durable rules; avoid narrative progress logs in
   architecture docs.
8. Commit separable concerns separately and preserve a clean verification record.

This preserves Reactor's partial-test strategy. Full `pytest` is a release or
cross-boundary tool, not the default inner-loop command.

Do not use remote CI as the product mechanism for confidence. Local deterministic
commands, focused tests, static gates, and release smoke artifacts are the required
evidence. Remote automation may mirror those gates, but Reactor must remain
verifiable without assuming it exists.

## Framework-Native First

Use the framework feature before custom code when it preserves Reactor policy:

- LangGraph for state, checkpointing, stores, interrupts, streaming, subgraphs,
  and durable execution.
- LangChain `create_agent` and middleware for generic model/tool loop controls.
- LangChain tool/retriever/provider integrations where Reactor can wrap them with
  policy, tenancy, audit, and redaction.
- LangSmith for trace/eval/dataset workflows where Reactor can keep secrets,
  tenant data, and release gates controlled.

Custom Reactor code belongs at product boundaries: RBAC, tenancy, approval rows,
audit, idempotency, ACL filtering, cost ledger, retention, migration
compatibility, and safety-critical policy.

Framework-native adoption must be explicit:

- LangChain middleware owns generic agent controls only when it can report enough
  metadata for Reactor audit, cost, and policy decisions.
- LangGraph persistence/checkpoints/stores/interrupts own runtime semantics, but
  product run records, approval rows, leases, and outbox/inbox records remain
  application-owned.
- LangSmith owns trace/eval workflow mechanics, but Reactor owns redaction,
  tenant scoping, dataset release policy, and what blocks a release.
- LangChain structured output should use concrete schemas first. Reactor response
  boundaries still validate, repair, or block outputs before filters and delivery.
  Schema-less JSON structured output must still be object-shaped; arrays and
  scalars are invalid unless an explicit schema permits them.
  Policy-blocked structured output terminates as `rejected`, never `completed`,
  and streaming surfaces return the block in the terminal event rather than as a
  successful model token. Native LangGraph streaming treats the final v2
  `on_chain_end.data.output` policy result as authoritative over earlier chunks
  only when an empty v2 `parent_ids` list proves root graph termination. Missing,
  malformed, or nested lineage fails closed. LangChain agent streaming likewise
  reads native `structured_response` only from
  `on_chain_end.data.output`, serializes it through the same invoke helper, and
  treats that field as authoritative whenever present. An empty native structured
  response fails closed for both invoke and stream instead of falling back to
  ordinary message or token text. Provider objects that cannot be JSON-serialized
  fail closed with a safe error code and without raw object or exception details.
  A v2 structured-response event must carry an empty `parent_ids` list, proving it
  is a root `on_chain_end`; missing, malformed, or non-empty lineage fails closed
  and nested chain output is ignored.

Runtime contracts:

- LangGraph durable execution owns checkpoint/resume mechanics. Reactor nodes still
  isolate non-idempotent side effects behind approval, outbox, inbox, or
  idempotency records because interrupted or retried nodes can replay. Native
  LangGraph and LangChain tools use one durable pre-handler claim primitive:
  unavailable or unresolved claims fail closed, succeeded claims reuse stored
  results, and approval resume atomically binds the matching pending-approval row
  without changing its invocation identity.
- Checkpoint retention is application policy; checkpoint retention records how
  long graph state can be replayed, exported, or deleted. LangGraph checkpointers
  and stores provide framework mechanics, but Reactor owns tenant-scoped
  retention, deletion, export, fork provenance, and replay/audit meaning in
  Postgres-backed records.
- Production or `database_required` runtime startup must fail closed when the
  database URL is missing; in-memory graph stores are local/non-durable only and
  must not mask a missing Postgres checkpointer.
- Subgraphs must declare their subgraph checkpoint mode. Use inherited parent
  checkpointers for shared runtime state, dedicated checkpointers only when the
  subgraph has independent replay semantics, and disabled checkpointing only for
  deterministic local helper graphs whose state can be recomputed.
- Checkpoint fork/replay may pass `checkpoint_id` to LangGraph config only from
  trusted fork provenance. When the fork body omits `checkpointId`, the fork API
  may derive `forkedFromCheckpointId` from the source run's persisted
  `last_checkpoint_id`; user-supplied checkpoint metadata keys outside the fork
  API are ignored. Fork APIs strip generic checkpoint metadata keys (`checkpointId`
  and `checkpoint_id`) before creating the child run. Explicit fork `checkpointId`
  values are trimmed before becoming trusted provenance or LangGraph
  `checkpoint_id` config.
- Input and output guard block exceptions expose structured, raw-content-free metadata such as
  stage, reason, run id, tenant id, and graph node so traces and operators can
  diagnose fail-close decisions without leaking model output or tool payloads.
  Completed run metadata preserves the same safe fields as `guardBlock` when a
  guard rejects a run, and release readiness preserves and validates that facet
  for fail-close input/output guard review.
- Public run API responses project internal `response_metadata` through an
  allowlist. Approval request metadata keeps recovery/HITL fields such as IDs,
  risk, timeout, and idempotency keys, but omits raw tool input payloads.
- User-controlled chat metadata must strip checkpoint provenance keys, including
  `source`, `checkpointId`, `checkpoint_id`, `forkedFrom*`, and `forkTarget*`, so
  chat metadata cannot replay-pin or mislabel a run as a trusted fork.
- Fork APIs scrub stale fork provenance from source and request metadata before
  writing the new trusted provenance. A stale `forkedFromCheckpointId` from an
  earlier fork must never replay-pin a later fork, and stale target metadata must
  never mislabel the new `forkTargetThreadId` or `forkTargetCheckpointNs`.
- Any side effects before interrupts must be idempotent or moved behind outbox,
  inbox, approval, or reconciliation policy because resume can replay the node.
- LangGraph interrupts or LangChain HITL middleware own pause/resume mechanics.
  Reactor approval rows own RBAC, expiry, audit, and resume provenance. Release
  readiness preserves an `approvalLifecycle` facet from the hardening suite with the
  approval store/request/decision/row models, pending and terminal statuses, RBAC,
  tenant scoping, run access checks, required rejection reasons, resume provenance,
  audit, expiry support, Slack decision routing, native LangGraph direct/streaming
  and follow-up interrupt persistence, per-runtime approval-state matching,
  durable decision provenance with missing-actor fail-close, separated run-owner,
  decision-actor, and resume-actor audit identity, atomic resume claims with
  accurate runtime identity, persisted run runtime/owner/status/thread/checkpoint
  identity as the authoritative resume source, mismatch rejection before claim,
  approval-request runtime/thread/checkpoint matching against that source before
  claim with missing provenance rejected, and unsupported persisted runtimes
  rejected before runtime dispatch. Approved executions revalidate the tool's
  current catalog identity, enabled/approval policy, and resolved profile budget
  before claim; missing or inactive tool policy fails closed, while rejection can
  still finalize without executing a deactivated tool. LangChain HITL resumes are
  checked before invocation and permit exactly one approve/reject decision; edit
  decisions and external `Command` state/routing controls fail closed,
  terminal-state and resume-audit co-commit, and
  exclusion of success audit on runtime failure, plus native-resume
  timeout, guard fail-close, provider usage-ledger, graph response-metadata
  preservation, retained run-policy metadata, and durable sanitized runtime
  failure coverage for both native LangGraph and LangChain HITL resumes. Approval
  request persistence failures fail closed into recorded failed runs; streaming
  still emits a terminal completion and must not publish a pending approval event.
  A stream approval event is released only after its durable approval row exists.
  Its public payload includes that persisted `approval_id` so CLI and clients can
  act on the same durable row. Persisted stream replay preserves that identifier
  while the public event projection removes raw `tool_input`. Fixed metadata excludes storage error details,
  cancellation propagates, and a persisted approval id must normalize to a
  non-empty value before the interrupt is considered resumable. The facet names
  the focused sensors for these boundaries and retains the
  no-side-effects-before-approval contract.
- Invoke and stream paths persist an approval only after resolving the latest
  checkpoint id for the interrupted thread and namespace. A missing checkpointer,
  missing checkpoint, or checkpoint read failure fails closed before an approval
  row or public approval event can be created.
- LangGraph streaming events are product contracts once exposed through API, Slack,
  CLI, or other clients. Changes to event names, ordering, payload shape, or
  redaction require focused streaming-contract tests.
- Reactor's persisted raw event bridge uses LangChain/LangGraph
  `astream_events(..., version="v2")` `StreamEvent` payloads. Interrupt-capable
  v2 frames must be root `on_chain_stream` events with `parent_ids=[]`; missing,
  malformed, or nested lineage is ignored before approval projection and durable
  approval persistence. Only verified `__interrupt__` payloads create public
  approval events; ordinary `approval_status=pending` state chunks are ignored and
  cannot replace a verified interrupt event. Repeated root interrupt frames must
  normalize to identical approval actions: identical repeats are idempotent, while
  conflicts fail closed before approval persistence with the raw-content-free stop
  reason `interrupt_stream_conflict`. Release evidence for interrupt-capable
  streaming must separately record the LangGraph
  event-streaming projection contract: `stream_events(..., version="v3")` and
  async `astream_events(..., version="v3")` expose `stream.interrupted`,
  `stream.interrupts`, and `stream.output`, and resume uses
  `Command(resume=...)` with the same `thread_id` and a persistent checkpointer.
- LangChain middleware owns generic controls such as model/tool call limits, retry,
  fallback, PII handling, context editing, summarization, tool selection, and HITL
  only when Reactor can preserve tenant policy, audit, redaction, and usage ledger
  metadata.
- LangChain middleware is not a separate runtime. It runs inside Reactor's
  LangGraph/API/run-service policy boundary and must not bypass tool admission,
  approval rows, context manifests, usage ledgers, or event persistence.
- LangChain middleware policy resolution is observable. Applied policies record
  `langchainMiddlewarePolicy.status=applied`; invalid runtime settings record
  `status=ignored` with source, setting key, tenant, and reason so operators can
  diagnose why the harness fell back to default code policy.
- PII middleware policy evidence records `applyToInput`, `applyToOutput`,
  `applyToToolResults`, and `applyToStreamOutput` for every rule so release review
  can verify where redaction or blocking is active. Current LangChain
  `PIIMiddleware` ties streamed wire output to output handling, so Reactor rejects
  policies where `applyToStreamOutput` differs from `applyToOutput`.
- Explicit metadata middleware policy is an override boundary. If
  `metadata.middlewarePolicy` is present but invalid, Reactor records
  `langchainMiddlewarePolicy.status=ignored` with
  `reason=invalid_metadata_policy` and does not silently fall through to tenant or
  global runtime settings.
- LangSmith offline evals compare candidate graph/prompt/model/tool releases
  against curated datasets before deployment.
- LangSmith online observability monitors production traces, feedback, anomalies,
  and safety signals after deployment. Online findings become offline eval cases
  before they block future releases. This online-to-offline promotion must retain
  the incident source, redacted trace reference, expected fix owner, and eval case
  path so a future release gate can prove the incident class stayed fixed.

## Context, Tools, And Output Contracts

Agent quality fails most often through hidden context drift, too many tools, or
weak output contracts. Reactor makes those explicit:

- Every model call has a context manifest with section order, source type, taint
  labels, tenant/user scope, prompt release, and checksum.
- Prompt releases are production configuration changes. Release readiness preserves
  a `promptReleaseLifecycle` facet from the hardening suite with prompt version
  content hashes, rendered prompt checksums, PromptLab/LangSmith baseline
  comparison, prompt-write permission, release audit, rollback target, release
  metadata fields, and no dynamic prompt deserialization.
- Each manifest section records `content_checksum` over the model-visible redacted
  section content so replay/fork/eval review can verify context drift without
  exposing raw ACL metadata.
- Retrieved or memory-derived facts carry source, tenant, ACL/citation metadata,
  and model-visible redaction boundaries.
- Context manifest metadata also removes raw authorization fields such as `acl`,
  `acl_proof`, `acl_visibility`, `acl_users`, `acl_groups`, and internal
  `acl_user_*`/`acl_group_*` marker keys using normalized, case-insensitive key
  checks while retaining safe proof handles such as `acl_hash`, citation id,
  source URI, document id, chunk index, and content hash.
- Memory and RAG manifest sections carry evidence counts. RAG tool context records
  direct context count, tool chunk count, cited/uncited chunk counts, citation
  count, and sanitized citation IDs so downstream structured-output schemas can
  reject unknown sources. Grounding counts include only citation IDs that identify
  returned chunks; orphan and duplicate claims remain count-only failures.
- RAG ingestion is a background lifecycle, not hot-path answer generation. Release
  readiness preserves a `ragIngestionLifecycle` facet from the hardening suite with
  `langchain-postgres`/PGVector use, embedding boundary ownership, source/MIME/size
  policy, checksum idempotency, background retries, quarantine or human review
  before indexing captured candidates, ACL metadata, ACL-before-ranking, raw ACL
  redaction, reindex audit, diagnostics fields, and source-controlled poisoning
  eval case ids.
- Structured memory items render only memory content into model-visible context.
  Memory ids, source/proposal ids, confidence, reviewer metadata, and extraction
  prompt versions remain manifest evidence.
- Non-active memories, including tombstoned memories, are excluded from model-visible
  context. The manifest records skipped memory count and status counts so memory
  lifecycle decisions remain auditable without leaking deleted content.
- Structured memory records with ids or source ids require explicit `active` status.
  Missing status is counted as skipped `missing` status, not inferred as active.
- Structured output metadata records the selected strategy. Explicit schemas are
  `schema_passthrough`, JSON fallback is `json_object_schema`, and formats enforced
  only at the Reactor response boundary are `reactor_boundary`.
  Release readiness also records LangChain response-format strategy coverage:
  `ProviderStrategy`, `ToolStrategy`, direct schema types, and no structured
  response format.
- Invalid explicit `metadata.responseSchema` does not disappear into JSON fallback.
  Reactor records `structuredOutput.ignoredSchema` with
  `reason=invalid_response_schema` and `source=metadata.responseSchema`, while the
  response format still follows the requested format or Reactor boundary policy.
- Active tool profiles stay small. Prefer 10-20 high-signal tools with Pydantic
  schemas, risk levels, timeouts, idempotency, and recovery-friendly errors.
- Small active tool profiles are enforced by graph profile policy, runtime settings,
  and tests. A user-visible capability set that exceeds the default budget must be
  split by profile, selected dynamically, or delegated to a subgraph/subagent.
  Keep small active tool profiles as the default because tool count is part of the
  model-visible attack surface and latency/cost budget.
- Run completion metadata preserves the requested `toolProfileBudget` separately
  from `resolvedToolProfileBudget`, which records the enforcement source,
  normalized budget, configured tool count, active tool count, and dropped tool
  count for audit and release evidence.
- Invalid tool profile budget settings are observable. If
  `metadata.toolProfileBudget` is present but invalid, Reactor records
  `resolvedToolProfileBudget.status=ignored` with
  `reason=invalid_metadata_budget` and does not silently fall through to tenant or
  global runtime settings. Invalid `tools.profile_budget` runtime settings record
  `reason=invalid_runtime_setting`, source, setting key, and tenant.
- Tool outputs are untrusted until sanitized and labeled in the context manifest.
- RAG-backed answers should cite manifest evidence through structured output when
  the response format allows it. Missing or unknown citation IDs are policy
  failures, not formatting preferences. If RAG chunks are present but citation IDs
  are absent, JSON structured output fails closed instead of allowing
  model-invented citations. Native LangGraph and LangChain paths share one bounded
  citation normalization primitive. Invalid or oversized IDs are count-only, raw
  values are excluded from manifests, and they do not contribute to citation lists
  or cited/grounded chunk counts.
  Valid-looking orphan citations and repeated claims for the same returned chunk
  are likewise excluded from grounding and fail structured output closed. Matched
  citation source/document/chunk/hash fields cannot contradict the returned chunk;
  mismatches remain count-only provenance failures with invoke/stream parity.
  Duplicate citation IDs across returned chunks also fail closed: last-write-wins
  and one-citation-to-many-chunk grounding are forbidden. Native explicit IDs are
  authoritative, so legacy document/chunk-key fallback cannot connect conflicting
  explicit chunk and citation IDs. Every returned chunk must carry a safe explicit
  citation ID; missing or invalid IDs remain uncited count-only failures, and a
  valid citation for another chunk cannot make partial grounding safe. Validate
  IDs exactly as supplied at ingestion and manifest-read boundaries; never trim or
  normalize a noncanonical ID into validity.
  The allowed citation enum includes every sanitized
  citation id from both legacy single-id and citation-list manifest fields, and
  run metadata preserves `structured_output_allowed_citation_ids` for release
  review without raw context payloads.
- Context trimming and summarization use LangChain/LangGraph primitives first, but
  Reactor tests must prove message-pair validity and source-label preservation.

## Human Control

Human-in-the-loop is a product boundary, not a prompt suggestion.

- Use LangGraph interrupts or LangChain HITL middleware for generic pause/resume
  semantics.
- Reactor approval rows own requester, approver, expiry, RBAC, audit, decision
  metadata, and replay/resume provenance.
- Any side effect before an interrupt must be idempotent because interrupted nodes
  can replay.
- Destructive, external-write, shell, browser, file-write, and high-cost tools need
  approval or sandbox policy.
- Approval UX may live in Slack, API, CLI, or admin clients, but all paths write
  the same approval and audit records.

## Feedback Loops

Use failures to strengthen the harness:

- Prompt ambiguity -> tighter instruction file or canonical doc.
- Repeated edit mistake -> focused regression or architecture test.
- Tool misuse -> schema/risk policy, budget, approval, or tool profile gate.
- Retrieval leak -> ACL-before-ranking test, redaction test, and poisoning eval.
- Context drift -> context manifest reproducibility test.
- Runtime uncertainty -> trace/span contract, smoke report, or release evidence.
- Cost or latency regression -> budget/cost ledger test and metric assertion.

If a rule matters for production, prefer executable proof over prose.

Classify every repeated failure before fixing it:

| Failure class | Harness owner |
| --- | --- |
| Wrong package boundary | architecture test or import rule |
| Unsafe tool call | tool schema, risk policy, approval gate |
| Unbounded loop/cost | middleware budget, graph stop rule, usage ledger |
| Retrieval leak | ACL-before-ranking test and redaction boundary |
| Hallucinated source | citation schema/eval and answer blocking |
| Context lost in long run | checkpoint/replay test and manifest checksum |
| Poor model output shape | structured output schema and repair/block policy |
| Unobservable runtime | trace/span contract and smoke report |

## Evaluation And Observability

Agent quality is measured at multiple layers:

- Unit tests prove deterministic policy.
- Integration tests prove package boundaries and stores.
- Hardening tests prove malicious and safe paired inputs.
- Evals prove task success, grounding, tool efficiency, recovery, and budget
  adherence on representative cases.
- LangSmith datasets and experiments compare graph/prompt/model releases.
- OpenTelemetry and LangSmith traces prove runtime behavior while redacting
  secrets, credentials, PII, and private tool payloads.
- Release smoke reports prove live or local-contract readiness with JSON evidence.
- Release and eval gate reports expose `ok`, `status`, `scope`, and `evidence`
  metadata. A future agent must be able to identify the owner package, artifact
  path, intended command, and whether the report is a pass, failure, or skipped
  dry run without interpreting raw logs.
- Hardening suite evidence includes LangGraph stage order, node order, and subgraph
  entry/exit plus per-subgraph `nodes`/`nodeCount`/`checkpointMode` topology so
  runtime-structure drift is visible in release review.
- Hardening suite evidence includes LangGraph fault-tolerance loop-exit metadata:
  the durable invocation `recursion_limit` config key, positive default limit, and
  confirmation that both direct-graph and LangChain-agent invocations use it and
  release readiness fails closed when the loop budget is missing. The same facet
  records native invoke/resume/stream `RunnableConfig` trace names, shared runtime
  tag, secret-free runtime metadata, and focused executable sensors. Its error
  handling evidence also proves external cancellation propagation and underlying
  invoke/stream cancellation on timeout for native and LangChain runtimes, plus
  terminal cancellation persistence during runtime execution, approval
  persistence, and final response filtering. Cancellation persistence uses a
  tenant-scoped atomic `running -> cancelled` transition so late cancellation
  cannot overwrite an existing terminal result. The focused completion-race
  sensors prove both pre-commit cancellation and post-commit exception outcomes,
  plus terminal cancellation persistence when final token or post-interrupt
  approval event writes are cancelled, and when a client explicitly closes the
  stream after its started event, final model-visible token, or durable
  post-interrupt approval event. Run cancellation and tenant/run-scoped pending
  approval cancellation share one PostgreSQL transaction so a cancelled run
  cannot retain an actionable approval. Unexecuted `approval_required` tool claims
  are cancelled in that transaction, while other `started` claims remain eligible
  for operator reconciliation. Explicit cancellation reuses this transaction and
  permits `running` or `interrupted` runs while rejecting terminal-run races
  instead of rewriting terminal history.
- Hardening suite evidence includes the tool profile budget contract:
  recommended active-tool range, default enforcement source, and resolved metadata
  fields for configured, active, and dropped tool counts.
- Hardening suite evidence includes the context management lifecycle contract:
  LangChain `SummarizationMiddleware`, `ContextEditingMiddleware`,
  `LLMToolSelectorMiddleware`, provider tool search, context manifest checksums,
  tool-call/tool-result pair preservation, tenant policy before context mutation,
  mutation audit, and raw-context exclusion from release evidence.
- Hardening suite evidence includes the usage/cost lifecycle contract:
  LangChain `usage_metadata`, LangSmith token/cost tracking, Reactor usage ledger
  persistence, Prometheus cost metrics, tenant/run/session scoping, model
  breakdowns, admin review surfaces, and cost/token validation.
- Live backend provider smoke evidence includes LangChain
  `AIMessage.usage_metadata` token counts in `backendProviderIntegration`, and
  release readiness fails closed if that live usage metadata is missing or
  malformed.
- Hardening suite evidence includes the outbox/inbox lifecycle contract:
  replayable external side effects, incoming webhook/event de-duplication,
  Postgres `SKIP LOCKED` claims, lease ownership, retry/dead-letter behavior,
  stale-owner dispatch protection, and replayable payload routing.
- Hardening suite evidence includes LangGraph cache serialization policy:
  `CachePolicy` default key hashing uses pickle, so Reactor requires custom key
  functions for allowed cache paths, disables pickle fallback, and keeps
  side-effect nodes uncached.
- Hardening suite evidence includes `langchainSerializationBoundary` because
  LangChain serialization can revive classes from JSON through allowlisted load
  APIs and can read secrets from the environment when configured. Reactor release
  review must prove product request paths avoid LangChain object/prompt load/loads APIs,
  `secrets_from_env=True`, and user-controlled serialized configs, using trusted
  JSON parsed into Reactor-owned schemas instead. The same evidence includes
  `checkpointState`: new graph inputs receive and validate the current state schema
  version before LangGraph's initial checkpoint, every graph node rejects stale
  durable replay state before work, pending tool requests use a versioned JSON-safe schema, reducer
  updates cannot restore custom objects, unknown schema versions fail closed, and
  tool catalog identity survives checkpoint round trips. Native approval resumes
  are also versioned and normalized before LangGraph; external resume commands
  cannot smuggle state updates, routing, graph targeting, or unexpected fields.
- Hardening suite evidence includes the research answer contract
  `researchAnswerContract`: research answers set `requiresCitationIds=true` and
  `requiresSourceLabels=true`, use manifest-id citation style, disallow uncited
  claims, expose only `research_plan.answerContract` and
  `research_plan.answerExtraction` in public metadata, track
  `tracksContentHashMismatches=true` and `tracksMissingChunks=true`, and ensure
  deterministic fallback responses include sources.
- LangSmith dataset sync reports also include `datasetName`, the source suite path,
  enabled-case count, deterministic `exampleIds`, `metadataCaseIds`,
  `splitCounts`, source-suite-bearing `datasetMetadata`, and a metadata-only
  `exampleContract` with `secretScan`, plus `sdkContract` naming LangSmith `Client`,
  `has_dataset`, `create_dataset`, `create_examples`, `kv` data type, deterministic
  example ids, source-controlled cases, and max concurrency 1 so managed
  LangSmith experiments remain traceable back to source-controlled eval gates,
  framework-native SDK usage, and the release regression split. Dataset example
  sync rejects secret-shaped keys and values before calling LangSmith so managed
  eval data never receives live
  credentials through inputs, outputs, metadata, or dynamic field names.
- `reactor-release-readiness-evidence` aggregates observability, hardening, eval,
  and other gate reports into one `release_readiness` artifact. Skipped gates block
  readiness, skipped report reasons stay visible for remediation, malformed gate
  reports fail closed, and the aggregate artifact is the handoff point for release
  review.
- Readiness items preserve structured privacy evidence from submitted gate reports.
  LangSmith observability reports must carry the trace privacy contract
  (`hideInputs`, `hideOutputs`, `hideMetadata`, and required redaction check) so a
  release handoff can prove tracing is enabled without leaking sensitive inputs.
  The privacy evidence also carries `redactionCoverage`, the named field set
  exercised by the local redaction smoke.
- Observability smoke evidence also carries `observabilitySdk`, proving the
  framework-native tracing path: LangSmith tracing/privacy environment keys for
  managed traces and OpenTelemetry `TracerProvider`, `BatchSpanProcessor`, console
  and OTLP/HTTP exporters, resource attributes, sampler, and provider
  force-flush/shutdown on FastAPI lifespan exit for local/OTLP export.
- LangSmith observability smoke evidence also carries `feedbackLoop`, linking
  online traces and feedback to the source-controlled offline eval gate that should
  receive promoted incidents. `feedbackLoop.promotedCaseIds` names the offline
  eval cases that cover online findings, and release readiness cross-checks those
  ids against `langsmith_eval_sync.caseIds`.
- LangSmith observability smoke evidence also carries `observabilityTarget`, a
  secret-free target descriptor with trace provider, project, endpoint, span name,
  and `secretFree=true` so release reviewers know which online surface was
  exercised without reading raw trace payloads. Secret-bearing target fields are
  dropped from aggregate readiness evidence and fail the observability target
  contract.
- Readiness items also preserve allowlisted review evidence facets from submitted
  gate reports: LangGraph `graphTopology`, tool profile budget contract,
  LangSmith `datasetName`, `sourceSuite`, `enabledCases`, `exampleIds`,
  `metadataCaseIds`, `splitCounts`, `exampleContract`, `sdkContract`,
  `observabilitySdk`, API boundary `apiBoundary`, context
  manifest `contextManifest`, LangChain middleware policy
  `langchainMiddlewarePolicy`, checkpoint fork/replay provenance
  `checkpointProvenance`, LangChain serialization boundary
  `langchainSerializationBoundary`, structured output strategy and repair boundary `structuredOutput`,
  research answer contract `researchAnswerContract`, tool invocation lifecycle
  `toolInvocationLifecycle`, A2A protocol `a2aProtocol`, MCP preflight
  `mcpPreflight`, Slack/MCP surface policy `slackMcpSurfacePolicy`,
  memory maintenance lifecycle
  `memoryMaintenanceLifecycle`, RAG ingestion lifecycle `ragIngestionLifecycle`,
  artifact lifecycle `artifactLifecycle`, prompt release lifecycle
  `promptReleaseLifecycle`, approval lifecycle `approvalLifecycle`, provider fallback
  policy `providerFallbackPolicy`, LangGraph
  fault tolerance `langgraphFaultTolerance`, checkpoint retention policy
  `checkpointRetentionPolicy`, streaming event contract `streamingEventContract`,
  context management lifecycle `contextManagementLifecycle`, usage/cost lifecycle
  `usageCostLifecycle`, outbox/inbox lifecycle `outboxInboxLifecycle`, Redis
  coordination `redisCoordination`, and
  observability `feedbackLoop`. Do not copy arbitrary
  gate payloads into readiness; add a named allowlist facet when release review
  needs that signal.
- `checkpointProvenance.storageSemantics` records the opaque
  tenant/thread/product-namespace key, empty LangGraph root namespace, official
  saver read/write materialization boundary, target and pending-write guards,
  typed fork capability authority, typed chat namespace precedence over untrusted
  metadata, end-to-end streaming namespace propagation, graph-profile metadata
  sourced from the already-resolved durable namespace rather than overriding it,
  runtime/profile compatibility, materialization modes, and fail-close reasons.
- Checkpoint retention evidence includes `graphStoreRuntime` to distinguish the
  durable LangGraph store (`AsyncPostgresStore`) from local-only `InMemoryStore`
  and to prove the same store is passed through LangChain `create_agent`.
- Redis coordination evidence keeps Redis at the ephemeral boundary: production
  multi-replica readiness requires Redis, Pub/Sub is wakeup-only and at-most-once,
  rate limiting fails closed by default, cached Redis publisher clients close during
  `AppContainer.close()`, `runLifecyclePublisherClosedOnContainerClose`,
  `slackUserRateLimiterClosedOnContainerClose`, and durable state/checkpoints
  remain in Postgres-backed stores.
- API dress smoke evidence includes `apiBoundary` so release review can see
  FastAPI, OpenAPI `/openapi.json`, Pydantic validation, route/schema counts,
  required public paths, request/response model coverage, and secret-free schema
  metadata.
- Migration dress readiness includes `migrationPersistence` so release review can
  see SQLAlchemy ORM, Alembic migration ownership, psycopg, retained-table
  manifest usage, checksum parity, rollback snapshots, idempotent import ledger,
  and immutable migration history.
- MCP preflight readiness records authorization-security evidence for OAuth 2.1,
  PKCE, protected-resource metadata discovery, server-side token storage, and
  scope validation, plus rejection of authenticated registrations when scoped
  credential binding is unavailable.
- MCP preflight readiness records `adapterToolLoading` evidence for the official
  LangChain adapter path: `MultiServerMCPClient.get_tools` for multi-server tool
  loading, `load_mcp_tools` for session-managed loading, stdio/streamable HTTP
  connection dictionaries, the negotiated `MCP-Protocol-Version` header,
  structured-content artifacts, and configurable tool-error propagation.
- Live A2A peer-network smoke evidence is preserved as `a2aProtocol` so release
  review can verify SDK/protocol version, protocol endpoint availability, agent
  card metadata, task API behavior, diagnostics, audit, idempotency, telemetry,
  push-outbox routing, and secret-free public payloads.
- A2A smoke evidence includes `protocolNegotiation` so release review can see
  `A2A-Version: 1.0`, Major.Minor-only versions, SDK FastAPI serving, telemetry
  instrumentation, server-generated task IDs, and checked agent-card versions.
- Graph runtime tool profile budget metadata records `dropped_tools` with
  deterministic drop reasons (`denied_tool`, `tool_not_allowed`,
  `risk_level_not_allowed`, `max_tools_exceeded`) so operators can audit why a
  model-facing tool was removed without replaying the graph.
- Context manifest metadata records `memoryAdmissionPolicy` and
  `ragGroundingPolicy` so memory admission, tombstone/missing-status exclusion,
  citation tracking, uncited chunk accounting, and ACL-hash-only evidence are
  visible in release artifacts without exposing raw authorization metadata. Memory
  status counts must reconcile rendered active memory plus skipped memory so
  excluded records cannot disappear from diagnostics or release readiness.
- RAG citation evidence keeps nonblank source labels; chunks whose metadata omits
  a usable `source_uri` fall back to `document_id` rather than leaking blank or
  stringified null sources into grounded-answer review.
- Memory maintenance evidence records the LangMem manager contract and
  consolidation policy. The contract names `create_memory_manager`,
  `create_memory_store_manager`, `ainvoke`, the `messages` input key, `max_steps=1`,
  enabled inserts/updates, disabled LangMem deletes, and Reactor-owned deletion.
  Reviewed promotion can supersede prior active memories, conflicts/dedupes require
  reviewer policy, and superseded records are excluded from active model-visible
  context. API/CLI approval review surfaces expose only the safe `maintenance`
  projection of LangMem contract evidence and never raw proposal `source_payload`;
  release readiness preserves only contract metadata and records
  `sourcePayloadPrivacy` evidence that raw payload values, source payload keys,
  and unscanned secrets are not exposed. Dependency warning scans preserve
  LangMem/trustcall/LangGraph deprecations as `dependencyWarnings` release
  evidence instead of hiding them in test logs. When `pyproject.toml` exact pins
  block dependency remediation, the evidence records
  `directPins` and `pinSource`; the remediation path updates those pins and runs
  `uv lock --upgrade-package langmem --upgrade-package trustcall --upgrade-package langgraph`.
- Hardening suite `graphTopology` records `composition=stage_subgraphs`,
  deterministic `subgraphOrder`, parent-level `subgraphEdges`, and per-subgraph
  entry/exit plus node counts so runtime topology review does not depend on
  manually inspecting LangGraph traces.
- Checkpoint retention evidence records `missingDatabaseFailsClosed=true` so release
  review can verify production startup does not fall back to in-memory state when
  Postgres configuration is missing.
- `reactor-release-smoke-run --readiness-output` writes the same aggregate after a
  smoke run, combining smoke execution status with release evidence status. A release
  handoff should point reviewers at this aggregate instead of raw command logs.
- Release smoke handoffs default `requiredReports` to `smoke_run` and
  `release_evidence` so the aggregate records `requiredReports` and
  `missingReports` without relying on caller discipline. A missing required gate is
  a blocked release state even when all submitted reports passed.
- Release readiness records `tagRecommendation` with eligible,
  eligible-with-warnings, or defer status, passed reports, warning reports,
  blocking reports, and next action so operators do not infer tag readiness from
  commit count, elapsed session time, or a local-only green slice.
  The recommendation records `recommendedVersionBump` and `recommendedTagPattern`;
  minor recommendations require passed `productCapabilityBoundary.minorEligible`
  evidence, and patch recommendations record `minorBlockedReason` when that product
  boundary is absent. `eligible_with_warnings` remains tag-eligible, but
  `warningReviewRequired=true` and `warningReports` require operators to review
  warnings such as dependency or memory maintenance findings before choosing the
  next tag.
- Release tags are not per-commit checkpoints. Keep implementation commits narrow
  and pushed, but reserve version bumps and tags for release-worthy batches,
  deployment candidates, or explicit user requests. Verified hardening batches should receive v1.0.x patch tags instead of being collapsed into one later tag. Evidence-only,
  docs-only, and focused-test slices should normally remain untagged.
- Version bump boundary: patch tags are for verified hardening batches; minor tags
  require a user-visible product/runtime capability boundary, not just additive
  evidence fields, diagnostics, docs, or focused tests; major tags require an
  incompatible product, API, data, or deployment contract.
- Commit granularity checklist: commit at reviewable product or safety boundaries,
  not every RED/GREEN micro-step. A good commit has one coherent behavior, policy,
  workflow, or evidence-sensor change and the tests that prove it. Batch adjacent
  fixture, CLI wording, report-shape, and readiness-surface edits when they only
  support the same behavior; split commits when rollback, review ownership,
  migration risk, or verification scope would become ambiguous.
- Long-running hardening goal stop condition: do not mark a goal complete merely
  because one coherent slice landed, a local affected lane passed, or a commit was
  pushed. After each stable slice, continue with the next highest-risk gap from the
  release, parity, legacy-remnant, memory, or harness backlog. Agents stop only
  when the requested release, parity, or hardening boundary is met, or when the
  same external blocker repeats enough to require user input; memory or context
  pressure is a handoff condition, not a completion condition: write the current
  state, evidence, next commands, and remaining risk so the next session can
  continue.

No eval or trace may bypass Reactor tenant policy, ACL policy, redaction, or
retention rules.

Minimum release evidence for agent-runtime changes:

- focused RED/GREEN test for the behavior changed
- affected lane tests for graph, tools, RAG, memory, API, or durable jobs
- static gates: `uv lock --check`, `ruff check`, `ruff format --check`, `pyright`
- full `pytest` only for broad runtime/security/persistence/dependency/release risk
- LangSmith/OpenTelemetry smoke evidence when tracing, redaction, evals, or
  observability contracts change

Evals should be layered, not monolithic:

- task success and refusal quality
- grounding and citation accuracy
- tool selection and tool-count budget
- recovery from tool errors and invalid model output
- latency/cost regression
- safety/hardening with paired malicious and safe inputs

## Documentation Quality Bar

Good Reactor docs are operational:

- They name the owner package and source of truth.
- They state decision rules, not preferences.
- They include exact verification commands or evidence artifacts.
- They separate local deterministic gates from live smoke/release gates.
- They avoid stale migration history unless it still changes decisions.
- They do not require remote automation as a product mechanism.

When a document grows into repeated task detail, move that detail into tests,
scripts, release smoke reports, or a dated plan under `docs/superpowers/plans/`.

# Reactor Python Module Architecture Review

Date: 2026-06-27 KST. Target compatibility date: 2026-06-26.

This note is a guardrail for the Spring/Kotlin inventory to Python/LangGraph
replatform. It does not mark the migration complete. It records the module
structure decisions that every later retained capability must follow.

## Sources Checked

- `docs/architecture/python-langgraph-replatform-spec.md`
- Optional local reference: a sibling `hermes-agent` checkout
- LangGraph official docs: <https://docs.langchain.com/oss/python/langgraph/application-structure>
- LangGraph persistence docs: <https://docs.langchain.com/oss/python/langgraph/persistence>
- OpenAI Agents SDK docs: <https://openai.github.io/openai-agents-python/>
- CrewAI agents docs: <https://docs.crewai.com/v1.15.0/en/concepts/agents>

## Decisions

1. Reactor keeps the spec-first package layout instead of copying Hermes' flatter
   `agent/` package. Hermes is useful as a checklist for runtime responsibilities:
   transports, provider adapters, tool execution, guardrails, context compression,
   memory, credentials, rate limits, streaming diagnostics, and verification evidence.
2. LangGraph-specific imports stay inside `reactor.agents`, `reactor.memory`, or graph
   tests. `reactor.core` may assemble the application, but it must call adapter
   factories instead of importing LangGraph checkpoint classes directly.
3. FastAPI stays inside `reactor.api`. Routers call services/stores; they do not build
   prompts, retrieve RAG chunks, execute tools, or open raw DB sessions.
4. SQLAlchemy stays inside `reactor.persistence` and application assembly. Feature
   packages use stores/repositories, not raw sessions.
5. MCP has two boundaries: `reactor.mcp` owns server registry, preflight, protocol
   negotiation, and status; `reactor.tools.mcp` is the only boundary graph/tool
   execution should see for MCP-backed tools.
6. A2A is a protocol boundary under `reactor.a2a`; graph nodes should see delegation
   services and persisted task references, not raw protocol handlers.
7. Jobs and workers are separate. `reactor.jobs` owns durable queue/outbox/inbox logic;
   `reactor.workers` owns process entrypoints only.
8. Package scaffolds are temporary ownership markers, not a goal. Keep a package only
   when a retained capability needs the boundary or near-term tests are landing
   there. Remove empty or obsolete packages once LangChain, LangGraph, LangSmith, or
   the new product model makes the boundary unnecessary.

## Current Gaps To Keep Visible

| Package | Current State | Required Direction |
| --- | --- | --- |
| `agents` | Foundation graph/runtime exists | Split large graph behavior into `graphs`, `nodes`, and `policies` as behavior grows |
| `api/schemas` | Implemented schema boundary | Keep moving large router-local DTOs here when endpoint behavior expands |
| `auth` | Implemented auth boundary | Continue hardening JWT/IAM/RBAC/revocation around retained APIs |
| `admin` | Partial implementation | Keep admin domain helpers here; API routers still own HTTP surface |
| `slack` | Implemented integration boundary | Continue keeping Slack gateway, workers, Socket Mode, FAQ, feedback, and approval code here |
| `scheduler` | Implemented durable scheduling boundary | Keep scheduler domain/worker logic here and process startup in lifespan/workers |
| `jobs` | Implemented durable facade | Runtime imports queue, outbox, inbox, lease, and retry contracts here; persistence owns SQLAlchemy details |
| `workers` | Implemented dispatcher boundary | Keep only process/dispatch entrypoints here; business behavior stays in feature packages |
| `hooks` | Implemented runtime hook boundary | Keep hooks fail-open and separate from fail-close guards |
| `sandbox` | Implemented policy boundary | Keep code/shell/browser/file-write/destructive tools behind explicit sandbox admission |
| `artifacts` | Implemented metadata boundary | Keep blob bytes out of graph state; add storage adapters behind artifact references |
| `evals` | Implemented quality boundary | Keep regression datasets, judges, rubrics, red-team gates, and LangSmith sync here |
| `runtime_settings` | Implemented settings boundary | Keep DB-backed tenant settings and feature flags here |
| `persistence/repositories` | Partial implementation | Add typed repository interfaces only when they simplify feature-store contracts |
| `tools/mcp` | Implemented adapter facade | Graph/tool runtime imports MCP-backed LangChain tool adapters here; `reactor.mcp` remains protocol/admin |

## Architecture Invariants

- No Spring, Kotlin, Gradle, or Spring AI implementation code returns in the new runtime.
- No retained feature may bypass the capability ledger in
  `docs/migration/full-replatform-parity-ledger.md`.
- No framework import spreads across product packages just because it is convenient.
- Tests must mirror the package path and include hardening tests for security-sensitive
  behavior.
- A table, DTO, or scaffold is not completion. A retained feature only moves toward
  completion when behavior, tests, and runtime verification exist. Unretained
  features should be marked `drop` or `defer`, then removed from active implementation
  pressure.

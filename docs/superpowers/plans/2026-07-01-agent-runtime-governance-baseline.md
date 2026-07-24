# 2026-07-01 Agent Runtime Governance Baseline

## A. Governance baseline

Commit `12d9b3c01` documents the Agent Runtime Governance Baseline in
`docs/architecture/agent-harness-operating-model.md` and pins it with
`tests/unit/test_agent_harness_docs.py`.

The baseline covers `v1.0.9..v1.0.17-3-ga6d8fe2a4` across these categories:

- `durable_operations`
- `privacy_observability`
- `provider_runtime`
- `protocol_boundaries`
- `rag_memory_grounding`
- `tool_governance`
- `langgraph_runtime`
- `release_readiness`

The stop condition is now explicit: do not add more generic evidence-field
hardening unless a new user-facing workflow, runtime surface, external
protocol/provider behavior, persistence path, model-visible surface, framework
version change, or verified repeated failure creates a concrete uncovered risk.

## B/C selection

Selected: B, CLI run workflow.

Reason: the governance baseline shows the runtime has broad policy, evidence, and
release-readiness coverage, while the remaining high-ROI gap is a product workflow
that a person can use without knowing the internal FastAPI route map. Existing code
already exposes governed run APIs for create, status, and stream-event replay, so a
thin CLI can create a real vertical slice without bypassing policy or adding a new
runtime surface.

Implementation target:

- Add `reactor-runs create --message ...`
- Add `reactor-runs status RUN_ID`
- Add `reactor-runs replay RUN_ID`
- Route all commands through existing `/v1/runs` API endpoints.

Not selected: C, agent quality improvement.

Next C candidate: failed trace to offline eval case promotion. The eval/readiness
contracts exist, but the day-to-day promotion workflow is still a likely next
quality bottleneck after the first user-facing run CLI slice.

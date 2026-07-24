from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS_DOC = ROOT / "docs/architecture/agent-harness-operating-model.md"
SPEC_DOC = ROOT / "docs/architecture/python-langgraph-replatform-spec.md"
AGENTS_DOC = ROOT / "AGENTS.md"
CLAUDE_DOC = ROOT / "CLAUDE.md"
PYPROJECT = ROOT / "pyproject.toml"


def read_doc(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalized_doc_text(path: Path) -> str:
    return " ".join(read_doc(path).split())


def project_dependency_pins() -> dict[str, str]:
    payload = tomllib.loads(read_doc(PYPROJECT))
    dependencies = payload["project"]["dependencies"]
    pins: dict[str, str] = {}
    for dependency in dependencies:
        if "==" not in dependency:
            continue
        name, version = dependency.split("==", maxsplit=1)
        pins[name.split("[", maxsplit=1)[0]] = version
    return pins


def test_harness_docs_pin_current_public_source_basis() -> None:
    text = read_doc(HARNESS_DOC)

    assert "Last reviewed: 2026-06-29" in text
    for required in [
        "OpenAI's",
        "Harness engineering for agentic coding",
        "Anthropic's",
        "Building effective agents",
        "Agentic Harness Engineering",
        "From Agent Traces to Trust",
        "HumanLayer",
        "12-factor agents",
        "Unrolling the Codex agent loop",
        "App Server",
        "Symphony",
    ]:
        assert required in text


def test_harness_docs_require_executable_feedback_over_prompt_prose() -> None:
    text = read_doc(HARNESS_DOC)

    for required in [
        "Component layer",
        "Experience layer",
        "Decision layer",
        "Rules-to-sensors matrix",
        "feedforward rule",
        "feedback sensor",
        "Forbid untrusted LangChain object deserialization",
        "reference freshness",
        "instruction ambiguity",
        "focused regression or architecture test",
        "typed policy or runtime boundary",
        "Do not use remote CI as the product mechanism for confidence.",
    ]:
        assert required in text


def test_harness_docs_define_agent_runtime_governance_baseline() -> None:
    text = read_doc(HARNESS_DOC)

    assert "## Agent Runtime Governance Baseline" in text
    for category in [
        "durable_operations",
        "privacy_observability",
        "provider_runtime",
        "protocol_boundaries",
        "rag_memory_grounding",
        "tool_governance",
        "langgraph_runtime",
        "release_readiness",
    ]:
        assert category in text

    for required in [
        "Closed baseline",
        "Remaining high-risk gaps",
        "Generic hardening stop condition",
        "Future hardening rule",
        "new user-facing workflow",
        "new runtime surface",
        "not another generic evidence-field expansion",
    ]:
        assert required in text

    gap_section = text.split("### Remaining high-risk gaps", maxsplit=1)[1].split(
        "### Generic hardening stop condition",
        maxsplit=1,
    )[0]
    gap_items = [line for line in gap_section.splitlines() if line.startswith("- ")]
    assert 1 <= len(gap_items) <= 5


def test_harness_docs_cover_framework_native_agent_runtime_contracts() -> None:
    text = read_doc(HARNESS_DOC)

    for required in [
        "LangGraph durable execution",
        "checkpoint retention",
        "subgraph checkpoint mode",
        "checkpointMode",
        "LangChain middleware is not a separate runtime",
        "side effects before interrupts",
        "streaming events",
        "forkTargetThreadId",
        "chat metadata",
        "checkpoint provenance keys",
        "last_checkpoint_id",
        "Input and output guard block exceptions",
        "raw-content-free metadata",
        "guardBlock",
        "fail-close input/output guard",
        "[tool_output:data]",
        "Tool-output guard wiring",
        "tool-output guard counts",
        "toolOutputGuard",
        "checkpointProvenance",
        "LangChain middleware owns generic controls",
        "langchainMiddlewarePolicy.status=applied",
        "langchainMiddlewarePolicy",
        "langchainSerializationBoundary",
        "invalid_metadata_policy",
        "LangSmith offline evals",
        "LangSmith online observability",
        "observabilitySdk",
        "observabilityTarget",
        "datasetName",
        "exampleIds",
        "redactionCoverage",
        "context manifest",
        "contextManifest",
        "memoryAdmissionPolicy",
        "ragGroundingPolicy",
        "content_checksum",
        "citation-list",
        "uncited chunk counts",
        "schema_passthrough",
        "ProviderStrategy",
        "ToolStrategy",
        "structuredOutput",
        "invalid_response_schema",
        "composition=stage_subgraphs",
        "subgraphOrder",
        "subgraphEdges",
        "nodeCount",
        "feedbackLoop",
        "online-to-offline promotion",
        "small active tool profiles",
        "invalid_metadata_budget",
        "dropped_tools",
        "max_tools_exceeded",
        "mcpPreflight",
        "slackMcpSurfacePolicy",
        "a2aProtocol",
        "memoryMaintenanceLifecycle",
        "ragIngestionLifecycle",
        "promptReleaseLifecycle",
        "approvalLifecycle",
        "providerFallbackPolicy",
        "langgraphFaultTolerance",
        "checkpointRetentionPolicy",
        "streamingEventContract",
        "redisCoordination",
        "runLifecyclePublisherClosedOnContainerClose",
        "slackUserRateLimiterClosedOnContainerClose",
        "researchAnswerContract",
        "research_plan.answerContract",
        "research_plan.answerExtraction",
        "requiresCitationIds",
        "requiresSourceLabels",
        "tracksContentHashMismatches",
        "tracksMissingChunks",
        "Release tags are not per-commit checkpoints.",
        "Verified hardening batches should receive v1.0.x patch tags",
        "recommendedVersionBump",
        "release-worthy batches",
    ]:
        assert required in text


def test_spec_and_instruction_maps_reference_harness_contract() -> None:
    spec = read_doc(SPEC_DOC)
    agents = read_doc(AGENTS_DOC)
    claude = read_doc(CLAUDE_DOC)

    for text in [spec, agents, claude]:
        assert "agent-harness-operating-model.md" in text
        assert "CodeGraph" in text
        assert "focused" in text
        assert "remote CI" in text or "CI" in text

    for required in [
        "Component layer",
        "Experience layer",
        "Decision layer",
        "Rules-to-sensors matrix",
        "LangSmith offline evals",
        "LangSmith online observability",
        "researchAnswerContract",
    ]:
        assert required in spec

    for text in [agents, claude]:
        assert "Rules-to-sensors matrix" in text
        assert "reference freshness" in text
        assert "researchAnswerContract" in text
        assert "a2aProtocol" in text
        assert "protocolNegotiation" in text
        assert "apiBoundary" in text
        assert "migrationPersistence" in text
        assert "memoryMaintenanceLifecycle" in text
        assert "ragIngestionLifecycle" in text
        assert "promptReleaseLifecycle" in text
        assert "approvalLifecycle" in text
        assert "providerFallbackPolicy" in text
        assert "langgraphFaultTolerance" in text
        assert "checkpointRetentionPolicy" in text
        assert "graphStoreRuntime" in text
        assert "streamingEventContract" in text
        assert "redisCoordination" in text
        assert "adapterToolLoading" in text


def test_instruction_maps_pin_codegraph_structural_search_contract() -> None:
    harness = read_doc(HARNESS_DOC)
    spec = read_doc(SPEC_DOC)
    agents = read_doc(AGENTS_DOC)
    claude = read_doc(CLAUDE_DOC)

    for text in [harness, spec, agents, claude]:
        assert "CodeGraph" in text
        assert "codegraph_context" in text
        assert "codegraph_trace" in text
        assert "codegraph_impact" in text
        assert "codegraph_status" in text
        assert "rg for literal" in text
        assert "structural" in text


def test_instruction_maps_pin_commit_granularity_decision_rule() -> None:
    harness = normalized_doc_text(HARNESS_DOC)
    spec = normalized_doc_text(SPEC_DOC)
    agents = normalized_doc_text(AGENTS_DOC)
    claude = normalized_doc_text(CLAUDE_DOC)

    for text in [harness, spec, agents, claude]:
        assert "Commit granularity checklist" in text
        assert "one coherent behavior, policy, workflow, or evidence-sensor change" in text
        assert "not every RED/GREEN micro-step" in text
        assert (
            "Batch adjacent fixture, CLI wording, report-shape, and readiness-surface edits" in text
        )
        assert (
            "split commits when rollback, review ownership, migration risk, or verification scope"
            in text.lower()
        )


def test_instruction_maps_pin_version_bump_decision_rule() -> None:
    harness = normalized_doc_text(HARNESS_DOC)
    spec = normalized_doc_text(SPEC_DOC)
    agents = normalized_doc_text(AGENTS_DOC)
    claude = normalized_doc_text(CLAUDE_DOC)

    for text in [harness, spec, agents, claude]:
        assert "Version bump boundary" in text
        assert "patch tags are for verified hardening batches" in text
        assert "minor tags require a user-visible product/runtime capability boundary" in text
        assert "not just additive evidence fields, diagnostics, docs, or focused tests" in text
        assert (
            "major tags require an incompatible product, API, data, or deployment contract" in text
        )


def test_spec_agent_stack_versions_match_pyproject_pins() -> None:
    spec = read_doc(SPEC_DOC)
    pins = project_dependency_pins()

    for package in [
        "langgraph",
        "langgraph-checkpoint-postgres",
        "langchain",
        "langchain-openai",
        "langchain-anthropic",
        "langchain-google-genai",
        "langchain-postgres",
        "langchain-mcp-adapters",
        "mcp",
        "langmem",
        "langsmith",
    ]:
        assert f"| {package} | {pins[package]} |" in spec


def test_instruction_maps_pin_long_running_goal_stop_conditions() -> None:
    harness = normalized_doc_text(HARNESS_DOC)
    spec = normalized_doc_text(SPEC_DOC)
    agents = normalized_doc_text(AGENTS_DOC)
    claude = normalized_doc_text(CLAUDE_DOC)

    for text in [harness, spec, agents, claude]:
        assert "Long-running hardening goal stop condition" in text
        assert "do not mark a goal complete merely because one coherent slice landed" in text
        assert "continue with the next highest-risk gap" in text
        assert "stop only when the requested release, parity, or hardening boundary is met" in text
        assert (
            "memory or context pressure is a handoff condition, not a completion condition" in text
        )


def test_memory_dependency_warning_docs_capture_direct_pin_remediation() -> None:
    harness = read_doc(HARNESS_DOC)
    spec = read_doc(SPEC_DOC)
    agents = read_doc(AGENTS_DOC)
    claude = read_doc(CLAUDE_DOC)

    for text in [harness, spec, agents, claude]:
        assert "dependencyWarnings" in text
        assert "directPins" in text
        assert "pinSource" in text
        assert "pyproject.toml" in text
        assert "uv lock --upgrade-package langmem" in text
        assert "--upgrade-package trustcall" in text
        assert "--upgrade-package langgraph" in text


def test_instruction_maps_share_security_invariants() -> None:
    spec = read_doc(SPEC_DOC)
    agents = read_doc(AGENTS_DOC)
    claude = read_doc(CLAUDE_DOC)

    for text in [spec, agents, claude]:
        assert "LANGGRAPH_STRICT_MSGPACK=true" in text
        assert "No untrusted LangChain object deserialization" in text
        assert "No user-controlled checkpoint metadata keys" in text
        assert "No SQLite checkpointer in production" in text
        assert "No LangGraph cache backend with pickle fallback enabled" in text

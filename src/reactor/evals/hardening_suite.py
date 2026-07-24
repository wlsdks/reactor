from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from shlex import quote
from tempfile import gettempdir
from typing import cast

from reactor.agents.events import STREAM_EVENT_TYPES
from reactor.agents.graph import build_reactor_graph_stages, build_reactor_graph_subgraphs
from reactor.agents.graph_composition import (
    graph_node_order,
    graph_stage_order,
    subgraph_edge_order,
    subgraph_stage_order,
)
from reactor.agents.langchain_agent import (
    LANGCHAIN_AGENT_INVOKE_VERSION,
    langchain_middleware_chain_metadata,
)
from reactor.agents.langchain_middleware import (
    build_langchain_agent_middleware,
    default_langchain_middleware_policy,
    langchain_middleware_policy_metadata,
)
from reactor.agents.runner import RunResult
from reactor.agents.runtime_config import (
    DEFAULT_LANGGRAPH_RECURSION_LIMIT,
    LANGGRAPH_NATIVE_CONFIG_METADATA,
    LANGGRAPH_NATIVE_INVOKE_RUN_NAME,
    LANGGRAPH_NATIVE_RESUME_RUN_NAME,
    LANGGRAPH_NATIVE_RUN_TAGS,
    LANGGRAPH_NATIVE_STREAM_RUN_NAME,
)
from reactor.agents.streaming import (
    LANGCHAIN_AGENT_STREAM_EVENTS_VERSION,
    LANGCHAIN_RAW_STREAM_EVENTS_VERSION,
    LANGGRAPH_INTERRUPT_STREAM_EVENTS_VERSION,
)
from reactor.context.diagnostics import context_manifest_diagnostics
from reactor.context.manifest import ContextManifest, ContextSection
from reactor.core.settings import Settings
from reactor.mcp.registry import MCP_PROTOCOL_VERSION, MCP_TRANSPORTS
from reactor.memory.lifecycle_actions import MEMORY_LIFECYCLE_GATE_ACTION
from reactor.persistence.tool_invocation_store import TOOL_INVOCATION_STATUSES
from reactor.release.readiness_actions import HARDENING_SUITE_REPORT_FILE
from reactor.response.structured import StructuredResponseRepairer
from reactor.runs.service import stream_completion_payload

MEMORY_LIFECYCLE_TEST_SELECTOR = (
    "memory_lifecycle or sensitive_recovery_actions or structured_error_body"
)
PACKAGE_NAME_NORMALIZATION_PATTERN = re.compile(r"[-_.]+")


@dataclass(frozen=True)
class HardeningSuite:
    steps: tuple[HardeningSuiteStep, ...]
    uv_bin: str
    python_bin: str

    def step_by_id(self, step_id: str) -> HardeningSuiteStep:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise KeyError(step_id)


@dataclass(frozen=True)
class HardeningSuiteStep:
    id: str
    description: str
    command: tuple[str, ...]
    tags: frozenset[str]
    timeout_seconds: int = 120


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class HardeningSuiteStepReport:
    id: str
    description: str
    command: tuple[str, ...]
    tags: tuple[str, ...]
    status: str
    exit_code: int
    duration_ms: int
    stdout: str = ""
    stderr: str = ""

    def to_json_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "description": self.description,
            "command": list(self.command),
            "tags": list(self.tags),
            "status": self.status,
            "exitCode": self.exit_code,
            "durationMs": self.duration_ms,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(frozen=True)
class HardeningSuiteReport:
    generated_at_ms: int
    dry_run: bool
    summary: dict[str, int]
    steps: list[HardeningSuiteStepReport]
    artifact: str
    include_tags: frozenset[str] = frozenset()
    exclude_tags: frozenset[str] = frozenset()

    def to_json_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "ok": self.ok,
            "status": self.status,
            "scope": "agent_release_gate",
            "evidence": self.evidence,
            "generatedAtMs": self.generated_at_ms,
            "dryRun": self.dry_run,
            "summary": self.summary,
            "steps": [step.to_json_dict() for step in self.steps],
        }
        release_gate = self.release_gate_block
        if release_gate:
            payload["releaseGate"] = release_gate
        return payload

    @property
    def ok(self) -> bool:
        return (
            self.summary["total"] > 0
            and self.summary["failed"] == 0
            and not self.dry_run
            and not self.filtered
        )

    @property
    def status(self) -> str:
        if self.summary["failed"] > 0:
            return "failed"
        if self.dry_run or self.summary["total"] == self.summary["skipped"]:
            return "skipped"
        if self.filtered:
            return "blocked"
        return "passed"

    @property
    def filtered(self) -> bool:
        return bool(self.include_tags or self.exclude_tags)

    @property
    def release_gate_block(self) -> dict[str, object]:
        if self.dry_run:
            return {
                "status": "blocked",
                "blocksReleaseReadiness": True,
                "reason": "dry_run_only",
                "requiredReport": "hardening_suite",
                "remediation": [
                    "run_reactor_hardening_suite_without_dry_run",
                    "include_passed_hardening_suite_report_in_release_readiness",
                ],
            }
        if self.filtered:
            return {
                "status": "blocked",
                "blocksReleaseReadiness": True,
                "reason": "partial_hardening_suite",
                "requiredReport": "hardening_suite",
                "remediation": [
                    "run_reactor_hardening_suite_without_include_or_exclude_tags",
                    "include_full_passed_hardening_suite_report_in_release_readiness",
                ],
            }
        return {}

    @property
    def evidence(self) -> dict[str, object]:
        return {
            "artifact": self.artifact,
            "command": hardening_suite_command(
                artifact=self.artifact,
                include_tags=self.include_tags,
                exclude_tags=self.exclude_tags,
            ),
            "owner": "reactor.evals",
            "mode": "local_agent_hardening_release_gate",
            "selectedTags": {
                "include": sorted(self.include_tags),
                "exclude": sorted(self.exclude_tags),
                "partial": self.filtered,
            },
            "toolProfileBudget": tool_profile_budget_evidence(),
            "researchAnswerContract": research_answer_contract_evidence(),
            "toolInvocationLifecycle": tool_invocation_lifecycle_evidence(),
            "durableRunQueue": durable_run_queue_evidence(),
            "outboxInboxLifecycle": outbox_inbox_lifecycle_evidence(),
            "redisCoordination": redis_coordination_evidence(),
            "mcpPreflight": mcp_preflight_evidence(),
            "slackMcpSurfacePolicy": slack_mcp_surface_policy_evidence(),
            "memoryMaintenanceLifecycle": memory_maintenance_lifecycle_evidence(),
            "ragIngestionLifecycle": rag_ingestion_lifecycle_evidence(),
            "artifactLifecycle": artifact_lifecycle_evidence(),
            "promptReleaseLifecycle": prompt_release_lifecycle_evidence(),
            "approvalLifecycle": approval_lifecycle_evidence(),
            "providerFallbackPolicy": provider_fallback_policy_evidence(),
            "langgraphFaultTolerance": langgraph_fault_tolerance_evidence(),
            "checkpointRetentionPolicy": checkpoint_retention_policy_evidence(),
            "streamingEventContract": streaming_event_contract_evidence(),
            "graphTopology": graph_topology_evidence(),
            "contextManifest": context_manifest_evidence(),
            "contextManifestDiagnostics": context_manifest_diagnostics_evidence(),
            "langchainMiddlewarePolicy": langchain_middleware_policy_evidence(),
            "langchainMiddlewareChain": langchain_middleware_chain_evidence(),
            "langchainSerializationBoundary": langchain_serialization_boundary_evidence(),
            "contextManagementLifecycle": context_management_lifecycle_evidence(),
            "usageCostLifecycle": usage_cost_lifecycle_evidence(),
            "checkpointProvenance": checkpoint_provenance_evidence(),
            "structuredOutput": structured_output_evidence(),
        }


def mcp_preflight_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "supportedTransports": sorted(MCP_TRANSPORTS),
        "adapter": "langchain-mcp-adapters",
        "sdk": "mcp",
        "toolNameFormat": "ServerName:tool_name",
        "adapterToolLoading": {
            "client": "MultiServerMCPClient",
            "primaryMethod": "get_tools",
            "sessionLoader": "load_mcp_tools",
            "connectionDictionaryTransports": ["stdio", "streamable_http"],
            "streamableHttpProtocolHeader": "MCP-Protocol-Version",
            "structuredContentArtifactsSupported": True,
            "toolErrorsReturnToolMessage": True,
            "toolExceptionPropagationConfigurable": True,
        },
        "privateAddressBlocked": True,
        "tokenPassthroughForbidden": True,
        "unsupportedProtocolRejected": True,
        "credentialBindingRequired": True,
        "authWithoutCredentialBindingRejected": True,
        "authorizationSecurity": {
            "oauth21Required": True,
            "pkceRequired": True,
            "tlsRequired": True,
            "protectedResourceMetadataRequired": True,
            "authorizationServerMetadataRequired": True,
            "tokensStoredServerSide": True,
            "scopesValidated": True,
            "resourceIndicatorsRequired": True,
            "tokenAudienceValidated": True,
            "leastPrivilegeScopesRequired": True,
        },
    }


def hardening_suite_command(
    *,
    artifact: str,
    include_tags: frozenset[str],
    exclude_tags: frozenset[str],
) -> str:
    parts = ["uv", "run", "reactor-hardening-suite"]
    for tag in sorted(include_tags):
        parts.extend(["--include-tag", tag])
    for tag in sorted(exclude_tags):
        parts.extend(["--exclude-tag", tag])
    parts.extend(["--report-file", artifact])
    return " ".join(quote(part) for part in parts)


def slack_mcp_surface_policy_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "nativeGatewayOwnsIngress": True,
        "nativeGatewayOwnsCurrentThreadReplies": True,
        "slackMcpModelFacingOnly": True,
        "overlappingWriteSurfacesRequireRouteSelection": True,
        "currentThreadReplyRoute": "native_gateway",
        "workspaceActionRoute": "slack_mcp_tools",
        "promptContextDeclaresToolAvailability": True,
        "unavailableToolClaimsForbidden": True,
        "auditSurfaces": ["native_slack_gateway", "slack_mcp_tools"],
        "faqIngestionFailureBoundary": {
            "status": "verified",
            "worker": "ChannelFaqIngestWorker",
            "safeFailureCode": "slack_faq_ingestion_failed",
            "exceptionDetailsExcludedFrom": [
                "worker.result.error",
                "registration.last_error",
                "admin.registration.lastError",
            ],
            "failOpenResultPreserved": True,
            "verificationSensors": [
                "uv run pytest tests/unit/test_slack_worker.py -q "
                "-k channel_faq_ingest_worker_records_failure_without_raising"
            ],
            "covers": ["slack_faq_ingestion_failure_uses_safe_error_code"],
        },
        "feedbackReviewHandoff": {
            "status": "verified",
            "responseSurfaces": ["slack_run_response", "slack_approval_resume_ack"],
            "reviewCommand": (
                "reactor-admin feedback --rating thumbs_down "
                "--review-status inbox --limit 10 --output table"
            ),
            "feedbackNextActionIds": [
                "promote-eval",
                "sync-langsmith",
                "refresh-readiness",
                "export-candidate-feedback",
                "review-done",
            ],
            "feedbackNextActionIdentityFields": [
                "feedbackId",
                "evalCaseId",
                "sourceRunId",
            ],
            "feedbackNextActionReadinessFields": [
                "releaseReadinessFile",
                "readinessReportArg",
                "requiredReadinessReports",
                "readinessReports",
            ],
            "verificationSensors": {
                "focusedTests": [
                    (
                        "uv run pytest tests/unit/test_admin_cli.py -q "
                        "-k 'structured_recovery_actions or structured_error_body'"
                    ),
                    (
                        "uv run pytest tests/unit/test_feedback_router.py -q "
                        "-k 'feedback_id or readiness_handoff'"
                    ),
                    "uv run pytest tests/integration/test_feedback_api.py -q -k feedback",
                ],
                "covers": [
                    "admin_feedback_review_surfaces_recovery_actions",
                    "admin_feedback_review_preserves_structured_error_body",
                    "feedback_api_review_handoff_exercised",
                    "feedback_next_actions_preserve_feedback_identity",
                    "feedback_next_actions_preserve_readiness_handoff_fields",
                ],
            },
            "rawSlackPayloadExcluded": True,
        },
    }


def memory_maintenance_lifecycle_evidence() -> dict[str, object]:
    dependency_warnings = memory_dependency_warnings_evidence()
    return {
        "status": "verified",
        "framework": "langmem",
        "extractor": "LangMemMemoryExtractor",
        "proposalJob": "LangMemProposalJob",
        "proposalService": "MemoryProposalService",
        "store": "SqlAlchemyMemoryStore",
        "managerContract": {
            "factory": "langmem.create_memory_manager",
            "storeFactory": "langmem.create_memory_store_manager",
            "invokeApi": "ainvoke",
            "inputMessagesKey": "messages",
            "maxSteps": 1,
            "enableInserts": True,
            "enableUpdates": True,
            "enableDeletes": False,
            "applicationOwnsDeletes": True,
            "maxCandidates": 20,
            "candidateOverflowPolicy": "reject_all",
        },
        "proposalStatuses": ["proposed", "approved", "rejected", "expired"],
        "itemStatuses": ["active", "superseded", "tombstoned"],
        "extractionCreatesProposalsOnly": True,
        "extractedMemoryIdRequired": True,
        "extractedMemoryContentRequired": True,
        "promotionRequiresReviewer": True,
        "sensitivePromotionBlocked": True,
        "tombstoneDeletesEmbedding": True,
        "activeQueryFiltersStatus": True,
        "applicationOwnsLifecycle": True,
        "checkpointMemorySeparated": True,
        "consolidationPolicy": {
            "supersedesPriorActiveMemory": True,
            "reviewedPromotionCanSupersedePriorActiveMemory": True,
            "dedupeOrConflictRequiresReviewer": True,
            "supersededItemsExcludedFromActiveContext": True,
        },
        "verificationSensors": {
            "focusedTests": [
                "uv run pytest tests/unit/test_rag_memory.py -q",
                "uv run pytest tests/unit/test_prompt_assembler.py -q -k memory",
                "uv run pytest tests/unit/test_context_manifest.py -q -k memory",
                "uv run pytest tests/unit/test_memory_cli.py "
                "tests/unit/test_memory_lifecycle_actions.py "
                f"-q -k '{MEMORY_LIFECYCLE_TEST_SELECTOR}'",
                "REACTOR_TEST_POSTGRES=1 uv run pytest "
                "tests/integration/test_memory_postgres_lifecycle.py -q",
                "uv run pytest tests/integration/test_admin_api.py -q -k memory",
                "uv run pytest tests/integration/test_feedback_api.py -q -k memory",
                (
                    "uv run pytest tests/unit/test_slack_worker.py "
                    "-q -k 'reaction_feedback_memory_handoff'"
                ),
                (
                    "uv run pytest tests/unit/test_slack_feedback.py "
                    "-q -k 'negative_ack_preserves_memory_review_tag'"
                ),
            ],
            "releaseReadinessContracts": [
                "memoryMaintenanceLifecycle",
                "contextManifestDiagnostics.memoryAdmissionPolicy",
            ],
            "artifactOutputs": [
                "reports/hardening-suite.json",
                "reports/release/replatform-readiness.local.json",
                "reports/release/release-smoke-plan.local.json",
                "reports/release/release-smoke-preflight.local.json",
                "reports/release/release-smoke-preflight.local.env",
                "reports/release-smoke-run.json",
                "reports/release-evidence.json",
                "reports/release-readiness.json",
            ],
            "covers": [
                "langmem_manager_shape_exercised",
                "langmem_manager_lifecycle_policy_explicitly_configured",
                "langmem_extracted_memory_id_required",
                "langmem_extracted_memory_content_required",
                "langmem_extraction_candidate_budget_enforced",
                "proposal_promotion_requires_reviewer",
                "sensitive_memory_proposals_blocked",
                "memory_source_payload_secret_markers_flagged",
                "source_payload_sensitive_memory_proposals_blocked",
                "supersession_marks_prior_active_memory",
                "self_supersession_rejected",
                "tombstone_deletes_embedding",
                "active_namespace_memory_retrieval_boundary_exercised",
                "superseded_and_tombstoned_memory_excluded_from_model_context",
                "memory_review_api_and_cli_surface_exercised",
                "memory_feedback_review_handoff_exercised",
                "slack_reaction_feedback_enters_memory_review_handoff",
                "slack_button_feedback_preserves_memory_review_tags",
            ],
        },
        "reviewSurface": {
            "approvalApi": "/api/admin/memory/proposals/{proposal_id}/approve",
            "cliApprovalTable": (
                "reactor-memory approve PROPOSAL_ID "
                "--reason 'reviewed and approved memory' --output table"
            ),
            "lifecycleGateAction": MEMORY_LIFECYCLE_GATE_ACTION,
            "dependencyReviewCommand": dependency_warnings["reviewCommand"],
            "dependencyRemediationCommand": dependency_warnings["remediationCommand"],
            "proposalNextActionIds": [
                "approve-memory",
                "reject-memory",
                "review-memory-dependencies",
                "verify-memory-lifecycle",
            ],
            "lifecycleGateReportBinding": {
                "readinessReportArg": (
                    f"--readiness-report hardening_suite={HARDENING_SUITE_REPORT_FILE}"
                ),
                "requiredReadinessReports": ["hardening_suite"],
                "readinessReports": {"hardening_suite": HARDENING_SUITE_REPORT_FILE},
            },
            "feedbackNextActionSubjectField": "subjectUserId",
            "responseProjection": "maintenance",
            "rawSourcePayloadExposed": False,
            "sourcePayloadPrivacy": {
                "apiProjection": "maintenance",
                "cliProjection": "maintenance",
                "readinessProjection": "contract_metadata_only",
                "rawSourcePayloadExposed": False,
                "sourcePayloadKeysExposed": False,
                "secretScanRequired": True,
            },
            "sensitivityProjection": {
                "apiProjection": "maintenance.sensitivity",
                "cliProjection": "SENSITIVITY",
                "rawSourcePayloadExposed": False,
                "fields": ["status", "policy", "markers", "source"],
            },
            "maintenanceSummaryFields": [
                "manager",
                "storeManager",
                "operation",
                "maxSteps",
                "deletePolicy",
                "dependencyReviewCommand",
                "dependencyRemediationCommand",
                "sensitivity",
            ],
        },
        "dependencyWarnings": dependency_warnings,
    }


def memory_dependency_warnings_evidence() -> dict[str, object]:
    findings: list[dict[str, object]] = []
    try:
        trustcall_base = metadata.distribution("trustcall").locate_file("trustcall/_base.py")
    except metadata.PackageNotFoundError:
        trustcall_base = None
    if trustcall_base is not None and trustcall_base.exists():
        source = trustcall_base.read_text(encoding="utf-8")
        if "from langgraph.constants import Send" in source:
            findings.append(
                {
                    "package": "trustcall",
                    "module": "trustcall._base",
                    "deprecatedImport": "langgraph.constants.Send",
                    "replacement": "langgraph.types.Send",
                    "severity": "warning",
                }
            )
    return {
        "status": "review_required" if findings else "verified",
        "checkedPackages": ["langmem", "trustcall", "langgraph"],
        "installedVersions": memory_dependency_installed_versions(
            ["langmem", "trustcall", "langgraph"]
        ),
        "directPins": memory_dependency_direct_pins(["langmem", "langgraph"]),
        "pinSource": "pyproject.toml",
        "reviewCommand": "uv pip show langmem trustcall langgraph",
        "resolverCheck": {
            "command": (
                "uv lock --upgrade-package langmem --upgrade-package trustcall "
                "--upgrade-package langgraph --dry-run"
            ),
            "status": "no_lockfile_changes",
            "latestKnownFrom": "resolver",
        },
        "remediationCommand": (
            "monitor upstream trustcall/langmem compatibility; keep "
            "dependency warning visible until "
            "trustcall stops importing langgraph.constants.Send or "
            "Reactor replaces the dependency path"
        ),
        "findings": findings,
    }


def memory_dependency_direct_pins(packages: Sequence[str]) -> dict[str, str]:
    pyproject = Path("pyproject.toml")
    if not pyproject.exists():
        return {}
    payload = cast(Mapping[str, object], tomllib.loads(pyproject.read_text(encoding="utf-8")))
    project = payload.get("project")
    if not isinstance(project, Mapping):
        return {}
    dependencies = cast(Mapping[str, object], project).get("dependencies")
    if not isinstance(dependencies, list):
        return {}
    package_set = {_canonical_package_name(package) for package in packages}
    pins: dict[str, str] = {}
    for dependency in cast(list[object], dependencies):
        if not isinstance(dependency, str) or "==" not in dependency:
            continue
        name, version = dependency.split("==", 1)
        normalized = _canonical_package_name(name)
        if normalized in package_set and version.strip():
            pins[normalized] = f"=={version.strip()}"
    return pins


def _canonical_package_name(name: str) -> str:
    return PACKAGE_NAME_NORMALIZATION_PATTERN.sub("-", name.strip().lower())


def memory_dependency_installed_versions(packages: Sequence[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in packages:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def rag_ingestion_lifecycle_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "framework": "langchain-postgres",
        "vectorStore": "PGVector",
        "embeddingBoundary": "LangChainEmbeddings",
        "sourceAllowlistRequired": True,
        "mimeAllowlistRequired": True,
        "sizeLimitRequired": True,
        "checksumIdempotency": True,
        "backgroundRetries": True,
        "quarantineBeforeIndex": True,
        "humanReviewRequiredForCapturedCandidates": True,
        "aclMetadataRequired": True,
        "aclBeforeRanking": True,
        "retrievalResultsReauthorized": True,
        "retrievalResultLimitEnforced": True,
        "rawAclRedactedFromModelContext": True,
        "toolOutputBoundary": {
            "auditPayloadPreserved": True,
            "contextManifestAclHashPreserved": True,
            "nativeToolMessageAclEvidenceExcluded": True,
            "langchainToolNodeAclEvidenceExcluded": True,
            "responseFilterInsightsAclEvidenceExcluded": True,
            "recursiveCaseInsensitiveAclKeyFiltering": True,
            "citationLabelsPreserved": True,
            "langchainContentAndArtifactMode": True,
            "langchainOutputLabeled": True,
            "langchainSecretRedaction": True,
            "langchainTruncationSafe": True,
            "langchainArtifactSanitized": True,
            "langchainGuardFindingsPersisted": True,
            "langchainGuardManifestChecksummed": True,
            "langchainInvokeAndStreamGuardParity": True,
            "toolArtifactContentBoundToToolMessage": True,
            "toolArtifactContentMismatchFailsClosed": True,
            "toolArtifactContentMismatchInvokeStreamParity": True,
            "toolMessageLabelRequired": True,
            "unlabeledToolOutputFailsClosed": True,
            "unlabeledToolOutputInvokeStreamParity": True,
            "mappingWrappedToolMessagesGuarded": True,
            "commandWrappedToolMessagesGuarded": True,
            "rawSanitizedOutputExcludedFromManifest": True,
            "boundedRuntimeRagCitationArtifact": True,
            "runtimeRagCitationPromotionBeforeStructuredBoundary": True,
            "langchainInvokeAndStreamCitationParity": True,
            "runtimeRagCitationFieldsAllowlisted": True,
            "runtimeRagCitationLengthsBounded": True,
            "invalidRuntimeRagCitationIdsFailClosed": True,
            "invalidRuntimeRagCitationValuesExcluded": True,
            "invalidRuntimeRagCitationInvokeStreamParity": True,
            "invalidRuntimeRagCitationCountProjected": True,
            "invalidCitationIdsExcludedFromGroundingCounts": True,
            "nativeRagCitationBoundarySharedWithLangChain": True,
            "nativeRagCitationFieldsAndLengthsBounded": True,
            "invalidNativeRagCitationIdsCountOnly": True,
            "invalidNativeRagCitationValuesExcluded": True,
            "citationChunkIdentityRequired": True,
            "orphanCitationIdsExcludedFromGroundingCounts": True,
            "duplicateCitationIdsExcludedFromGroundingCounts": True,
            "orphanAndDuplicateCitationClaimsFailClosed": True,
            "citationProvenanceFieldsMatchReturnedChunk": True,
            "mismatchedCitationProvenanceExcluded": True,
            "mismatchedCitationProvenanceFailClosed": True,
            "mismatchedCitationProvenanceInvokeStreamParity": True,
            "duplicateChunkCitationIdsExcludedFromGroundingCounts": True,
            "duplicateChunkCitationIdsDoNotUseLastWriteWins": True,
            "duplicateChunkCitationIdsFailClosed": True,
            "duplicateChunkCitationIdInvokeStreamParity": True,
            "nativeExplicitCitationIdentityAuthoritative": True,
            "legacyDocumentKeyFallbackCannotOverrideExplicitId": True,
            "conflictingExplicitCitationIdsExcluded": True,
            "conflictingExplicitCitationIdsFailClosed": True,
            "missingOrInvalidChunkCitationIdsCountOnly": True,
            "noncanonicalCitationIdsRejected": True,
            "noncanonicalManifestCitationIdsRejected": True,
            "chunksWithoutSafeCitationIdsRemainUncited": True,
            "partialRagGroundingFailsClosed": True,
            "invalidChunkCitationIdInvokeStreamParity": True,
            "runtimeRagCitationCardinalityBounded": True,
            "runtimeRagCitationLimitAlignedWithSearch": True,
            "omittedRuntimeRagCitationValuesExcluded": True,
            "omittedRuntimeRagCitationsFailClosed": True,
            "omittedRuntimeRagCitationInvokeStreamParity": True,
            "versionedReactorToolArtifactContract": True,
            "runtimeRagArtifactContractValidated": True,
            "runtimeRagArtifactManifestBoundToDurableEnvelope": True,
            "mismatchedRagArtifactManifestRejected": True,
            "failedRagArtifactCitationClaimsRejected": True,
            "foreignSchemaRagArtifactCitationClaimsRejected": True,
            "invalidRagArtifactValuesExcluded": True,
            "invalidRagArtifactInvokeStreamParity": True,
            "durableToolEnvelopeVersioned": True,
            "langchainInterruptReadsCheckpointMessages": True,
            "langchainInterruptRagEvidencePersisted": True,
            "artifactlessCheckpointToolOutputChecksummed": True,
            "hitlResumeRuntimeEvidenceSnapshotStable": True,
            "hitlResumeNoRagDoubleCount": True,
            "streamRuntimeEvidenceDeltaMode": True,
            "rawDurableToolOutputExcludedFromManifest": True,
            "pinnedReplayInvocationCheckpointPreserved": True,
            "postInterruptCheckpointPinRemovedFromReadCopy": True,
            "postInterruptLatestChildCheckpointRead": True,
            "postInterruptReadDoesNotMutateInvocationConfig": True,
            "checkpointReadFailurePreservesInterrupt": True,
            "checkpointReadFailureMetadataSecretFree": True,
            "checkpointReadCancellationPropagated": True,
            "repeatedHitlLatestPendingAction": True,
            "repeatedHitlApprovedToolExactlyOnce": True,
            "repeatedHitlFinalApprovalCompletes": True,
        },
        "reindexAuditRequired": True,
        "poisoningEvalCaseIds": ["rag-poisoning-retrieval-is-labeled"],
        "verificationSensors": {
            "focusedTests": [
                (
                    "uv run pytest tests/unit/test_rag_document_management.py "
                    "tests/unit/test_rag_retriever.py tests/unit/test_rag_vector_store.py "
                    "tests/unit/test_rag_tool.py -q"
                ),
                "uv run pytest tests/unit/test_prompt_assembler.py -q -k rag",
                "uv run pytest tests/unit/test_structured_output.py -q -k 'rag and citation'",
                (
                    "uv run pytest tests/unit/test_agent_graph_policy.py "
                    "-q -k 'research_profile_marks_plan or "
                    "removes_rag_acl_evidence_from_model_visible_tool_message'"
                ),
                (
                    "uv run pytest tests/unit/test_langchain_tool_adapter.py "
                    "-q -k 'executes_through_reactor_tool_handler or "
                    "hides_acl_evidence_but_preserves_audit_payload or "
                    "bounded_citation_evidence_drops_unbounded_and_private_fields or "
                    "bounded_citation_evidence_rejects_noncanonical_citation_ids or "
                    "records_oversized_citation_id or "
                    "excludes_orphan_citations_from_grounding_counts or "
                    "deduplicates_citations_in_grounding_counts or "
                    "rejects_mismatched_citation_provenance or "
                    "rejects_duplicate_chunk_citation_ids or "
                    "counts_chunks_without_safe_citation_ids or "
                    "bounds_citation_evidence_cardinality or "
                    "labels_and_redacts_model_visible_result or "
                    "keeps_truncated_result_as_safe_artifact'"
                ),
                (
                    "uv run pytest tests/unit/test_langchain_agent.py "
                    "-q -k 'records_tool_output_guard_manifest or "
                    "blocks_tool_artifact_content_mismatch or "
                    "blocks_unlabeled_tool_output or "
                    "promotes_runtime_rag_citations_before_boundary or "
                    "blocks_oversized_runtime_rag_citation_id or "
                    "blocks_orphan_runtime_rag_citation_claims or "
                    "blocks_omitted_runtime_rag_citations or "
                    "blocks_rag_artifact_manifest_mismatch or "
                    "blocks_failed_rag_artifact_citation_claims or "
                    "hitl_resume_does_not_double_count_checkpoint_rag or "
                    "durable_rag_context_metadata_rejects_foreign_schema_claim or "
                    "durable_interrupt_messages_reads_latest_after_pinned_replay or "
                    "preserves_interrupt_when_checkpoint_read_fails or "
                    "propagates_checkpoint_read_cancellation or "
                    "repeated_hitl_resumes_latest_pending_action'"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py "
                    "-q -k 'langchain_stream_records_tool_output_guard_manifest or "
                    "langchain_stream_blocks_tool_artifact_content_mismatch or "
                    "stream_promotes_runtime_rag_citations_before_boundary or "
                    "stream_blocks_oversized_runtime_rag_citation_id or "
                    "stream_blocks_orphan_runtime_rag_citation_claims or "
                    "stream_blocks_omitted_runtime_rag_citations or "
                    "stream_blocks_rag_artifact_manifest_mismatch or "
                    "stream_blocks_failed_rag_artifact_citation_claims'"
                ),
                ("uv run pytest tests/unit/test_documents_cli.py -q -k 'ask and citation'"),
                (
                    "uv run pytest tests/unit/test_eval_regression_suite_apply.py "
                    "-q -k documents_ask"
                ),
                (
                    "uv run pytest tests/unit/test_rag_ingestion_candidate_ids.py "
                    "tests/unit/test_runs_cli.py -q -k candidate"
                ),
                (
                    "uv run pytest tests/unit/test_rag_candidate_actions.py "
                    "tests/unit/test_dress_api_smoke.py -q"
                ),
                (
                    "uv run pytest tests/unit/test_feedback_router.py "
                    "tests/unit/test_documents_cli.py -q -k "
                    "'preserve_feedback_id_on_rag_candidate_handoff or "
                    "candidate_ask_missing_citation_uses_candidate_eval_handoff or "
                    "langsmith_report_preserves_rating_only_feedback_queue'"
                ),
                (
                    "uv run pytest tests/unit/test_release_readiness_evidence.py "
                    "-q -k 'eval_apply_boundary or without_eval_apply_coverage'"
                ),
                "uv run pytest tests/integration/test_rag_ingestion_candidates_api.py -q",
                "uv run pytest tests/integration/test_feedback_api.py -q -k rag_candidate",
                (
                    "uv run pytest tests/integration/test_feedback_api.py -q "
                    "-k 'admin_submit_returns_review_next_actions or stats_export'"
                ),
                (
                    "uv run pytest tests/integration/test_feedback_api.py -q "
                    "-k 'citation_marker and memory'"
                ),
            ],
            "releaseReadinessContracts": [
                "ragIngestionLifecycle",
                "contextManifestDiagnostics.ragGroundingPolicy",
                "researchAnswerContract",
                "ragIngestionLifecycle.toolOutputBoundary",
            ],
            "covers": [
                "managed_document_ingest_requires_acl",
                "retrieval_filters_acl_before_ranking",
                "rag_tool_revalidates_retriever_results_before_model_output",
                "rag_tool_caps_retriever_results_to_requested_limit",
                "rag_tool_results_promote_citations_to_context",
                "native_and_langchain_tool_outputs_exclude_acl_evidence",
                "audit_and_context_manifest_preserve_acl_hash_evidence",
                "langchain_tool_node_labels_and_redacts_model_visible_results",
                "langchain_tool_node_truncation_preserves_safe_artifact",
                "langchain_invoke_and_stream_guard_findings_persisted",
                "langchain_tool_artifact_content_mismatch_fails_closed",
                "unlabeled_langchain_tool_output_fails_closed",
                "mapping_wrapped_langchain_tool_messages_are_guarded",
                "command_wrapped_langgraph_tool_messages_are_guarded",
                "tool_output_manifest_excludes_sanitized_content",
                "runtime_rag_citations_promoted_before_structured_output_validation",
                "runtime_rag_citation_artifacts_are_bounded_and_allowlisted",
                "langchain_invoke_and_stream_runtime_citation_parity",
                "invalid_runtime_rag_citation_ids_fail_closed",
                "invalid_runtime_rag_citation_values_excluded_from_manifest",
                "langchain_invoke_and_stream_invalid_citation_parity",
                "public_run_metadata_preserves_invalid_citation_count",
                "native_rag_citations_share_bounded_normalization",
                "invalid_native_rag_citations_are_count_only",
                "invalid_native_rag_citation_values_are_not_persisted",
                "rag_citations_require_returned_chunk_identity",
                "orphan_and_duplicate_citations_do_not_inflate_grounding_counts",
                "orphan_and_duplicate_citation_claims_fail_closed",
                "citation_provenance_fields_match_returned_chunks",
                "mismatched_citation_provenance_is_not_persisted",
                "mismatched_citation_provenance_fails_closed_with_invoke_stream_parity",
                "duplicate_chunk_citation_ids_do_not_inflate_grounding_counts",
                "duplicate_chunk_citation_ids_do_not_use_last_write_wins",
                "duplicate_chunk_citation_ids_fail_closed_with_invoke_stream_parity",
                "native_explicit_citation_identity_is_authoritative",
                "legacy_document_key_fallback_cannot_alias_explicit_citation_ids",
                "conflicting_explicit_citation_ids_are_excluded_and_fail_closed",
                "missing_or_invalid_chunk_citation_ids_are_count_only",
                "noncanonical_citation_ids_are_not_normalized",
                "noncanonical_manifest_citation_ids_fail_closed",
                "chunks_without_safe_citation_ids_remain_uncited",
                "partial_rag_grounding_fails_closed_with_invoke_stream_parity",
                "runtime_rag_citation_evidence_is_limited_to_search_maximum",
                "omitted_runtime_rag_citation_values_are_not_persisted",
                "omitted_runtime_rag_citations_fail_closed",
                "langchain_invoke_and_stream_omitted_citation_parity",
                "reactor_tool_artifacts_are_versioned",
                "runtime_rag_artifacts_require_successful_reactor_contract",
                "runtime_rag_artifact_manifest_is_bound_to_durable_envelope",
                "mismatched_runtime_rag_artifact_manifest_fails_closed_with_invoke_stream_parity",
                "failed_and_foreign_schema_citation_claims_fail_closed",
                "invalid_runtime_rag_artifact_values_are_not_persisted",
                "langchain_invoke_and_stream_invalid_artifact_parity",
                "durable_tool_content_envelopes_are_versioned",
                "langchain_interrupt_reads_messages_from_checkpoint_saver",
                "interrupt_rag_and_tool_guard_evidence_is_persisted",
                "artifactless_checkpoint_tool_output_is_checksum_only",
                "hitl_resume_replaces_runtime_snapshot_counts",
                "hitl_resume_does_not_double_count_rag_evidence",
                "stream_runtime_evidence_remains_delta_merged",
                "raw_durable_tool_output_is_excluded_from_manifest",
                "pinned_checkpoint_id_remains_on_graph_invocation",
                "post_interrupt_read_drops_pin_from_config_copy_only",
                "post_interrupt_read_uses_latest_child_checkpoint",
                "trusted_invocation_config_is_not_mutated",
                "checkpoint_read_failure_preserves_interrupt_result",
                "checkpoint_read_failure_metadata_excludes_error_details",
                "checkpoint_read_cancellation_is_not_swallowed",
                "repeated_hitl_exposes_only_latest_pending_action",
                "each_approved_tool_executes_exactly_once",
                "repeated_hitl_completes_after_final_approval",
                "weak_documents_ask_answers_promote_to_eval_with_citation_markers",
                "documents_ask_review_done_action_closes_feedback_queue",
                "rag_candidate_eval_handoff_uses_canonical_candidate_ids",
                "rag_candidate_hardening_report_action_exposed_before_readiness",
                "api_smoke_requires_readiness_action_fields",
                "rag_candidate_feedback_review_handoff_exercised",
                "rag_candidate_feedback_actions_scope_inferred_candidate_tag",
                "rag_candidate_feedback_bulk_review_action_closes_candidate_queue",
                "rag_candidate_ask_action_preserves_feedback_tags",
                "rag_candidate_minor_boundary_requires_eval_apply_coverage",
                "rag_candidate_eval_apply_boundary_remediation_exposed",
                "memory_feedback_review_handoff_preserved_while_citation_marker_is_required",
            ],
        },
        "diagnosticsSurface": {
            "status": "verified",
            "apiPaths": [
                "/api/admin/rag/ingestion-jobs/{job_id}",
                "/v1/rag/ingestion-jobs/{job_id}",
            ],
            "releaseReviewFields": [
                "sourceAllowlist",
                "mimeAllowlist",
                "sizeLimitBytes",
                "checksum",
                "chunkCount",
                "aclHash",
                "quarantineStatus",
                "retryCount",
                "poisoningFindings",
            ],
        },
    }


def artifact_lifecycle_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "storage": {
            "production": "s3-compatible",
            "local": "filesystem",
            "metadataStore": "postgres",
        },
        "referenceBoundary": "ArtifactReference",
        "graphStateStoresReferencesOnly": True,
        "blobBodiesExcludedFromGraphState": True,
        "metadataRequired": [
            "artifact_id",
            "tenant_id",
            "owner_user_id",
            "mime_type",
            "size_bytes",
            "sha256",
            "acl",
            "retention_days",
            "source_run_id",
        ],
        "accessPolicy": {
            "shortLivedSignedUrls": True,
            "authenticatedStreamingEndpointSupported": True,
            "tenantAclEnforcedBeforeDownload": True,
            "signedUrlExpiryTested": True,
        },
        "ingestionPolicy": {
            "mimeSniffingRequired": True,
            "mimeAllowlistRequired": True,
            "sizeLimitRequired": True,
            "checksumIdempotency": True,
            "parserAllowlistRequired": True,
            "parserSandboxingRequired": True,
            "spoofingRegressionTested": True,
            "parserFailureQuarantinesArtifact": True,
        },
        "retentionPolicy": {
            "tenantRetentionApplied": True,
            "deleteOrTombstoneDerivedEmbeddings": True,
            "tombstoneAuditRequired": True,
        },
    }


def prompt_release_lifecycle_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "store": "SqlAlchemyPromptStore",
        "versionModel": "PromptVersionRecord",
        "releaseModel": "PromptReleaseRecord",
        "templateBoundary": "ChatPromptTemplate",
        "contentHashRequired": True,
        "renderedChecksumRequired": True,
        "evalGateRequired": True,
        "langsmithDatasetRequired": True,
        "baselineComparisonRequired": True,
        "promptWritePermissionRequired": True,
        "releaseAuditRequired": True,
        "rollbackTargetRequired": True,
        "noDynamicPromptDeserialization": True,
        "metadataFields": [
            "promptReleaseId",
            "templateId",
            "versionId",
            "environment",
            "contentHash",
            "renderedChecksum",
            "evalDatasetName",
            "evalExperimentId",
            "baselineVersionId",
            "candidateVersionId",
            "releasedBy",
        ],
        "evalGate": {
            "sourceSuite": "tests/fixtures/agent-eval/regression-suite.json",
            "datasetName": "reactor-regression",
            "requiredSplit": "regression",
            "splitCounts": {"regression": 4},
            "caseIds": [
                "tool-exposure-issue-readonly",
                "casual-prompt-exposes-no-tools",
                "rag-grounded-answer-cites-source",
                "rag-poisoning-retrieval-is-labeled",
            ],
            "langsmithReportName": "langsmith_eval_sync",
        },
        "diagnosticsSurface": {
            "status": "verified",
            "apiPaths": [
                "/api/admin/prompts/templates/{template_id}/releases",
                "/v1/admin/prompts/templates/{template_id}/releases",
            ],
            "releaseReviewFields": [
                "promptReleaseId",
                "contentHash",
                "renderedChecksum",
                "evalDatasetName",
                "evalExperimentId",
                "recommendation",
                "rollbackTarget",
            ],
        },
    }


def approval_lifecycle_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "runtimePause": "langgraph_interrupts_or_langchain_hitl",
        "store": "SqlAlchemyApprovalStore",
        "requestModel": "ApprovalRequest",
        "decisionModel": "ApprovalDecision",
        "rowModel": "PendingApproval",
        "pendingStatus": "pending",
        "resumeClaimStore": "SqlAlchemyRunStore",
        "resumeClaimTransition": "interrupted_to_running",
        "resumeClaimAuditEvent": "run.resume_claimed",
        "resumeClaimPayloadFields": ["approval_id", "claimed_by", "runtime"],
        "terminalStatuses": ["approved", "rejected", "expired", "cancelled"],
        "rbacRequired": True,
        "tenantScoped": True,
        "runAccessChecked": True,
        "decisionReasonRequiredOnReject": True,
        "rejectionReasonValidatedAtApiBoundary": True,
        "resumeProvenanceRequired": True,
        "checkpointProvenanceRequiredBeforeApproval": True,
        "resumeFollowupCheckpointProvenanceRequiredBeforeApproval": True,
        "langgraphResumeCheckpointProvenanceRefreshed": True,
        "langchainResumeCheckpointProvenanceRefreshed": True,
        "auditRequired": True,
        "expirySupported": True,
        "sideEffectsBeforeApprovalForbidden": True,
        "slackDecisionRouteSupported": True,
        "atomicResumeClaim": True,
        "duplicateResumeFailsClosed": True,
        "tenantScopedResumeClaim": True,
        "rawToolInputExcludedFromResumeClaimAudit": True,
        "resumeClaimRuntimeAccurate": True,
        "resumeRuntimeUnavailablePreservesInterruptedRun": True,
        "nativeLangGraphInterruptsEnabledInDatabaseRuntime": True,
        "nativeLangGraphDirectInterruptPersisted": True,
        "nativeLangGraphStreamingInterruptPersisted": True,
        "nativeLangGraphFollowupInterruptPersisted": True,
        "runtimeResumeApprovalStateMatched": True,
        "resumeDecisionUsesDurableProvenance": True,
        "resumeApprovalBooleanStrict": True,
        "langchainHitlSingleDecisionRequired": True,
        "langchainHitlEditDecisionForbidden": True,
        "langchainHitlControlFieldsForbidden": True,
        "langchainHitlResumeValidatedBeforeInvoke": True,
        "persistedRunResumeIdentityAuthoritative": True,
        "resumeCheckpointIdentityMismatchFailsClosed": True,
        "persistedRunRuntimeOwnerStatusAuthoritative": True,
        "resumeIdentityCheckedBeforeClaim": True,
        "approvalRequestRuntimeAuthoritative": True,
        "approvalRequestThreadIdentityRequired": True,
        "approvalRequestCheckpointNamespaceRequired": True,
        "approvalResumeProvenanceMismatchFailsClosed": True,
        "approvalResumeProvenanceCheckedBeforeClaim": True,
        "langchainResumeApprovalLookupCancellationPersisted": True,
        "langchainResumeApprovalLookupFailureFailsClosed": True,
        "langgraphResumeApprovalLookupCancellationPersisted": True,
        "langgraphResumeApprovalLookupFailureFailsClosed": True,
        "langgraphResumeToolPolicyCancellationPersisted": True,
        "langgraphResumeToolPolicyFailureFailsClosed": True,
        "unsupportedPersistedResumeRuntimeFailsClosed": True,
        "resumeRuntimeValidatedBeforeDispatch": True,
        "approvedToolRevalidatedBeforeResume": True,
        "currentToolCatalogIdentityRequired": True,
        "currentToolPolicyBudgetApplied": True,
        "missingToolProviderFailsClosed": True,
        "inactiveApprovedToolFailsClosed": True,
        "rejectedResumeAllowsInactiveTool": True,
        "approvalToolCheckedBeforeClaim": True,
        "missingDecisionActorFailsClosed": True,
        "resumeAuditActorsSeparated": True,
        "resumeTerminalAuditAtomic": True,
        "failedResumeExcludesSuccessAudit": True,
        "nativeResumeTimeoutEnforced": True,
        "nativeResumeGuardFailClosed": True,
        "nativeResumeProviderUsageRecorded": True,
        "nativeResumeResponseMetadataPreserved": True,
        "nativeResumeRunMetadataPreserved": True,
        "nativeResumeRuntimeFailurePersisted": True,
        "langchainResumeRuntimeFailurePersisted": True,
        "approvalPersistenceFailureFailClosed": True,
        "approvalPersistenceFailureRecorded": True,
        "streamApprovalPersistenceFailureCompletes": True,
        "streamApprovalEventAfterPersistence": True,
        "failedApprovalPersistenceSuppressesPendingEvent": True,
        "streamApprovalEventIncludesPersistedId": True,
        "persistedApprovalIdReplayable": True,
        "approvalToolInputExcludedFromReplay": True,
        "approvalPersistenceErrorDetailsExcluded": True,
        "approvalPersistenceCancellationPropagated": True,
        "approvalPersistenceIdValidated": True,
        "runCancellationCancelsPendingApprovalsAtomically": True,
        "resumeRuntimes": ["langgraph", "langchain_agent"],
        "verificationSensors": [
            (
                "uv run pytest tests/unit/test_runs_router.py -q -k "
                "resume_run_request_requires_strict_boolean_approval"
            ),
            (
                "uv run pytest tests/integration/test_api.py -q -k "
                "approval_reject_requires_nonblank_reason"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "'fails_closed_when_approval_storage_raises or "
                "stream_completes_failed_when_approval_storage_raises or "
                "propagates_approval_storage_cancellation or "
                "approval_storage_returns_blank_id or "
                "stream_persists_redacted_langchain_v2_interrupt or "
                "stream_persists_redacted_native_langgraph_interrupt'"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "'resume_fails_closed_when_checkpoint_identity_differs_from_persisted_run or "
                "resume_uses_persisted_runtime_owner_and_status or "
                "resume_fails_closed_when_approval_request_provenance_differs or "
                "resume_fails_closed_for_unsupported_persisted_runtime or "
                "resume_without_graph_preserves_unclaimed_interrupted_run or "
                "resume_fails_closed_when_approved_tool_is_no_longer_active or "
                "rejected_resume_does_not_require_tool_to_remain_active'"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "'resume_does_not_request_followup_approval_without_checkpoint or "
                "native_langgraph_resume_persists_a_followup_interrupt or "
                "langchain_resume_persists_followup_interrupt_checkpoint'"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "langchain_resume_approval_lookup_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "langchain_resume_approval_lookup_failure_fails_closed"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "langgraph_resume_approval_lookup_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "langgraph_resume_approval_lookup_failure_fails_closed"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "langgraph_resume_tool_policy_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "langgraph_resume_tool_policy_failure_fails_closed"
            ),
            (
                "uv run pytest tests/integration/test_api.py -q -k "
                "stream_events_endpoint_preserves_approval_id_without_tool_input"
            ),
            (
                "uv run pytest tests/unit/test_run_store.py tests/unit/test_run_service.py -q "
                "-k 'cancel_pending_run_approvals_query_is_tenant_and_run_scoped or "
                "approval_event_persistence_cancellation_records_cancelled'"
            ),
        ],
        "covers": [
            "approval_persistence_failure_returns_failed_run",
            "approval_persistence_failure_is_recorded",
            "stream_approval_persistence_failure_emits_completion",
            "stream_approval_event_requires_persisted_approval",
            "failed_approval_persistence_suppresses_pending_event",
            "stream_approval_event_includes_persisted_approval_id",
            "persisted_stream_replay_preserves_approval_id",
            "persisted_stream_replay_excludes_tool_input",
            "approval_persistence_error_details_are_not_exposed",
            "approval_persistence_cancellation_is_not_swallowed",
            "blank_persisted_approval_id_fails_closed",
            "persisted_run_identity_drives_resume_configuration",
            "resume_checkpoint_identity_mismatch_fails_before_claim",
            "caller_runtime_owner_and_status_cannot_override_persisted_run",
            "approval_request_runtime_matches_selected_resume_runtime",
            "approval_request_thread_matches_persisted_run_thread",
            "approval_request_checkpoint_namespace_matches_persisted_run_namespace",
            "missing_or_mismatched_approval_request_provenance_fails_before_claim",
            "langchain_resume_approval_lookup_cancellation_persisted",
            "langchain_resume_approval_lookup_failure_fails_closed",
            "langgraph_resume_approval_lookup_cancellation_persisted",
            "langgraph_resume_approval_lookup_failure_fails_closed",
            "langgraph_resume_tool_policy_cancellation_persisted",
            "langgraph_resume_tool_policy_failure_fails_closed",
            "unsupported_persisted_resume_runtime_fails_before_dispatch",
            "unavailable_resume_runtime_preserves_unclaimed_interrupted_run",
            "approved_tool_is_revalidated_against_current_catalog_identity",
            "approved_tool_obeys_current_enabled_approval_and_profile_budget_policy",
            "missing_tool_provider_fails_approved_resume_before_claim",
            "inactive_approved_tool_fails_before_claim",
            "rejected_resume_can_finalize_after_tool_deactivation",
            "run_cancellation_atomically_cancels_pending_approvals",
        ],
        "metadataFields": [
            "approval_id",
            "tenant_id",
            "run_id",
            "tool_id",
            "requested_by",
            "decided_by",
            "decision_reason",
            "thread_id",
            "checkpoint_ns",
        ],
        "apiPaths": [
            "/api/approvals",
            "/v1/approvals",
            "/api/approvals/{approval_id}/approve",
            "/v1/approvals/{approval_id}/approve",
            "/api/approvals/{approval_id}/reject",
            "/v1/approvals/{approval_id}/reject",
        ],
    }


def provider_fallback_policy_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "middleware": "ModelFallbackMiddleware",
        "router": "ProviderRouter",
        "fallbackMetadata": [
            "from_provider",
            "from_model",
            "to_provider",
            "to_model",
            "reason",
            "latency_ms",
            "cost_usd",
        ],
        "disabledProfilesSkipped": True,
        "sameModelFallbackRejected": True,
        "fallbackRequiresAlternateEnabledProfile": True,
        "tenantPolicyBoundary": "provider_routing_policy",
        "regionRetentionBoundaryRequired": True,
        "postToolFallbackRequiresPersistedState": True,
        "retryComposition": {
            "middlewareOrder": [
                "ModelFallbackMiddleware",
                "ModelRetryMiddleware",
            ],
            "firstMiddlewareOutermost": True,
            "retryScope": "per_model_before_fallback",
            "primaryExcludedFromFallbackModels": True,
            "verificationSensors": [
                "tests/unit/test_langchain_middleware.py::"
                "test_model_retry_is_exhausted_per_model_before_fallback",
                "tests/unit/test_langchain_agent.py::"
                "test_resolve_langchain_agent_models_rejects_primary_as_fallback",
            ],
        },
    }


def langgraph_fault_tolerance_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "runtime": "langgraph",
        "loopExitBudget": {
            "configKey": "recursion_limit",
            "defaultLimit": DEFAULT_LANGGRAPH_RECURSION_LIMIT,
            "configuredOnDurableInvocations": True,
            "configuredOnLangChainAgentInvocations": True,
            "releaseEvidenceRequired": True,
        },
        "runnableConfigTraceIdentity": {
            "runNames": {
                "invoke": LANGGRAPH_NATIVE_INVOKE_RUN_NAME,
                "resume": LANGGRAPH_NATIVE_RESUME_RUN_NAME,
                "stream": LANGGRAPH_NATIVE_STREAM_RUN_NAME,
            },
            "tags": list(LANGGRAPH_NATIVE_RUN_TAGS),
            "metadata": dict(LANGGRAPH_NATIVE_CONFIG_METADATA),
            "configuredOnInvokeResumeStream": True,
            "secretFree": True,
            "verificationSensors": [
                (
                    "uv run pytest tests/unit/test_langchain_agent.py -q "
                    "-k runner_invokes_langgraph_with_versioned_state_and_durable_config"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k 'publishes_resume_lifecycle_event_after_durable_event or "
                    "streams_langgraph_events_and_records_them'"
                ),
            ],
        },
        "nodeDefaults": {
            "retryPolicy": "graph_node_retry_policy",
            "cachePolicy": "disabled_for_side_effect_nodes",
            "timeoutSeconds": 120,
        },
        "cacheSerialization": {
            "langgraphDefaultKeyFuncUsesPickle": True,
            "customKeyFuncRequired": True,
            "pickleFallbackEnabled": False,
            "sideEffectNodeCacheEnabled": False,
        },
        "errorHandling": {
            "guardFailuresFailClosed": True,
            "toolFailuresBecomeToolMessages": True,
            "nonIdempotentEffectsBehindOutbox": True,
            "interruptsBypassErrorHandlers": True,
            "externalCancellationPropagates": True,
            "invokeStartCommitCancellationPersistsTerminalState": True,
            "streamStartCommitCancellationPersistsTerminalState": True,
            "langgraphResumeRuntimeCancellationPersistsTerminalState": True,
            "langchainResumeRuntimeCancellationPersistsTerminalState": True,
            "langgraphResumeClaimCommitCancellationPersistsTerminalState": True,
            "langchainResumeClaimCommitCancellationPersistsTerminalState": True,
            "langgraphResumeApprovalCancellationPersistsTerminalState": True,
            "langchainResumeApprovalCancellationPersistsTerminalState": True,
            "langgraphResumeResponseFilteringCancellationPersistsTerminalState": True,
            "langgraphResumeResponseFilteringFailureFailsOpenSafely": True,
            "langchainResumeResponseFilteringCancellationPersistsTerminalState": True,
            "langgraphResumeCompletionPersistenceCancellationResolvesTerminalState": True,
            "langchainResumeCompletionPersistenceCancellationResolvesTerminalState": True,
            "resumeCompletionCommitCancellationPreservesTerminalState": True,
            "runtimeExecutionCancellationPersistsTerminalState": True,
            "invokeRuntimeExecutionCancellationPersistsTerminalState": True,
            "invokeToolPreflightCancellationPersistsTerminalState": True,
            "invokeCheckpointReplayCancellationPersistsTerminalState": True,
            "invokeMiddlewarePreflightCancellationPersistsTerminalState": True,
            "checkpointReadCancellationPersistsTerminalState": True,
            "invokeCheckpointReadCancellationPersistsTerminalState": True,
            "resumeCheckpointReadCancellationPersistsTerminalState": True,
            "approvalPersistenceCancellationPersistsTerminalState": True,
            "invokeApprovalPersistenceCancellationPersistsTerminalState": True,
            "responseFilteringCancellationPersistsTerminalState": True,
            "invokeResponseFilteringCancellationPersistsTerminalState": True,
            "cancellationPersistencePreservesTerminalState": True,
            "completionPersistenceCancellationResolvesTerminalState": True,
            "invokeCompletionPersistenceCancellationResolvesTerminalState": True,
            "tokenEventPersistenceCancellationPersistsTerminalState": True,
            "approvalEventPersistenceCancellationPersistsTerminalState": True,
            "streamCloseAfterStartedPersistsTerminalState": True,
            "streamCloseAfterFinalTokenPersistsTerminalState": True,
            "streamCloseAfterApprovalPersistsTerminalState": True,
            "explicitRunCancellationUsesAtomicTransition": True,
            "explicitRunCancellationAllowsInterrupted": True,
            "timeoutCancelsUnderlyingExecution": True,
            "invokeRuntimeParity": True,
            "streamRuntimeParity": True,
            "verificationSensors": [
                (
                    "uv run pytest tests/unit/test_langchain_agent.py -q "
                    "-k propagates_external_cancellation_to_native_and_langchain_invocations"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k stream_timeout_cancels_native_and_langchain_generators"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k start_commit_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k resume_runtime_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k resume_claim_commit_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k resume_approval_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k resume_response_filter_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k langgraph_resume_response_filter_failure_logs_safely_and_completes"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k resume_completion_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k resume_completion_commit_cancellation_preserves_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k runtime_execution_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k create_run_runtime_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k create_run_tool_preflight_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k create_run_checkpoint_replay_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k create_run_middleware_preflight_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k checkpoint_read_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k create_run_checkpoint_read_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k resume_checkpoint_read_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k stream_approval_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k response_filter_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k create_run_response_filter_cancellation_persists_terminal_state"
                ),
                (
                    "uv run pytest tests/unit/test_run_store.py -q "
                    "-k 'cancel_running_run_query_is_tenant_scoped_and_atomic or "
                    "record_cancelled_if_running or "
                    "complete_running_run_query_is_tenant_scoped_and_atomic or "
                    "record_completed_preserves_existing_terminal_state'"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k external_cancellation_does_not_overwrite_terminal_result"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k 'completion_persistence_cancellation_records_cancelled or "
                    "completion_commit_cancellation_preserves_completed or "
                    "late_completion_rejection_suppresses_phantom_completion or "
                    "late_completion_rejection_returns_cancelled_result or "
                    "run_service_resume_completion_rejection_returns_cancelled_without_events or "
                    "langchain_resume_completion_rejection_returns_cancelled_without_events or "
                    "unknown_runtime_rejection_losing_to_cancellation_returns_cancelled or "
                    "checkpoint_preflight_failure_losing_to_cancellation_returns_cancelled or "
                    "stream_runtime_rejection_losing_to_cancellation_suppresses_completion or "
                    "streaming_capability_rejection_losing_to_cancellation_"
                    "suppresses_completion or "
                    "research_preflight_rejection_losing_to_cancellation_returns_cancelled or "
                    "stream_research_rejection_losing_to_cancellation_suppresses_completion'"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k 'create_run_completion_persistence_cancellation_records_cancelled or "
                    "create_run_completion_commit_cancellation_preserves_completed'"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k token_event_persistence_cancellation_records_cancelled"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k approval_event_persistence_cancellation_records_cancelled"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k close_after_started_event_records_cancelled"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k close_after_final_token_records_cancelled"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q "
                    "-k close_after_approval_event_records_cancelled"
                ),
                (
                    "uv run pytest tests/integration/test_api.py -q "
                    "-k 'run_cancel_endpoint_marks_run_cancelled or "
                    "run_cancel_endpoint_rejects_existing_terminal_run'"
                ),
            ],
        },
        "resumeSemantics": {
            "threadIdRequired": True,
            "checkpointNsRequired": True,
            "trustedCheckpointIdOnly": True,
            "stateHistoryAuditable": True,
            "interruptedNodeRerunsFromStart": True,
            "preInterruptSideEffectsForbidden": True,
            "preInterruptSideEffectsRequireIdempotency": True,
        },
    }


def langchain_serialization_boundary_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "sdk": "langchain-core",
        "unsafeLoadApisForbidden": [
            "langchain_core.load.load",
            "langchain_core.load.loads",
            "langchain_core.prompts.load_prompt",
            "langchain.chains.loading.load_chain",
            "langchain.agents.loading.load_agent",
        ],
        "secretsFromEnvForbidden": True,
        "userConfigDeserializationForbidden": True,
        "trustedJsonOnly": True,
        "checkpointState": {
            "runtime": "langgraph",
            "strictMsgpackEnvironment": "LANGGRAPH_" + "STRICT_MSGPACK",
            "strictMsgpackEnabledBeforeImports": True,
            "stateSchema": "reactor.agent.state.v1",
            "pendingToolSchema": "reactor.pending_tool_request.v1",
            "approvalResumeSchema": "reactor.approval_resume.v1",
            "newInputVersionInjected": True,
            "incompatibleNewInputRejected": True,
            "everyNodeVersionGuarded": True,
            "staleReplayRejected": True,
            "graphInputNormalizedBeforeCheckpoint": True,
            "resumeCommandNormalizedBeforeCheckpoint": True,
            "resumeControlFieldsForbidden": True,
            "unexpectedResumeFieldsRejected": True,
            "reducersNormalizeUpdates": True,
            "customObjectsForbidden": True,
            "unknownSchemaVersionsRejected": True,
            "catalogIdentityPreserved": True,
            "verificationSensors": [
                "tests/unit/test_agent_tool_state.py",
                "tests/unit/test_agent_graph_policy.py::test_graph_checkpoint_normalizes_pending_tool_to_strict_msgpack_state",
                "tests/unit/test_agent_graph_policy.py::test_graph_replay_rejects_stale_checkpoint_state_version",
            ],
        },
    }


def checkpoint_retention_policy_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "runtime": "langgraph",
        "store": "AsyncPostgresSaver",
        "graphStoreRuntime": {
            "durableStore": "AsyncPostgresStore",
            "localStore": "InMemoryStore",
            "schemaOwner": "alembic",
            "checkpointMigrationRevision": "202606260001",
            "graphStoreMigrationRevision": "202607230002",
            "durableDeploymentsRequirePostgres": True,
            "localStoreNonDurableOnly": True,
            "sameStorePassedToLangChainCreateAgent": True,
            "runtimeSchemaSetupForbidden": True,
            "existingSchemaAdoptionIdempotent": True,
            "frameworkMigrationVersionSensor": True,
            "startupFailureClosesDurableResources": True,
            "blankDatabaseUrlFailsBeforeEngineCreation": True,
            "runCheckpointIdentityPersisted": True,
            "durableCompletedStreamsRequireCheckpointProvenance": True,
            "durableCompletedInvocationsRequireCheckpointProvenance": True,
            "durableCompletedResumesRequireCheckpointProvenance": True,
            "resumePinsPersistedCheckpoint": True,
            "missingCheckpointIdentityBlocksResume": True,
            "checkpointVerifiedBeforeApproval": True,
        },
        "verificationSensors": [
            "uv run pytest tests/unit/test_container.py -q -k open_container",
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "'checkpoint_namespace or persisted_checkpoint_id or "
                "persisted_runtime_owner or durable_approval or "
                "durable_checkpoint'"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "resume_fails_closed_without_required_completed_checkpoint"
            ),
        ],
        "retentionSettings": [
            "retention.session.days",
            "retention.conversation.days",
            "retention.audit.days",
            "retention.metric.days",
            "retention.checkpoint.days",
        ],
        "policyOwner": "reactor.persistence",
        "missingDatabaseFailsClosed": True,
        "tenantScopedDeletion": True,
        "exportBeforeDeleteSupported": True,
        "stateHistoryRetentionAligned": True,
        "forkProvenanceRetained": True,
        "checkpointMetadataRedacted": True,
        "auditSurface": "retention_policy_api",
    }


def streaming_event_contract_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "runtime": "langgraph",
        "api": "astream_events",
        "version": LANGCHAIN_RAW_STREAM_EVENTS_VERSION,
        "eventTypes": sorted(STREAM_EVENT_TYPES),
        "upstreamEventFields": [
            "event",
            "name",
            "run_id",
            "parent_ids",
            "tags",
            "metadata",
            "data",
        ],
        "requiredPayloadFields": ["run_id", "sequence", "graph_node", "trace_id"],
        "sequenceMonotonic": True,
        "persistedReplay": True,
        "replayFilter": "run.stream.",
        "graphNodeRequired": True,
        "traceIdRequired": True,
        "tenantScopedPersistence": True,
        "langchainAgentInvoke": {
            "api": "ainvoke",
            "version": LANGCHAIN_AGENT_INVOKE_VERSION,
            "output": "GraphOutput",
            "interruptStatus": "interrupted",
            "rawInterruptPayloadExcluded": True,
            "publicMetadata": ["approval_status", "stop_reason"],
        },
        "langchainAgentStreaming": {
            "api": "astream_events",
            "version": LANGCHAIN_AGENT_STREAM_EVENTS_VERSION,
            "surface": "async_iterator",
            "interruptStatus": "interrupted",
            "publicEventType": "run.stream.approval",
            "publicPayloadFields": ["approval_status", "action_count", "approval_id"],
            "rawInterruptPayloadExcluded": True,
            "durableApprovalPersisted": True,
            "toolInputStoredOnlyInApprovalRow": True,
            "persistedApprovalIdReplayable": True,
            "approvalToolInputExcludedFromReplay": True,
        },
        "interruptLineage": {
            "status": "enforced",
            "event": "on_chain_stream",
            "version": LANGGRAPH_INTERRUPT_STREAM_EVENTS_VERSION,
            "runtimes": ["langgraph", "langchain_agent"],
            "requiredParentIds": "empty",
            "rootFramesOnly": True,
            "missingMalformedNestedFailClosed": True,
            "invalidLineageStopReason": "interrupt_stream_lineage_invalid",
            "malformedRootPayloadFailsClosed": True,
            "invalidPayloadCannotEmitTokens": True,
            "invalidPayloadStopReason": "interrupt_stream_payload_invalid",
            "singleApprovalActionRequired": True,
            "invalidActionsFailBeforeApprovalPersistence": True,
            "invalidActionsCannotEmitTokens": True,
            "invalidActionStopReason": "interrupt_stream_action_invalid",
            "invokeInvalidActionsFailClosed": True,
            "invokeInvalidActionStatusFailed": True,
            "invokeStreamInvalidActionParity": True,
            "invalidInvokeActionSkipsCheckpointRead": True,
            "nonRecoverableStreamsSkipCheckpointRead": True,
            "nonRecoverableInvocationsSkipCheckpointRead": True,
            "nestedInterruptCannotPersistApproval": True,
            "interruptPayloadOnlyApprovalSource": True,
            "pendingStateChunksIgnored": True,
            "verifiedInterruptCannotBeOverridden": True,
            "identicalInterruptFramesIdempotent": True,
            "conflictingInterruptFramesFailClosed": True,
            "conflictingInterruptApprovalPersistenceBlocked": True,
            "conflictStopReason": "interrupt_stream_conflict",
            "verificationSensors": [
                (
                    "uv run pytest tests/unit/test_langchain_agent.py "
                    "tests/unit/test_run_service.py "
                    "tests/integration/test_agent_streaming.py -q -k "
                    "'real_create_agent_v2_stream_exposes_interrupt_without_executing_tool or "
                    "run_langchain_agent_once_fails_closed_on_invalid_interrupt_actions or "
                    "stream_interrupts_requires_root_stream_lineage or "
                    "stream_fails_closed_on_invalid_langchain_v2_interrupt_lineage or "
                    "stream_fails_closed_on_malformed_root_interrupt_payload or "
                    "stream_fails_closed_on_invalid_interrupt_actions or "
                    "stream_persists_redacted_langchain_v2_interrupt or "
                    "stream_projection_ignores_pending_approval_without_interrupt or "
                    "stream_persists_redacted_native_langgraph_interrupt or "
                    "stream_fails_closed_on_conflicting_root_interrupts or "
                    "native_stream_fails_closed_on_conflicting_root_interrupts'"
                )
            ],
        },
        "publicPayloadRedaction": {
            "apiBoundary": "public_run_event_payload",
            "apiEndpoints": ["GET /v1/runs/{run_id}/events", "GET /v1/runs/{run_id}/stream-events"],
            "cliBoundary": "stream_event_summary",
            "redactionFunction": "redact_trace_payload",
            "secretShapedValuesRedacted": True,
            "sensitiveKeysDropped": True,
            "toolResultsSanitized": True,
            "rawPayloadsExcluded": True,
        },
        "terminalNextActions": terminal_next_actions_evidence(),
        "recommendedInterruptStreaming": {
            "recommendedApi": "stream_events",
            "recommendedAsyncApi": "astream_events",
            "version": LANGGRAPH_INTERRUPT_STREAM_EVENTS_VERSION,
            "projectionFields": ["approval_status", "action_count"],
            "resumeCommand": "Command(resume=...)",
            "threadIdRequired": True,
            "persistentCheckpointerRequired": True,
            "interruptPayloadsJsonSerializable": True,
        },
    }


def terminal_next_actions_evidence() -> dict[str, object]:
    run_id = "{run_id}"
    thread_id = "{thread_id}"
    checkpoint_ns = "{checkpoint_ns}"
    checkpoint_id = "{checkpoint_id}"
    payload = stream_completion_payload(
        RunResult(
            run_id=run_id,
            tenant_id="tenant_hardening",
            user_id="user_hardening",
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            status="completed",
            response="completed",
            provider="hardening",
            model="hardening",
        )
    )
    actions = [
        cast(Mapping[str, object], action)
        for action in cast(Sequence[object], payload.get("nextActions", []))
        if isinstance(action, Mapping)
    ]
    action_ids = [str(action["id"]) for action in actions if action.get("id")]
    commands = [str(action["command"]) for action in actions if action.get("command")]
    required_identity = {
        "sourceRunId": run_id,
        "threadId": thread_id,
        "checkpointNs": checkpoint_ns,
    }
    identity_fields = [
        field
        for field, value in required_identity.items()
        if actions and all(action.get(field) == value for action in actions)
    ]
    commands.append(
        f"reactor-runs fork {run_id} --checkpoint-ns {checkpoint_ns} "
        f"--checkpoint-id {checkpoint_id} --output table"
    )
    return {
        "includedInCompletedPayload": bool(actions),
        "actionIds": [*action_ids, "fork-checkpoint"],
        "commands": commands,
        "identityFields": identity_fields,
        "runtimePayloadVerified": (
            set(action_ids) == {"diagnose-run", "inspect-state-history", "replay-stream"}
            and identity_fields == list(required_identity)
        ),
    }


CommandRunner = Callable[[list[str], int], CommandResult]


def graph_topology_evidence() -> dict[str, object]:
    stages = build_reactor_graph_stages()
    subgraphs = build_reactor_graph_subgraphs(stages)
    return {
        "composition": "stage_subgraphs",
        "stageOrder": list(graph_stage_order(stages)),
        "nodeOrder": list(graph_node_order(stages)),
        "subgraphOrder": list(subgraph_stage_order(subgraphs)),
        "subgraphEdges": [
            {"source": source, "target": target}
            for source, target in subgraph_edge_order(subgraphs)
        ],
        "subgraphs": [
            {
                "name": subgraph.name,
                "entryNode": subgraph.entry_node,
                "exitNode": subgraph.exit_node,
                "checkpointMode": subgraph.checkpoint_mode,
                "nodes": [node.name for node in subgraph.stage.nodes],
                "nodeCount": len(subgraph.stage.nodes),
            }
            for subgraph in subgraphs
        ],
        "executionBoundary": {
            "wrapper": "JsonSafeReactorGraph",
            "productionAsyncOnly": True,
            "allowedApis": ["ainvoke", "astream", "astream_events"],
            "forbiddenApis": ["invoke", "stream"],
            "verificationSensors": [
                "uv run pytest tests/unit/test_agent_tool_state.py -q "
                "-k 'rejects_synchronous_invoke or rejects_synchronous_stream'"
            ],
            "covers": ["langgraph_sync_execution_is_blocked_at_graph_boundary"],
        },
    }


def tool_profile_budget_evidence() -> dict[str, object]:
    return {
        "recommendedActiveToolRange": {"min": 10, "max": 20},
        "defaultSource": "graph_profile_policy",
        "budgetFieldValidation": {
            "allowedFields": [
                "allowedRiskLevels",
                "allowedTools",
                "deniedTools",
                "maxTools",
            ],
            "unknownFieldsRejected": True,
            "metadataFailureReason": "invalid_metadata_budget",
            "runtimeSettingFailureReason": "invalid_runtime_setting",
            "metadataAndRuntimeSettingsSharedParser": True,
        },
        "researchForcedTool": {
            "profile": "research",
            "tool": "Rag:hybrid_search",
            "preflightBlocksWhenUnavailable": True,
            "runBlocksWhenUnavailable": True,
            "streamBlocksWhenUnavailable": True,
            "operatorAction": "allow_required_research_tool",
        },
        "resolvedMetadataFields": [
            "source",
            "budget",
            "configuredToolCount",
            "activeToolCount",
            "activeTools",
            "droppedToolCount",
            "droppedTools",
        ],
        "resumePolicyLifecycle": {
            "budgetReevaluated": True,
            "staleResolvedMetadataRemoved": True,
            "currentResolvedMetadataPersisted": True,
            "runtimeSettingsSnapshotSharedWithMiddleware": True,
            "settingsSnapshotCancellationPersisted": True,
            "verificationSensors": [
                "tests/unit/test_run_service.py::"
                "test_langchain_resume_replaces_stale_tool_profile_budget_evidence",
                "tests/unit/test_run_service.py::"
                "test_langchain_resume_uses_one_runtime_settings_snapshot",
                "tests/unit/test_run_service.py::"
                "test_langchain_resume_settings_snapshot_cancellation_persists_terminal_state",
            ],
        },
        "invokePolicyLifecycle": {
            "runtimeSettingsSnapshotSharedWithMiddleware": True,
            "verificationSensors": [
                "tests/unit/test_run_service.py::"
                "test_langchain_invoke_uses_one_runtime_settings_snapshot",
            ],
        },
        "preflightPolicyLifecycle": {
            "runtimeSettingsSnapshotSharedWithMiddleware": True,
            "verificationSensors": [
                "tests/unit/test_run_service.py::"
                "test_langchain_preflight_uses_one_runtime_settings_snapshot",
            ],
        },
        "streamPolicyLifecycle": {
            "runtimeSettingsSnapshotSharedWithMiddleware": True,
            "verificationSensors": [
                "tests/unit/test_run_service.py::"
                "test_langchain_stream_uses_one_runtime_settings_snapshot",
            ],
        },
        "sampleDroppedTools": [
            {"tool": "Dangerous:delete", "reason": "denied_tool", "riskLevel": "write"},
            {
                "tool": "Rag:admin_search",
                "reason": "tool_not_allowed",
                "riskLevel": "read",
            },
            {
                "tool": "Shell:run",
                "reason": "risk_level_not_allowed",
                "riskLevel": "admin",
            },
            {
                "tool": "Slack:post_message",
                "reason": "max_tools_exceeded",
                "riskLevel": "write",
            },
        ],
    }


def research_answer_contract_evidence() -> dict[str, object]:
    return {
        "profile": "research",
        "requiresCitationIds": True,
        "requiresSourceLabels": True,
        "citationStyle": "manifest_ids",
        "uncitedClaimsAllowed": False,
        "publicMetadataField": "research_plan.answerContract",
        "extractionMetadataField": "research_plan.answerExtraction",
        "tracksContentHashMismatches": True,
        "tracksMissingChunks": True,
        "fallbackResponseIncludesSources": True,
    }


def tool_invocation_lifecycle_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "store": "SqlAlchemyToolInvocationStore",
        "model": "ToolInvocationRecord",
        "idempotencyConstraint": "uq_tool_invocations_idempotency",
        "langchainClaimOperation": "insert_on_conflict_do_nothing",
        "langchainReplayPolicy": "reuse_succeeded_else_fail_closed",
        "nativeClaimOperation": "insert_on_conflict_do_nothing",
        "sharedExecutionPrimitive": "execute_tools_parallel",
        "pendingApprovalClaimTransition": "started_unbound_to_started_approved",
        "langchainCallIdentity": "InjectedToolCallId",
        "toolIdentityField": "catalog_id",
        "staleClaimTransition": "started_to_requires_reconciliation",
        "staleClaimOperatorEndpoint": "/v1/admin/tool-calls/reconcile-stale",
        "allowedStatuses": [
            status
            for status in (
                "started",
                "succeeded",
                "failed",
                "requires_reconciliation",
                "cancelled",
            )
            if status in TOOL_INVOCATION_STATUSES
        ],
        "requiredRecordFields": [
            "tenant_id",
            "run_id",
            "tool_id",
            "status",
            "idempotency_key",
            "request_checksum",
            "input_payload",
        ],
        "auditSurfaces": [
            "langgraph_tool_executor",
            "langchain_tool_adapter",
            "approval_pending",
            "approval_rejected",
            "run_tool_invocations_api",
            "admin_tool_calls_api",
            "admin_tool_reconciliation_api",
        ],
        "publicPayloadRedaction": True,
        "terminalPayloadsValidated": True,
        "langchainPreExecutionClaimRequired": True,
        "langchainConcurrentDuplicateBlocked": True,
        "langchainClaimFailureFailsClosed": True,
        "idempotencyClaimFailureLogsSafe": True,
        "langchainApprovalAuditFailureFailsClosed": True,
        "langchainSucceededResultReused": True,
        "nativePreExecutionClaimRequired": True,
        "nativeClaimFailureFailsClosed": True,
        "nativeUnresolvedClaimFailsClosed": True,
        "nativeSucceededResultReused": True,
        "sharedLangGraphLangChainClaimContract": True,
        "pendingApprovalClaimAtomic": True,
        "pendingApprovalAuditFailureFailsClosed": True,
        "rejectedApprovalAuditFailureFailsClosed": True,
        "pendingApprovalClaimApprovalBound": True,
        "pendingApprovalClaimChecksumBound": True,
        "pendingApprovalClaimMarkerRequired": True,
        "pendingApprovalReplayKeepsInvocationId": True,
        "runCancellationCancelsUnexecutedApprovalClaims": True,
        "requestChecksumStableAcrossLifecycle": True,
        "langchainCallIdentityHiddenFromModelSchema": True,
        "langchainDistinctCallsPreserved": True,
        "langchainSameCallReplayStable": True,
        "completionAuditFailureRequiresReconciliation": True,
        "completionAuditFailureSkipsSuccessCache": True,
        "staleClaimAutoReplayForbidden": True,
        "staleClaimTenantScoped": True,
        "staleClaimTransitionAudited": True,
        "staleClaimResponseRawFree": True,
        "pendingApprovalStatus": "started",
        "terminalStatuses": ["succeeded", "failed", "cancelled"],
        "verificationSensors": [
            (
                "uv run pytest tests/unit/test_agent_graph_policy.py -q -k "
                "'fails_closed_when_pending_approval_audit_cannot_be_persisted or "
                "fails_closed_when_rejected_approval_audit_cannot_be_persisted or "
                "rebinds_pending_approval_audit_row_before_resumed_execution or "
                "reuses_durable_idempotent_tool_result_before_handler_execution or "
                "fails_closed_when_durable_idempotency_claim_is_unavailable or "
                "fails_closed_for_unresolved_durable_idempotency_claim'"
            ),
            (
                "uv run pytest tests/unit/test_tool_execution.py -q -k "
                "'idempotency_claim_failure_logs_safely_and_skips_execution or "
                "external_side_effect_requires_reconciliation_when_completion_audit_fails'"
            ),
            (
                "uv run pytest tests/unit/test_tool_invocation_store.py -q -k "
                "'approved_pending_tool_invocation_claim or "
                "tool_invocation_claim_insert_is_conflict_safe'"
            ),
            (
                "uv run pytest tests/unit/test_langchain_tool_adapter.py -q -k "
                "'reuses_succeeded_idempotent_result or "
                "fails_closed_when_approval_audit_cannot_be_persisted or "
                "fails_closed_for_unresolved_idempotency_claim or "
                "fails_closed_when_idempotency_store_is_unavailable'"
            ),
            (
                "uv run pytest tests/unit/test_run_store.py tests/unit/test_run_service.py -q "
                "-k 'cancel_pending_approval_tool_invocations_query_excludes_executing_claims "
                "or approval_event_persistence_cancellation_records_cancelled'"
            ),
        ],
        "covers": [
            "native_tool_claim_precedes_handler_execution",
            "native_claim_failure_skips_handler",
            "native_unresolved_claim_skips_handler",
            "native_succeeded_result_reused_without_handler",
            "langgraph_and_langchain_share_durable_execution_primitive",
            "langchain_approval_audit_failure_blocks_model_result",
            "idempotency_claim_failure_logs_exclude_exception_details",
            "completion_audit_failure_requires_reconciliation",
            "completion_audit_failure_skips_success_cache",
            "pending_approval_audit_failure_blocks_interrupt",
            "rejected_approval_audit_failure_blocks_completion",
            "pending_approval_claim_is_atomic_and_approval_bound",
            "pending_approval_claim_requires_request_checksum_and_marker",
            "pending_approval_replay_preserves_invocation_identity",
            "run_cancellation_cancels_only_unexecuted_approval_claims",
        ],
    }


def durable_run_queue_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "store": "SqlAlchemyDurableStore",
        "queueModel": "RunQueue",
        "deadLetterModel": "DeadLetterJob",
        "leasedStatuses": ["queued", "retryable_failed"],
        "expiredLeaseAction": "retry_or_dead_letter",
        "deadLetterReason": "run_queue_lease_attempts_exhausted",
        "fencingTokenRequired": True,
        "deadLetterPayloadFields": [
            "attempt",
            "maxAttempts",
            "leaseOwner",
            "fencingToken",
            "queuePayload",
        ],
        "diagnosticsSurface": {
            "status": "verified",
            "apiPaths": [
                "/api/admin/durable-queue/diagnostics",
                "/v1/admin/durable-queue/diagnostics",
            ],
            "dashboardFacet": "ops.dashboard.durableQueue",
            "tenantScoped": True,
            "missingStoreStatus": "unavailable",
            "requiredCountFields": [
                "queueStatusCounts",
                "queueBacklog",
                "leasedCount",
                "deadLetterCount",
            ],
            "releaseReviewFields": [
                "leaseRecovery",
                "deadLetterReason",
                "fencingTokenRequired",
            ],
            "remediationActions": [
                {
                    "name": "release_expired_leases",
                    "apiPaths": [
                        "/api/admin/durable-queue/release-expired",
                        "/v1/admin/durable-queue/release-expired",
                    ],
                    "permission": "settings:write",
                    "auditCategory": "durable_queue",
                    "auditAction": "UPDATE",
                    "resourceType": "run_queue",
                    "resourceId": "release_expired",
                }
            ],
        },
        "scheduledJobFailureBoundary": {
            "status": "verified",
            "worker": "SchedulerWorker",
            "executionRecord": "ScheduledJobExecutionRecord",
            "deadLetterRecord": "ScheduledJobDeadLetterRecord",
            "safeFailureCode": "scheduled_job_execution_failed",
            "exceptionDetailsExcludedFrom": [
                "execution.result",
                "job.last_result",
                "dead_letter.reason",
                "dead_letter.result",
            ],
            "retrySemanticsPreserved": True,
            "verificationSensors": [
                "uv run pytest tests/unit/test_scheduler_worker.py -q "
                "-k dead_letters_after_retry_exhaustion"
            ],
            "covers": ["scheduler_failure_uses_safe_durable_error_code"],
        },
    }


def outbox_inbox_lifecycle_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "store": "SqlAlchemyDurableStore",
        "outboxModel": "OutboxEvent",
        "inboxModel": "InboxEvent",
        "idempotencyModel": "IdempotencyRecord",
        "dispatcher": "OutboxDispatcher",
        "claimStrategy": "postgres_for_update_skip_locked",
        "outboxStatuses": [
            "pending",
            "dispatching",
            "dispatched",
            "retryable_failed",
            "dead_lettered",
        ],
        "inboxStatuses": ["received", "processing", "processed", "ignored", "failed"],
        "replayableDestinations": [
            "a2a.task.created",
            "a2a.task.updated",
            "slack.event_callback",
            "slack.slash_command",
            "slack.block_action",
        ],
        "idempotencyConstraint": "uq_outbox_events_idempotency",
        "inboxDeduplicationConstraint": "uq_inbox_events_source_event",
        "leaseFields": ["lease_owner", "lease_expires_at", "attempt", "max_attempts"],
        "sideEffectsBeforeOutboxForbidden": True,
        "incomingEventsPersistedBeforeProcessing": True,
        "atLeastOnceDeliveryAssumed": True,
        "dispatcherDeadLettersUnsupportedRoutes": True,
        "retryableFailuresReclaimable": True,
        "staleLeaseOwnerCannotDispatch": True,
        "workerFailureErrorDetailsExcluded": True,
        "payloadReplayable": True,
        "verificationSensors": [
            "uv run pytest tests/unit/test_outbox_dispatcher.py -q "
            "-k 'marks_retryable_then_dead_letter or preserves_worker_retry_after_seconds'"
        ],
        "covers": ["outbox_worker_failure_uses_safe_durable_error_code"],
    }


def redis_coordination_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "client": "redis.asyncio.Redis",
        "healthCheck": "check_redis",
        "productionMultiReplicaRequired": True,
        "ephemeralOnly": True,
        "durableStateForbidden": True,
        "primaryCheckpointStoreForbidden": "langgraph-checkpoint-redis",
        "allowedUses": [
            "rate_limit_counters",
            "lock_tokens",
            "pubsub_wakeups",
            "ttl_cache_entries",
        ],
        "pubsubDelivery": "at_most_once",
        "rateLimitFailureMode": "fail_closed_by_default",
        "clientClosedAfterPing": True,
        "runLifecyclePublisherClosedOnContainerClose": True,
        "slackUserRateLimiterClosedOnContainerClose": True,
    }


def context_manifest_evidence() -> dict[str, object]:
    return {
        "sections": [
            {
                "name": "session_memory",
                "source_type": "memory",
                "content_checksum": "sha256:memory",
                "metadata": {"memory_count": 1, "skipped_memory_count": 0},
            },
            {
                "name": "rag_context",
                "source_type": "rag",
                "content_checksum": "sha256:rag",
                "metadata": {
                    "chunk_count": 2,
                    "cited_chunk_count": 1,
                    "uncited_chunk_count": 1,
                    "citation_count": 1,
                    "citations": [
                        {
                            "citation_id": "hardening_doc:0",
                            "source_uri": "docs/architecture/agent-harness-operating-model.md",
                            "content_hash": "sha256:hardening_doc_0",
                            "acl_hash": "acl_hash_only",
                        }
                    ],
                },
            },
            {
                "name": "tool_outputs",
                "source_type": "tool",
                "content_checksum": "sha256:tool_outputs",
                "metadata": {
                    "output_count": 1,
                    "sanitized_count": 1,
                    "findings": ["canary_secret"],
                },
            },
        ]
    }


def context_manifest_diagnostics_evidence() -> dict[str, object]:
    manifest = ContextManifest(
        sections=[
            ContextSection(
                "session_memory",
                "User prefers grounded answers.",
                source_type="memory",
                metadata={
                    "memory_count": 1,
                    "skipped_memory_count": 0,
                    "skipped_status_counts": {},
                    "status_counts": {"active": 1},
                    "memoryAdmissionPolicy": {
                        "activeOnly": True,
                        "missingStatusExcluded": True,
                        "tombstonedExcluded": True,
                        "supersededExcluded": True,
                    },
                },
            ),
            ContextSection(
                "rag_context",
                "Reactor requires grounded citations.",
                source_type="rag",
                tainted=True,
                metadata={
                    "chunk_count": 2,
                    "cited_chunk_count": 1,
                    "uncited_chunk_count": 1,
                    "poisoned_chunk_count": 1,
                    "poisoning_reasons": ["prompt_injection"],
                    "citation_count": 1,
                    "citations": [
                        {
                            "citation_id": "hardening_doc:0",
                            "source_uri": "docs/architecture/agent-harness-operating-model.md",
                            "content_hash": "sha256:hardening_doc_0",
                            "acl_hash": "acl_hash_only",
                        }
                    ],
                    "ragGroundingPolicy": {
                        "citationTracking": "required",
                        "uncitedChunksTracked": True,
                        "aclEvidence": "acl_hash_only",
                        "rawAclMetadataVisible": False,
                    },
                },
            ),
        ]
    )
    return context_manifest_diagnostics(manifest.as_manifest())


def langchain_middleware_policy_evidence() -> dict[str, object]:
    policy = default_langchain_middleware_policy(Settings(max_tool_calls=10))
    return {
        "status": "applied",
        "source": "default_code_policy",
        "policy": langchain_middleware_policy_metadata(policy),
        "policyFieldValidation": {
            "unknownPolicyFieldsRejected": True,
            "unknownPiiRuleFieldsRejected": True,
            "metadataFailureReason": "invalid_metadata_policy",
            "runtimeSettingFailureReason": "invalid_runtime_setting",
            "invokeStreamSharedResolver": True,
            "invokeRuntimeSettingsSnapshotShared": True,
            "preflightRuntimeSettingsSnapshotShared": True,
            "streamRuntimeSettingsSnapshotShared": True,
            "resumePolicyReevaluated": True,
            "resumeStaleEvidenceRemoved": True,
            "resumeRuntimeSettingsSnapshotShared": True,
            "resumeSettingsSnapshotCancellationPersisted": True,
            "resumeSettingsSnapshotFailureFailsClosed": True,
            "resumeMiddlewareLookupCancellationPersisted": True,
            "verificationSensors": [
                "tests/unit/test_langchain_middleware.py::"
                "test_langchain_middleware_policy_from_mapping_rejects_invalid_values",
                "tests/unit/test_run_service.py::"
                "test_run_service_ignores_invalid_metadata_langchain_middleware_policy",
                "tests/unit/test_run_service.py::"
                "test_run_service_ignores_invalid_langchain_middleware_runtime_setting",
                "tests/unit/test_run_service.py::"
                "test_langchain_invoke_uses_one_runtime_settings_snapshot",
                "tests/unit/test_run_service.py::"
                "test_langchain_preflight_uses_one_runtime_settings_snapshot",
                "tests/unit/test_run_service.py::"
                "test_langchain_stream_uses_one_runtime_settings_snapshot",
                "tests/unit/test_run_service.py::"
                "test_langchain_resume_removes_stale_middleware_policy_evidence",
                "tests/unit/test_run_service.py::"
                "test_langchain_resume_refreshes_middleware_policy_from_tenant_setting",
                "tests/unit/test_run_service.py::"
                "test_langchain_resume_uses_one_runtime_settings_snapshot",
                "tests/unit/test_run_service.py::"
                "test_langchain_resume_settings_snapshot_cancellation_persists_terminal_state",
                "tests/unit/test_run_service.py::"
                "test_langchain_resume_settings_snapshot_failure_fails_closed",
                "tests/unit/test_run_service.py::"
                "test_langchain_resume_middleware_lookup_cancellation_persists_terminal_state",
            ],
        },
        "retryExceptionPolicy": {
            "predicate": "is_transient_retry_exception",
            "appliesTo": [
                "ModelRetryMiddleware",
                "ToolRetryMiddleware",
                "invoke_chat_model_with_retry",
            ],
            "transientFamilies": [
                "timeout",
                "connection",
                "rate_limit",
                "server_error",
            ],
            "httpStatusPolicy": {
                "explicit": [408, 409, 425, 429],
                "serverRange": "500-599",
            },
            "permanentFailuresNotRetried": True,
            "sdkCoverage": [
                "openai",
                "anthropic",
                "google-genai",
            ],
            "verificationSensors": [
                "tests/unit/test_langchain_middleware.py::"
                "test_retry_exception_policy_uses_transient_failures_only",
                "tests/unit/test_langchain_middleware.py::"
                "test_model_retry_does_not_repeat_permanent_validation_error",
                "tests/unit/test_langchain_middleware.py::"
                "test_model_retry_is_exhausted_per_model_before_fallback",
                "tests/unit/test_langchain_middleware.py::"
                "test_tool_retry_retries_allowlisted_read_tool",
                "tests/unit/test_agent_graph_policy.py::"
                "test_graph_model_node_does_not_retry_permanent_chat_model_failure",
            ],
        },
        "retryBudgetOwnership": {
            "owner": "reactor_policy",
            "providerInternalMaxRetries": 0,
            "langchainAgentMiddleware": "ModelRetryMiddleware",
            "appliesTo": [
                "primary_model",
                "fallback_models",
                "explicit_langgraph_model",
            ],
            "nestedProviderRetriesDisabled": True,
            "middlewareEvidencePlanning": "side_effect_free",
            "providerInitializationOwner": "agent_runtime",
            "verificationSensors": [
                "tests/unit/test_provider_chat_models.py::"
                "test_langchain_chat_model_factory_delegates_to_init_chat_model",
                "tests/unit/test_langchain_agent.py::"
                "test_resolve_langchain_agent_models_uses_one_factory_for_primary_and_fallbacks",
                "tests/unit/test_langchain_agent.py::"
                "test_build_langchain_agent_passes_fallback_models_to_middleware",
                "tests/unit/test_agent_graph_policy.py::"
                "test_graph_model_node_retries_transient_chat_model_failure",
                "tests/unit/test_langchain_agent.py::"
                "test_planned_langchain_middleware_metadata_matches_actual_chain",
                "tests/unit/test_run_service.py::"
                "test_run_service_stream_delegates_fallback_model_initialization_to_runtime",
            ],
        },
        "toolRetryFailureBoundary": {
            "middleware": "ToolRetryMiddleware",
            "onFailure": "fixed_labeled_message",
            "modelVisiblePrefix": "[tool_output:data]",
            "rawExceptionVisible": False,
            "retryableRiskLevels": ["read"],
            "approvalRequiredToolsRetryable": False,
            "sideEffectExceptionStatus": "requires_reconciliation",
            "sideEffectTimeoutStatus": "requires_reconciliation",
            "verificationSensors": [
                "tests/unit/test_langchain_middleware.py::"
                "test_tool_retry_failure_hides_raw_exception_from_model",
                "tests/unit/test_langchain_middleware.py::"
                "test_tool_retry_does_not_repeat_external_side_effect_without_durable_store",
                "tests/unit/test_langchain_middleware.py::"
                "test_tool_retry_retries_allowlisted_read_tool",
                "tests/unit/test_langchain_tool_adapter.py::"
                "test_langchain_external_side_effect_timeout_requires_reconciliation",
            ],
        },
    }


def langchain_middleware_chain_evidence() -> dict[str, object]:
    settings = Settings(max_tool_calls=10)
    middleware = build_langchain_agent_middleware(settings)
    return langchain_middleware_chain_metadata(middleware)


def context_management_lifecycle_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "framework": "langchain_middleware",
        "summarizationMiddleware": "SummarizationMiddleware",
        "contextEditingMiddleware": "ContextEditingMiddleware",
        "toolSelectionMiddleware": "LLMToolSelectorMiddleware",
        "providerToolSearchMiddleware": "ProviderToolSearchMiddleware",
        "contextManifestRequired": True,
        "contentChecksumsRequired": True,
        "toolCallPairPreservationRequired": True,
        "tenantPolicyBeforeContextMutation": True,
        "auditRecordsContextMutations": True,
        "rawContextNotInReleaseEvidence": True,
        "activeToolBudgetEnforced": True,
        "selectionReasonsAudited": True,
    }


def usage_cost_lifecycle_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "ledger": "UsageLedgerRecord",
        "store": "SqlAlchemyUsageLedgerStore",
        "frameworkUsageSource": "LangChain usage_metadata",
        "streamUsageSource": "LangChain v2 data.chunk usage_metadata",
        "traceUsageSource": "LangSmith token_and_cost_tracking",
        "metricsSurface": "reactor_model_cost_usd_total",
        "requiredRecordFields": [
            "tenant_id",
            "run_id",
            "provider",
            "model",
            "step_type",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "estimated_cost_usd",
        ],
        "adminReviewSurfaces": [
            "/api/admin/token-cost/by-session",
            "/v1/admin/token-cost/by-session",
            "/api/admin/token-cost/daily",
            "/v1/admin/token-cost/daily",
            "/api/admin/token-cost/top-expensive",
            "/v1/admin/token-cost/top-expensive",
            "/api/admin/tenant/cost",
            "/v1/admin/tenant/cost",
        ],
        "tenantScoped": True,
        "runScoped": True,
        "sessionScoped": True,
        "modelBreakdownRequired": True,
        "negativeCostRejected": True,
        "tokenTotalsValidated": True,
        "totalTokensMatchesBreakdown": True,
        "zeroCostRecorded": True,
        "estimatedCostQuantized": True,
        "metricsRecorded": True,
        "providerUsagePreferred": True,
        "estimatedUsageFallbackOnly": True,
        "cacheAndReasoningTokensPreserved": True,
        "agentEvalReplayBoundary": {
            "runtime": "RunService",
            "usageLedgerAttached": True,
            "toolPolicyAttached": True,
            "components": [
                "usage_ledger",
                "tool_provider",
                "tool_handler",
                "tool_invocation_store",
                "builtin_tool_specs",
            ],
            "verificationSensors": [
                "tests/integration/test_eval_api.py::"
                "test_eval_replay_uses_reactor_policy_and_usage_components"
            ],
        },
        "runsApiBoundary": {
            "factory": "build_run_service",
            "usageLedgerAttached": True,
            "verificationSensors": [
                "tests/integration/test_runs_api.py::"
                "test_create_run_api_uses_configured_usage_ledger"
            ],
        },
    }


def checkpoint_provenance_evidence() -> dict[str, object]:
    return {
        "source": "checkpoint_fork",
        "forkedFromRunId": "run_hardening_source",
        "forkedFromThreadId": "thread_hardening_source",
        "forkedFromCheckpointNs": "reactor-hardening",
        "forkedFromCheckpointId": "checkpoint_hardening_source",
        "forkTargetThreadId": "thread_hardening_target",
        "forkTargetCheckpointNs": "reactor-hardening-fork",
        "replayCoverage": {
            "status": "verified",
            "runtimes": [
                "langgraph",
                "langchain_agent",
                "langgraph_stream",
                "langchain_agent_stream",
            ],
            "configurableKeys": ["thread_id", "checkpoint_ns", "checkpoint_id"],
            "ignoredReasons": ["missing_checkpoint_id", "fork_target_mismatch"],
            "appliedMetadataFields": [
                "status",
                "source",
                "requestedCheckpointId",
                "checkpointId",
                "materialization",
                "targetThreadId",
                "targetCheckpointNs",
            ],
        },
        "storageSemantics": {
            "status": "verified",
            "logicalIdentity": ["tenant_id", "thread_id", "checkpoint_ns"],
            "physicalThreadKey": "sha256_v1",
            "rootCheckpointNs": "",
            "sourceRead": "BaseCheckpointSaver.aget_tuple",
            "targetWrite": "BaseCheckpointSaver.aput",
            "tenantScoped": True,
            "targetMustBeEmpty": True,
            "pendingWritesRejected": True,
            "sourceReadIdentityVerified": True,
            "sourcePayloadIdentityVerified": True,
            "targetWriteScopeVerified": True,
            "trustedCapability": "TrustedCheckpointFork",
            "userMetadataCannotAuthorizeReplay": True,
            "typedChatNamespaceAccepted": True,
            "userMetadataCannotOverrideNamespace": True,
            "profileMetadataUsesDurableNamespace": True,
            "profileCannotOverrideDurableNamespace": True,
            "profileNamespaceStateField": "profile_checkpoint_ns",
            "profileNamespaceSource": "resolved_durable_checkpoint_ns",
            "streamingNamespaceTargets": [
                "run_store",
                "checkpoint_fork",
                "langgraph_config",
                "langchain_agent",
                "run_result",
                "terminal_actions",
            ],
            "executionContractFields": ["runtime", "graphProfile"],
            "executionContractMatchRequired": True,
            "materializationModes": ["pinned_source_scope", "copied_to_target_scope"],
            "failClosedReasons": [
                "invalid_fork_provenance",
                "checkpointer_unavailable",
                "source_checkpoint_not_found",
                "source_checkpoint_scope_mismatch",
                "source_checkpoint_id_mismatch",
                "source_checkpoint_payload_id_mismatch",
                "invalid_source_checkpoint",
                "source_checkpoint_has_pending_writes",
                "target_checkpoint_scope_not_empty",
                "target_checkpoint_write_scope_mismatch",
                "target_checkpoint_write_failed",
                "checkpoint_store_error",
                "fork_execution_contract_mismatch",
            ],
        },
        "diagnosticsSurface": {
            "status": "verified",
            "forkApiPaths": ["/v1/runs/{run_id}/fork"],
            "stateHistoryApiPaths": [
                "/api/admin/debug/state-history/{run_id}",
                "/v1/admin/debug/state-history/{run_id}",
            ],
            "diagnosticsApiPaths": [
                "/api/admin/checkpoints/diagnostics",
                "/v1/admin/checkpoints/diagnostics",
            ],
            "permission": "settings:read",
            "trustedMetadataKeys": [
                "source",
                "forkedFromRunId",
                "forkedFromThreadId",
                "forkedFromCheckpointNs",
                "forkedFromCheckpointId",
                "forkTargetThreadId",
                "forkTargetCheckpointNs",
                "forkedFromExecutionContract",
            ],
            "userMetadataStrippedKeys": [
                "source",
                "checkpointId",
                "checkpoint_id",
                "forkedFromRunId",
                "forkedFromThreadId",
                "forkedFromCheckpointNs",
                "forkedFromCheckpointId",
                "forkTargetThreadId",
                "forkTargetCheckpointNs",
                "forkedFromExecutionContract",
            ],
        },
    }


def structured_output_evidence() -> dict[str, object]:
    return {
        "format": "JSON",
        "schemaSource": "metadata.responseSchema",
        "strategy": "schema_passthrough",
        "langchainStrategies": [
            "ProviderStrategy",
            "ToolStrategy",
            "schema_type",
            "none",
        ],
        "reactorStrategies": [
            "schema_passthrough",
            "json_object_schema",
            "reactor_boundary",
        ],
        "enforcement": "langchain_response_format_and_reactor_boundary",
        "policyFailureStatus": "rejected",
        "blockedResponseEmittedAsSuccessToken": False,
        "nativeStreamFinalPolicyOutputHonored": True,
        "nativeStreamRootFinalOutputOnly": True,
        "nativeStreamInvalidLineageFailClosed": True,
        "conflictingRootNativeGraphResultsFailClosed": True,
        "identicalRootNativeGraphResultReplayAllowed": True,
        "nativeGraphResultConflictStopReason": "native_graph_result_stream_conflict",
        "nativeStructuredStreamResponseHonored": True,
        "invokeStreamStructuredResponseParity": True,
        "nativeStructuredResponseAuthoritativeWhenPresent": True,
        "emptyStructuredResponseFailsClosed": True,
        "unserializableStructuredResponseFailsClosed": True,
        "serializationFailureErrorCode": "STRUCTURED_RESPONSE_SERIALIZATION_FAILED",
        "rootStructuredStreamResponseOnly": True,
        "nestedStructuredStreamResponsesIgnored": True,
        "missingStructuredStreamParentIdsFailClosed": True,
        "conflictingRootStructuredResponsesFailClosed": True,
        "identicalRootStructuredResponseReplayAllowed": True,
        "structuredResponseConflictStopReason": "structured_response_stream_conflict",
        "applicationOwnedContextManifest": True,
        "schemaImpliesJsonFormat": True,
        "verificationSensors": [
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "'native_stream_uses_final_graph_policy_output or "
                "native_stream_fails_closed_on_conflicting_root_graph_results or "
                "native_stream_ignores_nested_final_policy_output or "
                "native_graph_stream_result_requires_v2_root_lineage'"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "'stream_uses_langchain_native_structured_response or "
                "stream_fails_closed_on_conflicting_root_structured_responses or "
                "stream_rejects_empty_native_structured_response or "
                "stream_ignores_nested_structured_response or "
                "stream_ignores_structured_response_without_parent_ids'"
            ),
            (
                "uv run pytest tests/integration/test_api.py "
                "tests/integration/test_chat_api.py -q -k context_manifest"
            ),
            (
                "uv run pytest tests/integration/test_api.py -q "
                "-k structured_output_diagnostics_treats_schema_only_contract_as_json"
            ),
        ],
        "covers": [
            "native_langgraph_final_result_requires_root_event",
            "native_langgraph_invalid_lineage_fails_closed",
            "nested_native_stream_result_cannot_override_root_output",
            "conflicting_root_native_graph_results_fail_closed",
            "identical_root_native_graph_result_replay_allowed",
            "langchain_native_structured_response_drives_stream_result",
            "langchain_invoke_and_stream_structured_response_precedence_match",
            "empty_native_structured_response_uses_token_fallback",
            "langchain_structured_stream_response_requires_root_event",
            "nested_structured_stream_response_cannot_override_root_output",
            "missing_structured_stream_parent_ids_fail_closed",
            "conflicting_root_structured_responses_fail_closed",
            "identical_root_structured_response_replay_allowed",
            "public_request_context_manifest_cannot_authorize_citations",
            "explicit_schema_implies_json_format_without_response_format",
        ],
        "citationBoundary": {
            "status": "enforced",
            "source": "context_manifest",
            "runtimes": ["langgraph", "langchain_agent", "langchain_agent_stream"],
            "requiredMetadata": [
                "structured_output_allowed_citation_ids",
                "structured_output_citation_policy",
                "structured_output_citation_count",
            ],
        },
        "repairBoundary": {
            "status": "enforced",
            "maxInvalidInputChars": StructuredResponseRepairer.MAX_REPAIR_INPUT_CHARS,
            "rawInvalidInputIncluded": False,
        },
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
    }


def build_default_hardening_suite(
    *,
    uv_bin: str = "uv",
    python_bin: str = "python",
) -> HardeningSuite:
    def uv_step(
        step_id: str,
        description: str,
        command: Sequence[str],
        tags: set[str],
        timeout_seconds: int = 120,
    ) -> HardeningSuiteStep:
        return HardeningSuiteStep(
            id=step_id,
            description=description,
            command=tuple(command),
            tags=frozenset(tags),
            timeout_seconds=timeout_seconds,
        )

    template_steps = (
        uv_step(
            "uv-lock",
            "Dependency lock file is current",
            ("{uv}", "lock", "--check"),
            {"static", "dependencies"},
            60,
        ),
        uv_step(
            "ruff-format",
            "Source formatting is stable",
            ("{uv}", "run", "ruff", "format", "--check"),
            {"static", "format"},
            120,
        ),
        uv_step(
            "ruff-check",
            "Lint and security rules pass",
            ("{uv}", "run", "ruff", "check"),
            {"static", "lint", "security"},
            120,
        ),
        uv_step(
            "pyright",
            "Strict type checking passes",
            ("{uv}", "run", "pyright"),
            {"static", "types"},
            180,
        ),
        uv_step(
            "pytest-unit",
            "Unit suite passes",
            ("{uv}", "run", "pytest", "tests/unit", "-q"),
            {"pytest", "unit"},
            240,
        ),
        uv_step(
            "pytest-rag-documents-workflow",
            "RAG documents ask, eval apply, and feedback review workflow sensor passes",
            (
                "{uv}",
                "run",
                "pytest",
                "tests/unit/test_documents_cli.py",
                "tests/unit/test_eval_regression_suite_apply.py",
                "-q",
                "-k",
                (
                    "asks_chat_with_retrieved_rag_context or ask_can_render_summary_output "
                    "or documents_ask"
                ),
            ),
            {"pytest", "hardening", "rag", "documents", "eval", "feedback"},
            120,
        ),
        uv_step(
            "pytest-memory-lifecycle",
            "Memory lifecycle CLI and shared gate action sensor passes",
            (
                "{uv}",
                "run",
                "pytest",
                "tests/unit/test_memory_cli.py",
                "tests/unit/test_memory_lifecycle_actions.py",
                "-q",
                "-k",
                MEMORY_LIFECYCLE_TEST_SELECTOR,
            ),
            {"pytest", "hardening", "memory"},
            120,
        ),
        uv_step(
            "pytest-redteam",
            "Red-team corpus guard regression suite passes",
            ("{uv}", "run", "pytest", "tests/unit/test_redteam_corpus.py", "-q"),
            {"pytest", "hardening", "redteam"},
            120,
        ),
        uv_step(
            "pytest-hardening",
            "Hardening suite passes",
            ("{uv}", "run", "pytest", "tests/hardening", "-q"),
            {"pytest", "hardening"},
            240,
        ),
        uv_step(
            "pytest-integration",
            "Integration suite passes",
            ("{uv}", "run", "pytest", "tests/integration", "-q"),
            {"pytest", "integration"},
            360,
        ),
        scenario_step(
            "scenario-agent-effect-canary",
            "scripts/dev/scenarios/agent-effect-canary.json",
            timeout_seconds=120,
        ),
        scenario_step(
            "scenario-user-activity-matrix",
            "scripts/dev/scenarios/user-activity-matrix.json",
            timeout_seconds=120,
        ),
        scenario_step(
            "scenario-integration-golden",
            "scripts/dev/scenarios/integration-golden-scenarios.json",
            timeout_seconds=120,
        ),
    )
    return HardeningSuite(
        uv_bin=uv_bin,
        python_bin=python_bin,
        steps=tuple(
            materialize_step(step, uv_bin=uv_bin, python_bin=python_bin) for step in template_steps
        ),
    )


def scenario_step(
    step_id: str,
    scenario_file: str,
    *,
    timeout_seconds: int,
) -> HardeningSuiteStep:
    report_name = step_id.replace("scenario-", "scenario-report-", 1)
    return HardeningSuiteStep(
        id=step_id,
        description=f"Scenario corpus expands: {scenario_file}",
        command=(
            "{uv}",
            "run",
            "{python}",
            "scripts/dev/validate-scenario-matrix.py",
            "--scenario-file",
            scenario_file,
            "--validate-only",
            "--report-file",
            f"{gettempdir()}/{report_name}.json",
        ),
        tags=frozenset({"scenario", "eval", "hardening"}),
        timeout_seconds=timeout_seconds,
    )


def render_command(
    step: HardeningSuiteStep,
    *,
    uv_bin: str = "",
    python_bin: str = "",
) -> list[str]:
    return [
        part.replace("{uv}", uv_bin or "uv").replace(
            "{python}",
            python_bin or "python",
        )
        for part in step.command
    ]


def materialize_step(
    step: HardeningSuiteStep,
    *,
    uv_bin: str,
    python_bin: str,
) -> HardeningSuiteStep:
    return HardeningSuiteStep(
        id=step.id,
        description=step.description,
        command=tuple(render_command(step, uv_bin=uv_bin, python_bin=python_bin)),
        tags=step.tags,
        timeout_seconds=step.timeout_seconds,
    )


def run_hardening_suite(
    suite: HardeningSuite,
    *,
    include_tags: set[str],
    exclude_tags: set[str],
    dry_run: bool,
    report_file: Path,
    command_runner: CommandRunner | None = None,
) -> HardeningSuiteReport:
    selected_steps = select_steps(suite.steps, include_tags=include_tags, exclude_tags=exclude_tags)
    reports: list[HardeningSuiteStepReport] = []
    runner = command_runner or run_command

    for step in selected_steps:
        command = tuple(render_command(step, uv_bin=suite.uv_bin, python_bin=suite.python_bin))
        if dry_run:
            reports.append(step_report(step, command, "skipped", 0, 0))
            continue
        result = runner(list(command), step.timeout_seconds)
        reports.append(
            step_report(
                step,
                command,
                "passed" if result.exit_code == 0 else "failed",
                result.exit_code,
                result.duration_ms,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        )
        if result.exit_code != 0:
            break

    report = HardeningSuiteReport(
        generated_at_ms=now_ms(),
        dry_run=dry_run,
        summary=build_summary(reports),
        steps=reports,
        artifact=str(report_file),
        include_tags=frozenset(include_tags),
        exclude_tags=frozenset(exclude_tags),
    )
    write_report(report_file, report)
    return report


def select_steps(
    steps: Sequence[HardeningSuiteStep],
    *,
    include_tags: set[str],
    exclude_tags: set[str],
) -> list[HardeningSuiteStep]:
    selected: list[HardeningSuiteStep] = []
    for step in steps:
        if include_tags and not (step.tags & include_tags):
            continue
        if exclude_tags and (step.tags & exclude_tags):
            continue
        selected.append(step)
    return selected


def run_command(command: list[str], timeout_seconds: int) -> CommandResult:
    started = now_ms()
    completed = subprocess.run(  # noqa: S603
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return CommandResult(
        exit_code=completed.returncode,
        duration_ms=now_ms() - started,
        stdout=completed.stdout[-4000:],
        stderr=completed.stderr[-4000:],
    )


def step_report(
    step: HardeningSuiteStep,
    command: tuple[str, ...],
    status: str,
    exit_code: int,
    duration_ms: int,
    *,
    stdout: str = "",
    stderr: str = "",
) -> HardeningSuiteStepReport:
    return HardeningSuiteStepReport(
        id=step.id,
        description=step.description,
        command=command,
        tags=tuple(sorted(step.tags)),
        status=status,
        exit_code=exit_code,
        duration_ms=duration_ms,
        stdout=stdout,
        stderr=stderr,
    )


def build_summary(reports: Sequence[HardeningSuiteStepReport]) -> dict[str, int]:
    return {
        "total": len(reports),
        "passed": sum(1 for item in reports if item.status == "passed"),
        "failed": sum(1 for item in reports if item.status == "failed"),
        "skipped": sum(1 for item in reports if item.status == "skipped"),
    }


def write_report(path: Path, report: HardeningSuiteReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_json_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def now_ms() -> int:
    return int(time.time() * 1000)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Reactor Python hardening suite gates.")
    parser.add_argument("--uv-bin", default="uv")
    parser.add_argument("--python-bin", default="python")
    parser.add_argument("--include-tag", action="append", default=[])
    parser.add_argument("--exclude-tag", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-file", default="")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report_file = (
        Path(args.report_file)
        if args.report_file
        else Path(gettempdir()) / f"reactor-hardening-suite-{int(time.time())}.json"
    )
    report = run_hardening_suite(
        build_default_hardening_suite(uv_bin=args.uv_bin, python_bin=args.python_bin),
        include_tags=set(args.include_tag),
        exclude_tags=set(args.exclude_tag),
        dry_run=bool(args.dry_run),
        report_file=report_file,
    )
    print(
        "Hardening suite summary: "
        f"total={report.summary['total']} passed={report.summary['passed']} "
        f"failed={report.summary['failed']} skipped={report.summary['skipped']}"
    )
    print(f"Report: {report_file}")
    return 1 if report.summary["failed"] > 0 else 0

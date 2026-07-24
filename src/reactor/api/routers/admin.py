from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from inspect import isawaitable
from pathlib import Path
from shlex import quote
from typing import Annotated, Any, Literal, Protocol, cast
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.admin.tenants import (
    TenantRecord,
    TenantStatus,
    activate_tenant,
    create_tenant,
    parse_tenant_plan,
    suspend_tenant,
)
from reactor.agents.runner import sanitize_public_metadata_value
from reactor.agents.state_history import read_graph_state_history
from reactor.api.auth import require_any_admin, require_permission
from reactor.api.routers.runs import public_run_event_payload
from reactor.api.schemas.admin import (
    A2AAgentCardSummaryResponse,
    A2ADiagnosticsSummaryResponse,
    A2AOperationalEvidenceSummaryResponse,
    A2AProtocolNegotiationSummaryResponse,
    A2AProtocolSummaryResponse,
    A2ATaskApiSummaryResponse,
    AdminAuditResponse,
    AdminAuditRollbackPreviewResponse,
    AdminAuditRollbackResultResponse,
    AdminCapabilitiesResponse,
    AdminUserResponse,
    AlertEvaluationResponse,
    AlertInstanceResponse,
    AlertRuleRequest,
    AlertRuleResponse,
    ApprovalOpsSummary,
    BackendProviderIntegrationSummaryResponse,
    CacheConfigResponse,
    CacheInvalidationResponse,
    CacheKeyInvalidationRequest,
    CacheKeyInvalidationResponse,
    CachePatternInvalidationRequest,
    CachePatternInvalidationResponse,
    CacheStatsResponse,
    DailyTokenCostResponse,
    DependencyWarningFindingSummaryResponse,
    DependencyWarningResolverCheckSummaryResponse,
    DependencyWarningsSummaryResponse,
    DoctorCheckResponse,
    DoctorReportResponse,
    DoctorSectionResponse,
    DurableQueueSummaryResponse,
    EmployeeValueSummary,
    EvalMetricResultRequest,
    EvalRunMetricResultsRequest,
    EvalTestCaseMetricResult,
    FeedbackReviewQueueSummaryResponse,
    LangSmithSyncSummaryResponse,
    LatencySummaryResponse,
    LatencyTimeseriesPointResponse,
    McpHealthMetricRequest,
    McpStatusSummary,
    MemoryMaintenanceResponse,
    MemoryNextAction,
    MemoryProposalApprovalResponse,
    MemoryProposalDecisionRequest,
    MemoryProposalReviewQueueItemResponse,
    MemoryProposalReviewQueueResponse,
    MemoryProposalReviewResponse,
    MemoryReviewItemResponse,
    MemorySensitivityResponse,
    ModelPricingRequest,
    ModelPricingResponse,
    OpsDashboardResponse,
    OpsMetricSnapshot,
    PaginatedAdminAuditResponse,
    PlatformHealthResponse,
    PolicyRagSeedEntry,
    PolicyRagSeedRequest,
    PolicyRagSeedResponse,
    ProductCapabilityBoundarySummaryResponse,
    ProviderUsageMetadataResponse,
    RagCollectionStatsResponse,
    RagDiagnosticsSurfaceSummaryResponse,
    RagIngestionLifecycleSummaryResponse,
    RagStatsResponse,
    RagVerificationSensorsSummaryResponse,
    RecentSchedulerExecutionSummary,
    ReleaseGateSummaryResponse,
    ReleaseReadinessProvenanceSummaryResponse,
    ReleaseReadinessSummaryResponse,
    ReleaseTagRecommendationResponse,
    ResearchAnswerContractSummaryResponse,
    ResponseTrustSummary,
    RetentionPolicyResponse,
    SchedulerOpsSummary,
    SlackGatewaySmokeSummaryResponse,
    TenantAnalyticsSummaryResponse,
    TenantCostDashboardResponse,
    TenantCreateRequest,
    TenantOverviewDashboardResponse,
    TenantQualityDashboardResponse,
    TenantQuotaResponse,
    TenantQuotaUsageResponse,
    TenantResponse,
    TenantSloResponse,
    TenantToolDashboardResponse,
    TenantUsageDashboardResponse,
    TenantUsageResponse,
    TimeSeriesPointResponse,
    TokenCostRowResponse,
    ToolCallMetricRequest,
    ToolUsageSummaryResponse,
    TopExpensiveRunResponse,
    TraceSpanResponse,
    TraceSummaryResponse,
    UpdateRetentionRequest,
    UpdateUserRoleRequest,
    UserUsageSummaryResponse,
    VectorStoreStatsResponse,
)
from reactor.auth.models import UserRecord
from reactor.auth.rbac import (
    AuthPrincipal,
    UserRole,
    current_actor,
    masked_admin_account_ref,
    parse_role,
)
from reactor.context.diagnostics import context_manifest_diagnostics
from reactor.core.container import AppContainer
from reactor.core.settings import Settings
from reactor.evals.hardening_suite import checkpoint_provenance_evidence, graph_topology_evidence
from reactor.memory.lifecycle_actions import MEMORY_LIFECYCLE_GATE_ACTION
from reactor.memory.service import (
    MemoryItemRecord,
    MemoryPromotionResult,
    MemoryProposalRecord,
    MemoryProposalService,
)
from reactor.observability.alerts import (
    AlertInstance,
    AlertRule,
    AlertSeverity,
    AlertType,
    AsyncAlertEvaluator,
)
from reactor.observability.metrics import reactor_prometheus_metric_names
from reactor.observability.pricing import ModelPricing
from reactor.observability.tracing import redact_trace_payload
from reactor.observability.usage_ledger import (
    DailyUsageSummary,
    ExpensiveRunSummary,
    TenantUsageSummary,
    UsageLedgerRecord,
)
from reactor.persistence.rag_ingest_store import (
    RagChunkMigrationRecord,
    RagDocumentMigrationRecord,
    RagSourceMigrationRecord,
    RagStatsRecord,
    checksum,
    deterministic_rag_id,
)
from reactor.persistence.run_store import RunEventRecord, SessionListRecord, SessionRunRecord
from reactor.persistence.tool_invocation_store import (
    ToolInvocationRecord,
    validate_tool_invocation_status,
)
from reactor.providers.chat_models import LangChainChatModelFactory
from reactor.release.a2a_smoke import (
    HttpA2AProbe,
    LiveA2APeerSmokeConfig,
    run_live_a2a_peer_smoke,
)
from reactor.release.backend_provider_smoke import (
    LiveBackendProviderSmokeConfig,
    run_live_backend_provider_smoke,
)
from reactor.release.observability_smoke import (
    ObservabilitySmokeConfig,
    observability_smoke_diagnostics,
)
from reactor.release.readiness import current_git_commit
from reactor.release.readiness_actions import (
    HARDENING_SUITE_REPORT_FILE,
    RELEASE_EVIDENCE_FILE,
    RELEASE_READINESS_FILE,
    RELEASE_SMOKE_PLAN_FILE,
    RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
    RELEASE_SMOKE_PREFLIGHT_FILE,
    REPLATFORM_READINESS_FILE,
)
from reactor.release.slack_smoke import HttpSlackProbe, LiveSlackSmokeConfig, run_live_slack_smoke
from reactor.runtime_settings.service import GLOBAL_TENANT_ID, RuntimeSettingUpdate
from reactor.scheduler.service import (
    JobExecutionStatus,
    ScheduledJobExecutionRecord,
    ScheduledJobRecord,
    ScheduledJobType,
    scheduler_failure_reason,
    scheduler_result_preview,
)

router = APIRouter(tags=["admin"])

DEFAULT_METRIC_NAMES = (
    "reactor.agent.executions",
    "reactor.agent.errors",
    "reactor.agent.tool.calls",
    "reactor.agent.output.guard.actions",
    "reactor.agent.boundary.violations",
    "reactor.agent.responses.unverified",
    "reactor.slack.inbound.total",
    "reactor.slack.duplicate.total",
    "reactor.slack.dropped.total",
    "reactor.slack.handler.duration",
    "reactor.slack.api.duration",
    "reactor.slack.api.retry.total",
)
MAX_METRIC_INGEST_BATCH_SIZE = 1000
RETENTION_DEFAULTS = {
    "retention.session.days": 90,
    "retention.conversation.days": 365,
    "retention.audit.days": 730,
    "retention.metric.days": 180,
}
MAX_RELEASE_READINESS_AGE_SECONDS = 21_600


class MemoryProposalReviewStore(Protocol):
    async def get_proposal(
        self,
        *,
        tenant_id: str,
        proposal_id: str,
    ) -> MemoryProposalRecord | None: ...

    async def get_memory_item(
        self,
        *,
        tenant_id: str,
        item_id: str,
    ) -> MemoryItemRecord | None: ...

    async def list_proposals(
        self,
        *,
        tenant_id: str,
        status: str = "proposed",
        limit: int = 50,
        subject_id: str | None = None,
    ) -> list[MemoryProposalRecord]: ...

    async def save_promotion(self, result: MemoryPromotionResult) -> str: ...

    async def save_rejection(self, proposal: MemoryProposalRecord) -> str: ...


class ContextManifestDiagnosticsRequest(BaseModel):
    context_manifest: dict[str, object] = Field(alias="contextManifest")


class ExternalSideEffectSmokeRequest(BaseModel):
    confirm_external_side_effects: Literal[True] = Field(alias="confirmExternalSideEffects")


@dataclass
class UserUsageAggregate:
    requests: int
    tokens: int
    cost: Decimal
    last_activity: datetime


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def observability_smoke_environ(settings: object) -> dict[str, str]:
    api_key = getattr(settings, "observability_langsmith_api_key", "")
    environ: dict[str, str] = {}
    if isinstance(api_key, str) and api_key.strip():
        environ["REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"] = api_key.strip()
    return environ


def run_configured_backend_provider_smoke(settings: Settings) -> dict[str, Any]:
    environ = dict(os.environ)
    langsmith_api_key = settings.observability_langsmith_api_key.strip()
    if langsmith_api_key:
        environ["REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"] = langsmith_api_key
    return run_live_backend_provider_smoke(
        LiveBackendProviderSmokeConfig(
            provider=settings.default_model_provider,
            model=settings.default_model,
            trace_exporter=settings.observability_trace_exporter,
            langsmith_project=(settings.observability_langsmith_project or "reactor-release-smoke"),
            langsmith_endpoint=(
                settings.observability_langsmith_endpoint or "https://api.smith.langchain.com"
            ),
        ),
        factory=LangChainChatModelFactory(),
        environ=environ,
    )


def run_configured_slack_smoke(settings: Settings) -> dict[str, Any]:
    environ = dict(os.environ)
    configured_values = {
        "REACTOR_SLACK_SIGNING_SECRET": settings.slack_signing_secret,
        "REACTOR_SLACK_BOT_TOKEN": settings.slack_bot_token,
        "REACTOR_SLACK_APP_TOKEN": settings.slack_app_token,
    }
    for name, value in configured_values.items():
        if value.strip():
            environ[name] = value.strip()
    report = run_live_slack_smoke(
        LiveSlackSmokeConfig(),
        environ=environ,
        auth_probe=HttpSlackProbe(),
    )
    check_mapping = safe_object_mapping(report.get("checks")) or {}
    auth_mapping = safe_object_mapping(check_mapping.get("auth_test")) or {}
    channel_mapping = safe_object_mapping(check_mapping.get("channel_info")) or {}
    thread_mapping = safe_object_mapping(check_mapping.get("thread_message")) or {}
    report["liveTarget"] = {
        "workspaceId": optional_string(auth_mapping.get("team_id")),
        "channelId": optional_string(thread_mapping.get("channel_id"))
        or optional_string(channel_mapping.get("channel_id"))
        or optional_string(environ.get("REACTOR_SLACK_CHANNEL_ID")),
        "channelName": optional_string(channel_mapping.get("channel_name")),
        "botUserId": optional_string(auth_mapping.get("user_id")),
    }
    return report


def run_configured_a2a_smoke() -> dict[str, Any]:
    environ = dict(os.environ)
    base_url = environ.get("REACTOR_A2A_BASE_URL", "").strip()
    config = LiveA2APeerSmokeConfig(base_url=base_url)
    return run_live_a2a_peer_smoke(
        config,
        http_probe=HttpA2AProbe(base_url=base_url, timeout_seconds=config.timeout_seconds),
        environ=environ,
    )


def ops_release_readiness_summary(settings: object) -> ReleaseReadinessSummaryResponse | None:
    report_path_value = getattr(settings, "release_readiness_report_path", "")
    if not isinstance(report_path_value, str) or not report_path_value.strip():
        return None
    report_path = Path(report_path_value.strip())
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    report = cast(dict[str, object], payload)
    items = release_readiness_items(report.get("items"))
    tag_recommendation = release_tag_recommendation(report.get("tagRecommendation"))
    provenance = release_readiness_provenance_summary(report.get("provenance"))
    blocking_reports = string_list(report.get("blockingReports"))
    summary_status = release_status(report.get("status"))
    trusted_release_claims = provenance.status == "verified"
    if not trusted_release_claims:
        summary_status = "blocked"
        blocking_reports = [*blocking_reports, "readiness_provenance"]
        tag_recommendation = None
    recommended_tag = (
        optional_string(report.get("recommendedTag"))
        or (tag_recommendation.recommendedTag if tag_recommendation else None)
        if trusted_release_claims
        else None
    )
    recommended_version_bump = (
        optional_string(report.get("recommendedVersionBump"))
        or (tag_recommendation.recommendedVersionBump if tag_recommendation else None)
        if trusted_release_claims
        else None
    )
    minor_eligible = (
        (
            optional_bool(report.get("minorEligible"))
            if "minorEligible" in report
            else (tag_recommendation.minorEligible if tag_recommendation else None)
        )
        if trusted_release_claims
        else None
    )
    return ReleaseReadinessSummaryResponse(
        status=summary_status,
        recommendedTag=recommended_tag,
        recommendedVersionBump=recommended_version_bump,
        minorEligible=minor_eligible,
        blockingReports=list(dict.fromkeys(blocking_reports)),
        warningReports=string_list(report.get("warningReports"))
        or string_list(report.get("warnings"))
        or (tag_recommendation.warningReports if tag_recommendation else None)
        or [],
        requiredReports=string_list_or_none(report.get("requiredReports")),
        missingReports=string_list_or_none(report.get("missingReports")),
        requiredEnvAnyOf=string_list_groups_or_none(report.get("requiredEnvAnyOf")),
        missingEnvAnyOf=string_list_or_none(report.get("missingEnvAnyOf")),
        recommendedEnv=string_list_or_none(report.get("recommendedEnv")),
        tagRecommendation=tag_recommendation,
        productCapabilityBoundary=product_capability_boundary_summary(items),
        gates=release_gate_summaries(items),
        langsmithSync=langsmith_sync_summary(items),
        ragIngestionLifecycle=rag_ingestion_lifecycle_summary(items),
        feedbackReviewQueue=feedback_review_queue_summary(items),
        backendProviderIntegration=backend_provider_integration_summary(items),
        slackGatewaySmoke=slack_gateway_smoke_summary(items),
        a2aProtocol=a2a_protocol_summary(items),
        dependencyWarnings=dependency_warnings_summary(items, tag_recommendation),
        provenance=provenance,
        syncedAt=optional_string(report.get("syncedAt")) or provenance.generatedAt,
    )


def release_readiness_provenance_summary(
    value: object,
) -> ReleaseReadinessProvenanceSummaryResponse:
    provenance = safe_object_mapping(value)
    if provenance is None:
        return ReleaseReadinessProvenanceSummaryResponse(
            status="missing",
            reason="missing_provenance",
        )

    commit_sha = optional_string(provenance.get("commitSha"))
    expected_commit_sha = optional_string(provenance.get("expectedCommitSha"))
    generated_at = optional_string(provenance.get("generatedAt"))
    input_hash = optional_string(provenance.get("inputHash"))
    current_commit = current_git_commit()
    reason = readiness_provenance_failure(
        commit_sha=commit_sha,
        expected_commit_sha=expected_commit_sha,
        generated_at=generated_at,
        input_hash=input_hash,
        current_commit=current_commit,
    )
    return ReleaseReadinessProvenanceSummaryResponse(
        status="verified" if not reason else "blocked",
        commitSha=commit_sha,
        expectedCommitSha=expected_commit_sha,
        generatedAt=generated_at,
        inputHash=input_hash,
        verifiedCurrentHead=not reason,
        reason=reason or None,
    )


def readiness_provenance_failure(
    *,
    commit_sha: str | None,
    expected_commit_sha: str | None,
    generated_at: str | None,
    input_hash: str | None,
    current_commit: str,
) -> str:
    if not commit_sha or not expected_commit_sha or not generated_at or not input_hash:
        return "missing_provenance_fields"
    if not re.fullmatch(r"[0-9a-f]{64}", input_hash, flags=re.IGNORECASE):
        return "invalid_input_hash"
    try:
        generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return "invalid_generated_at"
    if generated.tzinfo is None:
        return "invalid_generated_at"
    generated = generated.astimezone(UTC)
    now = datetime.now(UTC)
    if generated > now + timedelta(seconds=5):
        return "generated_at_in_future"
    if (now - generated).total_seconds() > MAX_RELEASE_READINESS_AGE_SECONDS:
        return "stale_readiness_evidence"
    if not current_commit:
        return "current_head_unavailable"
    if commit_sha != expected_commit_sha:
        return "report_commit_mismatch"
    if commit_sha != current_commit:
        return "current_head_mismatch"
    return ""


def release_readiness_items(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [cast(dict[str, object], item) for item in items if isinstance(item, dict)]


def release_status(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "missing"


def optional_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    values = cast(list[object], value)
    return [item.strip() for item in values if isinstance(item, str) and item.strip()]


def string_list_or_none(value: object) -> list[str] | None:
    values = string_list(value)
    return values if values or isinstance(value, list) else None


def string_list_groups_or_none(value: object) -> list[list[str]] | None:
    if not isinstance(value, list):
        return None
    groups = [
        string_list(cast(list[object], group))
        for group in cast(list[object], value)
        if isinstance(group, list)
    ]
    return [group for group in groups if group] or []


def int_mapping(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    mapping = cast(dict[object, object], value)
    result: dict[str, int] = {}
    for key, raw in mapping.items():
        if (
            isinstance(key, str)
            and key.strip()
            and isinstance(raw, int)
            and not isinstance(raw, bool)
        ):
            result[key.strip()] = raw
    return result


def string_mapping(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    mapping = cast(dict[object, object], value)
    result: dict[str, str] = {}
    for key, raw in mapping.items():
        if isinstance(key, str) and key.strip() and isinstance(raw, str) and raw.strip():
            result[key.strip()] = raw.strip()
    return result or None


def safe_object_mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    mapping = cast(dict[object, object], value)
    return {str(key): raw for key, raw in mapping.items() if isinstance(key, str)}


def dependency_warnings_summary(
    items: Sequence[Mapping[str, object]],
    tag_recommendation: ReleaseTagRecommendationResponse | None,
) -> DependencyWarningsSummaryResponse | None:
    for item in items:
        lifecycle = safe_object_mapping(item.get("memoryMaintenanceLifecycle"))
        if lifecycle is None:
            continue
        warnings = safe_object_mapping(lifecycle.get("dependencyWarnings"))
        if warnings is None:
            continue
        findings = dependency_warning_findings(warnings.get("findings"))
        return DependencyWarningsSummaryResponse(
            status=optional_string(warnings.get("status")),
            source="memoryMaintenanceLifecycle.dependencyWarnings",
            warningReports=tag_recommendation.warningReports if tag_recommendation else None,
            warningReviewRequired=tag_recommendation.warningReviewRequired
            if tag_recommendation
            else None,
            checkedPackages=string_list_or_none(warnings.get("checkedPackages")),
            installedVersions=string_mapping(warnings.get("installedVersions")),
            directPins=string_mapping(warnings.get("directPins")),
            pinSource=optional_string(warnings.get("pinSource")),
            findings=findings or None,
            findingCount=len(findings),
            reviewCommand=optional_string(warnings.get("reviewCommand")),
            remediationCommand=optional_string(warnings.get("remediationCommand")),
            resolverCheck=dependency_warning_resolver_check(
                safe_object_mapping(warnings.get("resolverCheck"))
            ),
        )
    return None


def product_capability_boundary_summary(
    items: Sequence[Mapping[str, object]],
) -> ProductCapabilityBoundarySummaryResponse | None:
    for item in items:
        boundary = safe_object_mapping(item.get("productCapabilityBoundary"))
        if boundary is None:
            continue
        return ProductCapabilityBoundarySummaryResponse(
            capability=optional_string(boundary.get("capability")),
            minorEligible=optional_bool(boundary.get("minorEligible")),
            evidence=string_list_or_none(boundary.get("evidence")),
            missingEvidence=string_list_or_none(boundary.get("missingEvidence")),
            sourceReport=optional_string(item.get("name")),
            status=optional_string(item.get("status")),
        )
    return None


def dependency_warning_findings(
    value: object,
) -> list[DependencyWarningFindingSummaryResponse]:
    if not isinstance(value, list):
        return []
    findings: list[DependencyWarningFindingSummaryResponse] = []
    for raw in cast(list[object], value):
        mapping = safe_object_mapping(raw)
        if mapping is None:
            continue
        findings.append(
            DependencyWarningFindingSummaryResponse(
                package=optional_string(mapping.get("package")),
                module=optional_string(mapping.get("module")),
                deprecatedImport=optional_string(mapping.get("deprecatedImport")),
                replacement=optional_string(mapping.get("replacement")),
                severity=optional_string(mapping.get("severity")),
            )
        )
    return findings


def dependency_warning_resolver_check(
    mapping: Mapping[str, object] | None,
) -> DependencyWarningResolverCheckSummaryResponse | None:
    if mapping is None:
        return None
    return DependencyWarningResolverCheckSummaryResponse(
        status=optional_string(mapping.get("status")),
        command=optional_string(mapping.get("command")),
        latestKnownFrom=optional_string(mapping.get("latestKnownFrom")),
    )


def rag_ingestion_lifecycle_summary(
    items: Sequence[Mapping[str, object]],
) -> RagIngestionLifecycleSummaryResponse | None:
    item = next((entry for entry in items if item_matches_gate(entry, "rag")), None)
    if item is None:
        return None
    lifecycle = item.get("ragIngestionLifecycle")
    if not isinstance(lifecycle, dict):
        return None
    mapping = cast(dict[str, object], lifecycle)
    return RagIngestionLifecycleSummaryResponse(
        status=optional_string(mapping.get("status")),
        framework=optional_string(mapping.get("framework")),
        vectorStore=optional_string(mapping.get("vectorStore")),
        embeddingBoundary=optional_string(mapping.get("embeddingBoundary")),
        sourceAllowlistRequired=optional_bool(mapping.get("sourceAllowlistRequired")),
        mimeAllowlistRequired=optional_bool(mapping.get("mimeAllowlistRequired")),
        sizeLimitRequired=optional_bool(mapping.get("sizeLimitRequired")),
        aclMetadataRequired=optional_bool(mapping.get("aclMetadataRequired")),
        aclBeforeRanking=optional_bool(mapping.get("aclBeforeRanking")),
        rawAclRedactedFromModelContext=optional_bool(mapping.get("rawAclRedactedFromModelContext")),
        humanReviewRequiredForCapturedCandidates=optional_bool(
            mapping.get("humanReviewRequiredForCapturedCandidates")
        ),
        quarantineBeforeIndex=optional_bool(mapping.get("quarantineBeforeIndex")),
        backgroundRetries=optional_bool(mapping.get("backgroundRetries")),
        checksumIdempotency=optional_bool(mapping.get("checksumIdempotency")),
        reindexAuditRequired=optional_bool(mapping.get("reindexAuditRequired")),
        poisoningEvalCaseIds=string_list_or_none(mapping.get("poisoningEvalCaseIds")),
        diagnosticsSurface=rag_diagnostics_surface_summary(
            safe_object_mapping(mapping.get("diagnosticsSurface"))
        ),
        verificationSensors=rag_verification_sensors_summary(
            safe_object_mapping(mapping.get("verificationSensors"))
        ),
        researchAnswerContract=research_answer_contract_summary(
            safe_object_mapping(item.get("researchAnswerContract"))
        ),
    )


def rag_diagnostics_surface_summary(
    mapping: Mapping[str, object] | None,
) -> RagDiagnosticsSurfaceSummaryResponse | None:
    if mapping is None:
        return None
    return RagDiagnosticsSurfaceSummaryResponse(
        status=optional_string(mapping.get("status")),
        apiPaths=string_list_or_none(mapping.get("apiPaths")),
        releaseReviewFields=string_list_or_none(mapping.get("releaseReviewFields")),
    )


def rag_verification_sensors_summary(
    mapping: Mapping[str, object] | None,
) -> RagVerificationSensorsSummaryResponse | None:
    if mapping is None:
        return None
    return RagVerificationSensorsSummaryResponse(
        covers=string_list_or_none(mapping.get("covers")),
        focusedTests=string_list_or_none(mapping.get("focusedTests")),
        releaseReadinessContracts=string_list_or_none(mapping.get("releaseReadinessContracts")),
    )


def research_answer_contract_summary(
    mapping: Mapping[str, object] | None,
) -> ResearchAnswerContractSummaryResponse | None:
    if mapping is None:
        return None
    return ResearchAnswerContractSummaryResponse(
        profile=optional_string(mapping.get("profile")),
        citationStyle=optional_string(mapping.get("citationStyle")),
        requiresCitationIds=optional_bool(mapping.get("requiresCitationIds")),
        requiresSourceLabels=optional_bool(mapping.get("requiresSourceLabels")),
        fallbackResponseIncludesSources=optional_bool(
            mapping.get("fallbackResponseIncludesSources")
        ),
        uncitedClaimsAllowed=optional_bool(mapping.get("uncitedClaimsAllowed")),
        tracksMissingChunks=optional_bool(mapping.get("tracksMissingChunks")),
        tracksContentHashMismatches=optional_bool(mapping.get("tracksContentHashMismatches")),
    )


def feedback_review_queue_summary(
    items: Sequence[Mapping[str, object]],
) -> FeedbackReviewQueueSummaryResponse | None:
    item = next((entry for entry in items if item_matches_gate(entry, "feedback")), None)
    if item is None:
        return None
    queue = item.get("feedbackReviewQueue")
    if not isinstance(queue, dict):
        return None
    mapping = cast(dict[str, object], queue)
    return FeedbackReviewQueueSummaryResponse(
        status=optional_string(mapping.get("status")) or optional_string(item.get("status")),
        reviewStatus=optional_string(mapping.get("reviewStatus")),
        reviewNote=optional_string(mapping.get("reviewNote")),
        candidateTag=optional_string(mapping.get("candidateTag")),
        caseIds=string_list_or_none(mapping.get("caseIds")),
        reviewTags=string_list_or_none(mapping.get("reviewTags")),
        feedbackRatingCounts=int_mapping(mapping.get("feedbackRatingCounts")),
        feedbackSourceCounts=int_mapping(mapping.get("feedbackSourceCounts")),
        workflowTagCounts=int_mapping(mapping.get("workflowTagCounts")),
        expectedCitationCounts=int_mapping(mapping.get("expectedCitationCounts")),
    )


def backend_provider_integration_summary(
    items: Sequence[Mapping[str, object]],
) -> BackendProviderIntegrationSummaryResponse | None:
    item = next((entry for entry in items if item_matches_gate(entry, "provider")), None)
    if item is None:
        return None
    integration = item.get("backendProviderIntegration")
    if not isinstance(integration, dict):
        return None
    mapping = cast(dict[str, object], integration)
    usage = provider_usage_metadata(mapping.get("usageMetadata"))
    return BackendProviderIntegrationSummaryResponse(
        status=optional_string(mapping.get("status")),
        provider=optional_string(mapping.get("provider")),
        model=optional_string(mapping.get("model")),
        requiredChecks=string_list_or_none(mapping.get("requiredChecks")),
        usageMetadata=usage,
    )


def slack_gateway_smoke_summary(
    items: Sequence[Mapping[str, object]],
) -> SlackGatewaySmokeSummaryResponse | None:
    item = next((entry for entry in items if item_matches_gate(entry, "slack")), None)
    if item is None:
        return None
    gateway = item.get("slackGatewaySmoke")
    if not isinstance(gateway, dict):
        return None
    mapping = cast(dict[str, object], gateway)
    return SlackGatewaySmokeSummaryResponse(
        status=optional_string(mapping.get("status")),
        gateway=optional_string(mapping.get("gateway")),
        ingress=optional_string(mapping.get("ingress")),
        currentThreadReplyRoute=optional_string(mapping.get("currentThreadReplyRoute")),
        signatureVerificationRequired=optional_bool(mapping.get("signatureVerificationRequired")),
        responseUrlRouteSupported=optional_bool(mapping.get("responseUrlRouteSupported")),
        mcpWriteOverlapForbidden=optional_bool(mapping.get("mcpWriteOverlapForbidden")),
        requiredChecks=string_list_or_none(mapping.get("requiredChecks")),
    )


def a2a_protocol_summary(
    items: Sequence[Mapping[str, object]],
) -> A2AProtocolSummaryResponse | None:
    item = next((entry for entry in items if item_matches_gate(entry, "a2a")), None)
    if item is None:
        return None
    protocol = item.get("a2aProtocol")
    if not isinstance(protocol, dict):
        return None
    mapping = cast(dict[str, object], protocol)
    agent_card = safe_object_mapping(mapping.get("agentCard"))
    diagnostics = safe_object_mapping(mapping.get("diagnostics"))
    negotiation = safe_object_mapping(mapping.get("protocolNegotiation"))
    task_api = safe_object_mapping(mapping.get("taskApi"))
    operational = safe_object_mapping(mapping.get("operationalEvidence"))
    return A2AProtocolSummaryResponse(
        status=optional_string(mapping.get("status")),
        agentCard=a2a_agent_card_summary(agent_card),
        diagnostics=a2a_diagnostics_summary(diagnostics),
        protocolNegotiation=a2a_protocol_negotiation_summary(negotiation),
        taskApi=a2a_task_api_summary(task_api),
        operationalEvidence=a2a_operational_evidence_summary(operational),
        secretFree=optional_bool(mapping.get("secretFree")),
        tlsRequired=optional_bool(mapping.get("tlsRequired")),
    )


def a2a_agent_card_summary(
    mapping: Mapping[str, object] | None,
) -> A2AAgentCardSummaryResponse | None:
    if mapping is None:
        return None
    return A2AAgentCardSummaryResponse(
        name=optional_string(mapping.get("name")),
        interfaceCount=int_value(mapping.get("interfaceCount")),
        interfaceProtocolBindings=string_list_or_none(mapping.get("interfaceProtocolBindings")),
        interfaceProtocolVersions=string_list_or_none(mapping.get("interfaceProtocolVersions")),
        wellKnownPath=optional_string(mapping.get("wellKnownPath")),
    )


def a2a_diagnostics_summary(
    mapping: Mapping[str, object] | None,
) -> A2ADiagnosticsSummaryResponse | None:
    if mapping is None:
        return None
    return A2ADiagnosticsSummaryResponse(
        sdkAvailable=optional_bool(mapping.get("sdkAvailable")),
        protocolVersion=optional_string(mapping.get("protocolVersion")),
        path=optional_string(mapping.get("path")),
    )


def a2a_protocol_negotiation_summary(
    mapping: Mapping[str, object] | None,
) -> A2AProtocolNegotiationSummaryResponse | None:
    if mapping is None:
        return None
    return A2AProtocolNegotiationSummaryResponse(
        requestHeader=optional_string(mapping.get("requestHeader")),
        requestedVersion=optional_string(mapping.get("requestedVersion")),
        responseVersion=optional_string(mapping.get("responseVersion")),
        majorMinorOnly=optional_bool(mapping.get("majorMinorOnly")),
        agentCardVersionsChecked=optional_bool(mapping.get("agentCardVersionsChecked")),
        serverGeneratedTaskIds=optional_bool(mapping.get("serverGeneratedTaskIds")),
        sdkFastApiSurface=optional_bool(mapping.get("sdkFastApiSurface")),
        telemetryInstrumentation=optional_string(mapping.get("telemetryInstrumentation")),
    )


def a2a_task_api_summary(mapping: Mapping[str, object] | None) -> A2ATaskApiSummaryResponse | None:
    if mapping is None:
        return None
    return A2ATaskApiSummaryResponse(
        status=optional_string(mapping.get("status")),
        taskStatus=optional_string(mapping.get("taskStatus")),
        path=optional_string(mapping.get("path")),
    )


def a2a_operational_evidence_summary(
    mapping: Mapping[str, object] | None,
) -> A2AOperationalEvidenceSummaryResponse | None:
    if mapping is None:
        return None
    return A2AOperationalEvidenceSummaryResponse(
        auditRecorded=optional_bool(mapping.get("auditRecorded")),
        idempotencyEnforced=optional_bool(mapping.get("idempotencyEnforced")),
        telemetryEnabled=optional_bool(mapping.get("telemetryEnabled")),
        pushOutboxRouted=optional_bool(mapping.get("pushOutboxRouted")),
    )


def provider_usage_metadata(value: object) -> ProviderUsageMetadataResponse | None:
    if not isinstance(value, dict):
        return None
    mapping = cast(dict[str, object], value)
    return ProviderUsageMetadataResponse(
        source=optional_string(mapping.get("source")),
        present=optional_bool(mapping.get("present")),
        inputTokens=int_value(mapping.get("inputTokens")),
        outputTokens=int_value(mapping.get("outputTokens")),
        totalTokens=int_value(mapping.get("totalTokens")),
        totalMatchesBreakdown=optional_bool(mapping.get("totalMatchesBreakdown")),
    )


def release_tag_recommendation(value: object) -> ReleaseTagRecommendationResponse | None:
    if not isinstance(value, dict):
        return None
    mapping = cast(dict[str, object], value)
    return ReleaseTagRecommendationResponse(
        status=optional_string(mapping.get("status")),
        eligible=optional_bool(mapping.get("eligible")),
        latestTag=optional_string(mapping.get("latestTag")),
        recommendedTag=optional_string(mapping.get("recommendedTag")),
        recommendedTagPattern=optional_string(mapping.get("recommendedTagPattern")),
        recommendedVersionBump=optional_string(mapping.get("recommendedVersionBump")),
        minorEligible=optional_bool(mapping.get("minorEligible")),
        minorBoundaryReports=string_list_or_none(mapping.get("minorBoundaryReports")),
        passedReports=string_list_or_none(mapping.get("passedReports")),
        warningReports=string_list_or_none(mapping.get("warningReports")),
        warningReviewRequired=optional_bool(mapping.get("warningReviewRequired")),
        missingEnv=string_list_or_none(mapping.get("missingEnv")),
        missingEnvAnyOf=string_list_or_none(mapping.get("missingEnvAnyOf")),
        preflightEnvFileCommand=optional_string(mapping.get("preflightEnvFileCommand")),
        releaseSmokeEnvFileCommand=optional_string(mapping.get("releaseSmokeEnvFileCommand")),
        nextAction=optional_string(mapping.get("nextAction")),
        releaseReadinessCommand=optional_string(mapping.get("releaseReadinessCommand")),
        reason=optional_string(mapping.get("reason")),
    )


def release_gate_summaries(
    items: Sequence[Mapping[str, object]],
) -> list[ReleaseGateSummaryResponse]:
    return [
        ReleaseGateSummaryResponse(id="rag", status=gate_status(items, "rag")),
        ReleaseGateSummaryResponse(id="feedback", status=gate_status(items, "feedback")),
        ReleaseGateSummaryResponse(id="langsmith", status=gate_status(items, "langsmith")),
        ReleaseGateSummaryResponse(id="slack", status=gate_status(items, "slack")),
        ReleaseGateSummaryResponse(id="a2a", status=gate_status(items, "a2a")),
        ReleaseGateSummaryResponse(id="provider", status=gate_status(items, "provider")),
    ]


def gate_status(items: Sequence[Mapping[str, object]], gate: str) -> str:
    matched = [item for item in items if item_matches_gate(item, gate)]
    if not matched:
        return "missing"
    statuses = {release_status(item.get("status")).lower() for item in matched}
    if any(status in {"blocked", "failed", "fail", "error"} for status in statuses):
        return "blocked"
    if any(status in {"warning", "warn", "skipped"} for status in statuses):
        return "warning"
    if any(status == "passed" for status in statuses):
        return "passed"
    return "warning"


def item_matches_gate(item: Mapping[str, object], gate: str) -> bool:
    name = optional_string(item.get("name")) or ""
    normalized = name.lower()
    if gate == "rag":
        return "rag" in normalized or "ragIngestionLifecycle" in item
    if gate == "feedback":
        return "feedback" in normalized or "feedbackReviewQueue" in item or "feedbackLoop" in item
    if gate == "langsmith":
        return "langsmith" in normalized
    if gate == "slack":
        return "slack" in normalized or "slackMcpSurfacePolicy" in item
    if gate == "a2a":
        return "a2a" in normalized or "peer_network" in normalized or "a2aProtocol" in item
    if gate == "provider":
        return "provider" in normalized or "backendProviderIntegration" in item
    return False


def langsmith_sync_summary(
    items: Sequence[Mapping[str, object]],
) -> LangSmithSyncSummaryResponse | None:
    item = next((entry for entry in items if item_matches_gate(entry, "langsmith")), None)
    if item is None:
        return None
    example_ids = string_list(item.get("exampleIds"))
    case_ids = string_list(item.get("caseIds"))
    metadata_case_ids = string_list(item.get("metadataCaseIds"))
    example_contract = safe_object_mapping(item.get("exampleContract"))
    sdk_contract_fields = safe_object_mapping(item.get("sdkContract"))
    return LangSmithSyncSummaryResponse(
        datasetName=optional_string(item.get("datasetName")),
        exampleCount=len(example_ids) if example_ids else int_value(item.get("examples")),
        caseCount=len(case_ids) if case_ids else int_value(item.get("enabledCases")),
        exampleIds=example_ids or None,
        caseIds=case_ids or None,
        metadataCaseIds=metadata_case_ids or None,
        splitCounts=int_mapping(item.get("splitCounts")),
        secretFree=langsmith_example_contract_secret_free(example_contract),
        sdkContract=langsmith_sdk_contract_label(sdk_contract_fields),
        sdkContractFields=sdk_contract_fields,
        exampleContract=example_contract,
    )


def int_value(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def langsmith_example_contract_secret_free(contract: Mapping[str, object] | None) -> bool | None:
    if contract is None:
        return None
    secret_scan = contract.get("secretScan")
    if not isinstance(secret_scan, dict):
        return False
    scan = cast(dict[str, object], secret_scan)
    return (
        scan.get("enabled") is True
        and scan.get("scansKeys") is True
        and scan.get("scansValues") is True
        and contract.get("rawExampleValuesIncluded") is False
    )


def langsmith_sdk_contract_label(contract: Mapping[str, object] | None) -> str | None:
    if contract is None:
        return None
    client = optional_string(contract.get("client"))
    dataset_api = optional_string(contract.get("datasetApi"))
    example_api = optional_string(contract.get("exampleApi"))
    if client and dataset_api and example_api:
        return f"{client}.{dataset_api}/{example_api}"
    return None


async def publish_metric_event_or_503(request: Request, event: dict[str, object]) -> None:
    if not await publish_metric_event(request, event):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Metric buffer full, event dropped",
        )


async def publish_metric_events(
    request: Request, events: Sequence[dict[str, object]]
) -> tuple[int, int]:
    accepted = 0
    dropped = 0
    for event in events:
        if await publish_metric_event(request, event):
            accepted += 1
        else:
            dropped += 1
    return accepted, dropped


async def publish_metric_event(request: Request, event: dict[str, object]) -> bool:
    buffer = metric_ingestion_buffer(request)
    if buffer is None:
        events = getattr(request.app.state, "_reactor_metric_ingestion_events", None)
        if events is None:
            events = []
            request.app.state._reactor_metric_ingestion_events = events
        events.append(event)
        return True

    publish = getattr(buffer, "publish", None)
    if publish is None:
        return False
    return bool(await maybe_await(publish(event)))


def metric_ingestion_buffer(request: Request):
    container = get_container(request)
    accessor = getattr(container, "metric_ingestion_buffer", None)
    return accessor() if accessor is not None else None


def require_metric_batch_size(size: int) -> None:
    if size > MAX_METRIC_INGEST_BATCH_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch size must be <= {MAX_METRIC_INGEST_BATCH_SIZE}",
        )


def mcp_health_metric_event(
    body: McpHealthMetricRequest, *, tenant_id: str | None = None
) -> dict[str, object]:
    return {
        "type": "mcp_health",
        "recordedAt": datetime.now(UTC).isoformat(),
        "tenantId": tenant_id if tenant_id is not None else body.tenantId,
        "serverName": body.serverName,
        "status": body.status,
        "responseTimeMs": body.responseTimeMs,
        "errorClass": body.errorClass,
        "errorMessage": body.errorMessage,
        "toolCount": body.toolCount,
    }


def tool_call_metric_event(
    body: ToolCallMetricRequest, *, tenant_id: str | None = None
) -> dict[str, object]:
    return {
        "type": "tool_call",
        "recordedAt": datetime.now(UTC).isoformat(),
        "tenantId": tenant_id if tenant_id is not None else body.tenantId,
        "runId": body.runId,
        "toolName": body.toolName,
        "toolSource": body.toolSource or "mcp",
        "mcpServerName": body.mcpServerName,
        "callIndex": body.callIndex or 0,
        "success": body.success,
        "durationMs": body.durationMs,
        "errorClass": body.errorClass,
        "errorMessage": body.errorMessage,
    }


def eval_result_metric_event(
    body: EvalMetricResultRequest, *, tenant_id: str | None = None
) -> dict[str, object]:
    return {
        "type": "eval_result",
        "recordedAt": datetime.now(UTC).isoformat(),
        "tenantId": tenant_id if tenant_id is not None else body.tenantId,
        "evalRunId": body.evalRunId,
        "testCaseId": body.testCaseId,
        "pass": body.pass_,
        "score": body.score,
        "latencyMs": body.latencyMs,
        "tokenUsage": body.tokenUsage,
        "cost": str(body.cost) if body.cost is not None else None,
        "assertionType": body.assertionType,
        "failureClass": body.failureClass,
        "failureDetail": truncate_failure_detail(body.failureDetail),
        "tags": body.tags or [],
    }


def eval_test_case_metric_event(
    *, tenant_id: str, eval_run_id: str, result: EvalTestCaseMetricResult
) -> dict[str, object]:
    return {
        "type": "eval_result",
        "recordedAt": datetime.now(UTC).isoformat(),
        "tenantId": tenant_id,
        "evalRunId": eval_run_id,
        "testCaseId": result.testCaseId,
        "pass": result.pass_,
        "score": result.score,
        "latencyMs": result.latencyMs,
        "tokenUsage": result.tokenUsage,
        "cost": str(result.cost) if result.cost is not None else None,
        "assertionType": result.assertionType,
        "failureClass": result.failureClass,
        "failureDetail": truncate_failure_detail(result.failureDetail),
        "tags": result.tags or [],
    }


def truncate_failure_detail(value: str | None) -> str | None:
    if value is None:
        return None
    return value[:500]


@router.get(
    "/api/admin/capabilities",
    response_model=AdminCapabilitiesResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/capabilities",
    response_model=AdminCapabilitiesResponse,
    response_model_by_alias=True,
)
async def capabilities(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> AdminCapabilitiesResponse:
    del principal
    container = request.app.state.reactor
    paths = sorted(
        path
        for path in request.app.openapi().get("paths", {})
        if path.startswith("/api/") or path.startswith("/v1/")
    )
    return AdminCapabilitiesResponse(
        generatedAt=epoch_millis(datetime.now().astimezone()),
        source="fastapi-routes",
        durable=container.session_factory is not None,
        paths=paths,
    )


@router.get(
    "/api/admin/memory/proposals",
    response_model=MemoryProposalReviewQueueResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/memory/proposals",
    response_model=MemoryProposalReviewQueueResponse,
    response_model_by_alias=True,
)
async def memory_proposals_review_queue(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    proposal_status: str = Query(default="proposed", alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    subject_id: str | None = Query(default=None),
) -> MemoryProposalReviewQueueResponse:
    normalized_status = proposal_status.strip().lower() or "proposed"
    normalized_subject_id = subject_id.strip() if isinstance(subject_id, str) else None
    proposals = await require_memory_proposal_review_store(request).list_proposals(
        tenant_id=principal.tenant_id,
        status=normalized_status,
        limit=limit,
        subject_id=normalized_subject_id or None,
    )
    return MemoryProposalReviewQueueResponse(
        items=[memory_proposal_review_queue_item_response(proposal) for proposal in proposals],
        count=len(proposals),
        status=normalized_status,
        subjectIdFilter=normalized_subject_id or None,
    )


@router.post(
    "/api/admin/memory/proposals/{proposal_id}/approve",
    response_model=MemoryProposalApprovalResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/memory/proposals/{proposal_id}/approve",
    response_model=MemoryProposalApprovalResponse,
    response_model_by_alias=True,
)
async def approve_memory_proposal(
    request: Request,
    proposal_id: str,
    body: MemoryProposalDecisionRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> MemoryProposalApprovalResponse:
    store = require_memory_proposal_review_store(request)
    proposal = await store.get_proposal(tenant_id=principal.tenant_id, proposal_id=proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory proposal not found: {proposal_id}",
        )
    supersedes_item: MemoryItemRecord | None = None
    if body.supersedesMemoryId is not None:
        supersedes_item = await store.get_memory_item(
            tenant_id=principal.tenant_id,
            item_id=body.supersedesMemoryId,
        )
        if supersedes_item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory item not found: {body.supersedesMemoryId}",
            )
    try:
        promotion = MemoryProposalService().promote(
            proposal,
            reviewer_id=current_actor(principal),
            reason=body.reason,
            supersedes=supersedes_item,
        )
    except ValueError as error:
        if str(error) == "sensitive memory proposals require rejection or redaction":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=sensitive_memory_approval_block_detail(proposal),
            ) from error
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    await store.save_promotion(promotion)
    return MemoryProposalApprovalResponse(
        proposal=memory_proposal_review_response(promotion.proposal),
        item=memory_review_item_response(promotion.item),
        supersededItems=[memory_review_item_response(item) for item in promotion.superseded_items],
        maintenance=memory_maintenance_response(proposal),
        nextAction=approved_memory_next_action(
            promotion.item,
            superseded_items=promotion.superseded_items,
        ),
        nextActions=approved_memory_next_actions(
            promotion.item,
            superseded_items=promotion.superseded_items,
            include_dependency_review=memory_maintenance_response(proposal) is not None,
        ),
    )


@router.post(
    "/api/admin/memory/proposals/{proposal_id}/reject",
    response_model=MemoryProposalReviewResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/memory/proposals/{proposal_id}/reject",
    response_model=MemoryProposalReviewResponse,
    response_model_by_alias=True,
)
async def reject_memory_proposal(
    request: Request,
    proposal_id: str,
    body: MemoryProposalDecisionRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> MemoryProposalReviewResponse:
    store = require_memory_proposal_review_store(request)
    proposal = await store.get_proposal(tenant_id=principal.tenant_id, proposal_id=proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory proposal not found: {proposal_id}",
        )
    try:
        rejected = MemoryProposalService().reject(
            proposal,
            reviewer_id=current_actor(principal),
            reason=body.reason,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    await store.save_rejection(rejected)
    return memory_proposal_review_response(rejected)


@router.get("/api/admin/doctor")
@router.get("/v1/admin/doctor")
async def doctor_report(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response:
    report = await build_doctor_report(request, tenant_id=principal.tenant_id)
    return render_doctor_response(report, request=request, summary_only=False)


@router.get("/api/admin/doctor/summary")
@router.get("/v1/admin/doctor/summary")
async def doctor_summary(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response:
    report = await build_doctor_report(request, tenant_id=principal.tenant_id)
    return render_doctor_response(report, request=request, summary_only=True)


@router.get(
    "/api/admin/audits",
    response_model=PaginatedAdminAuditResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/audits",
    response_model=PaginatedAdminAuditResponse,
    response_model_by_alias=True,
)
async def list_admin_audits(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("audit:read"))],
    limit: int | None = Query(default=None, ge=1, le=1000),
    category: str | None = None,
    action: str | None = None,
    offset: int = Query(default=0, ge=0),
    page_limit: int = Query(default=50, alias="pageLimit"),
) -> PaginatedAdminAuditResponse:
    rows = await require_admin_audit_store(request).list(
        tenant_id=principal.tenant_id,
        limit=max(1, min(limit or 1000, 1000)),
        category=category,
        action=action,
    )
    page = paginate(rows, offset=offset, limit=clamp_limit(page_limit))
    return PaginatedAdminAuditResponse(
        items=[audit_response(row) for row in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
    )


@router.get("/api/admin/audits/export")
@router.get("/v1/admin/audits/export")
async def export_admin_audits(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("audit:export"))],
    category: str | None = None,
    action: str | None = None,
    limit: int = Query(default=5000, ge=1, le=50000),
) -> Response:
    store = require_admin_audit_store(request)
    rows = await store.list(
        tenant_id=principal.tenant_id,
        limit=limit,
        category=category,
        action=action,
    )
    await record_admin_audit(
        store=store,
        tenant_id=principal.tenant_id,
        category="audit",
        action=AdminAuditAction.EXPORT,
        actor=current_actor(principal),
        detail=f"rows={len(rows)}",
    )
    filename = f"audit-export-{datetime.now().astimezone().strftime('%Y%m%d-%H%M')}.csv"
    return Response(
        content=build_audit_csv(rows),
        media_type="text/csv; charset=UTF-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/api/admin/audits/{audit_id}/rollback-preview",
    response_model=AdminAuditRollbackPreviewResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/audits/{audit_id}/rollback-preview",
    response_model=AdminAuditRollbackPreviewResponse,
    response_model_by_alias=True,
)
async def preview_admin_audit_rollback(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("audit:read"))],
    audit_id: str,
) -> AdminAuditRollbackPreviewResponse:
    log = await find_admin_audit_log(request, tenant_id=principal.tenant_id, audit_id=audit_id)
    return audit_rollback_preview_response(log)


@router.post(
    "/api/admin/audits/{audit_id}/rollback",
    response_model=AdminAuditRollbackResultResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/audits/{audit_id}/rollback",
    response_model=AdminAuditRollbackResultResponse,
    response_model_by_alias=True,
)
async def rollback_admin_audit_entry(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("audit:export"))],
    audit_id: str,
) -> AdminAuditRollbackResultResponse:
    await find_admin_audit_log(request, tenant_id=principal.tenant_id, audit_id=audit_id)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "automatic audit rollback is not available; use rollback preview for manual recovery"
        ),
    )


@router.get(
    "/api/ops/dashboard",
    response_model=OpsDashboardResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/ops/dashboard",
    response_model=OpsDashboardResponse,
    response_model_by_alias=True,
)
async def ops_dashboard(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    names: Annotated[list[str] | None, Query()] = None,
) -> OpsDashboardResponse:
    metric_names = [name for name in names or [] if name.strip()] or list(DEFAULT_METRIC_NAMES)
    generated_at = datetime.now().astimezone()
    tool_invocations = await tool_invocations_between(
        request,
        tenant_id=principal.tenant_id,
        from_time=generated_at - timedelta(days=7),
        to_time=generated_at + timedelta(seconds=1),
        limit=500,
    )
    tool_status_counts = tool_invocation_status_counts(tool_invocations)
    return OpsDashboardResponse(
        generatedAt=epoch_millis(generated_at),
        ragEnabled=True,
        mcp=await mcp_summary(request, tenant_id=principal.tenant_id),
        scheduler=await scheduler_summary(request, tenant_id=principal.tenant_id),
        recentSchedulerExecutions=await recent_scheduler_executions(
            request, tenant_id=principal.tenant_id
        ),
        approvals=await approval_summary(request, tenant_id=principal.tenant_id),
        durableQueue=await durable_queue_summary(request, tenant_id=principal.tenant_id),
        toolLifecycleStatusCounts=tool_status_counts,
        toolLifecycleAttentionCount=tool_lifecycle_attention_count(tool_status_counts),
        responseTrust=ResponseTrustSummary(),
        employeeValue=EmployeeValueSummary(),
        recentTrustEvents=[],
        metrics=[
            OpsMetricSnapshot(name=name, meterCount=0, measurements={}) for name in metric_names
        ],
        releaseReadiness=ops_release_readiness_summary(get_container(request).settings),
    )


@router.get("/api/ops/metrics/names", response_model=list[str])
@router.get("/v1/ops/metrics/names", response_model=list[str])
async def ops_metric_names(
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> list[str]:
    del principal
    return sorted({*DEFAULT_METRIC_NAMES, *reactor_prometheus_metric_names()})


@router.get("/api/admin/tool-calls")
@router.get("/v1/admin/tool-calls")
async def list_tool_calls(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:read"))],
    runId: str | None = None,
    status: str | None = None,
    days: int = 7,
    limit: int = 100,
) -> list[dict[str, object]]:
    status_filter = parse_tool_invocation_status_filter(status)
    from_time = datetime.now(UTC) - timedelta(days=max(1, min(days, 90)))
    records = await tool_invocations_between(
        request,
        tenant_id=principal.tenant_id,
        from_time=from_time,
        to_time=datetime.now(UTC) + timedelta(seconds=1),
        limit=max(1, min(limit, 500)),
        status=status_filter,
    )
    if runId is not None and runId.strip():
        records = [record for record in records if record.run_id == runId]
    return [tool_call_response(record) for record in records]


@router.post("/api/admin/tool-calls/reconcile-stale")
@router.post("/v1/admin/tool-calls/reconcile-stale")
async def reconcile_stale_tool_calls(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
    olderThanSeconds: int = Query(default=900, ge=60, le=604800),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    store = require_tool_invocation_store(request)
    older_than = datetime.now(UTC) - timedelta(seconds=olderThanSeconds)
    invocation_ids = list(
        await store.mark_stale_started_for_reconciliation(
            tenant_id=principal.tenant_id,
            older_than=older_than,
            limit=limit,
        )
    )
    await record_tool_reconciliation_audit(
        request=request,
        principal=principal,
        marked=len(invocation_ids),
        older_than_seconds=olderThanSeconds,
    )
    return {
        "status": "marked_for_reconciliation",
        "tenantId": principal.tenant_id,
        "marked": len(invocation_ids),
        "olderThanSeconds": olderThanSeconds,
    }


@router.get("/api/admin/tool-calls/ranking")
@router.get("/v1/admin/tool-calls/ranking")
async def rank_tool_calls(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:read"))],
    days: int = 30,
    status: str | None = None,
) -> list[ToolUsageSummaryResponse]:
    status_filter = parse_tool_invocation_status_filter(status)
    from_time = datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))
    records = await tool_invocations_between(
        request,
        tenant_id=principal.tenant_id,
        from_time=from_time,
        to_time=datetime.now(UTC) + timedelta(seconds=1),
        limit=500,
        status=status_filter,
    )
    return tool_ranking(records)


@router.post("/api/admin/metrics/ingest/mcp-health", status_code=status.HTTP_202_ACCEPTED)
@router.post("/v1/admin/metrics/ingest/mcp-health", status_code=status.HTTP_202_ACCEPTED)
async def ingest_mcp_health_metric(
    request: Request,
    body: McpHealthMetricRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> dict[str, str]:
    await publish_metric_event_or_503(
        request, mcp_health_metric_event(body, tenant_id=principal.tenant_id)
    )
    return {"status": "accepted"}


@router.post("/api/admin/metrics/ingest/tool-call", status_code=status.HTTP_202_ACCEPTED)
@router.post("/v1/admin/metrics/ingest/tool-call", status_code=status.HTTP_202_ACCEPTED)
async def ingest_tool_call_metric(
    request: Request,
    body: ToolCallMetricRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> dict[str, str]:
    await publish_metric_event_or_503(
        request, tool_call_metric_event(body, tenant_id=principal.tenant_id)
    )
    return {"status": "accepted"}


@router.post("/api/admin/metrics/ingest/eval-result", status_code=status.HTTP_202_ACCEPTED)
@router.post("/v1/admin/metrics/ingest/eval-result", status_code=status.HTTP_202_ACCEPTED)
async def ingest_eval_result_metric(
    request: Request,
    body: EvalMetricResultRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> dict[str, str]:
    await publish_metric_event_or_503(
        request, eval_result_metric_event(body, tenant_id=principal.tenant_id)
    )
    return {"status": "accepted"}


@router.post("/api/admin/metrics/ingest/batch")
@router.post("/v1/admin/metrics/ingest/batch")
async def ingest_mcp_health_metric_batch(
    request: Request,
    body: list[McpHealthMetricRequest],
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> dict[str, int]:
    require_metric_batch_size(len(body))
    accepted, dropped = await publish_metric_events(
        request, [mcp_health_metric_event(item, tenant_id=principal.tenant_id) for item in body]
    )
    return {"accepted": accepted, "dropped": dropped}


@router.post("/api/admin/metrics/ingest/eval-results")
@router.post("/v1/admin/metrics/ingest/eval-results")
async def ingest_eval_result_metric_batch(
    request: Request,
    body: EvalRunMetricResultsRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> dict[str, int | str]:
    if not body.results:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Results list must not be empty",
        )
    require_metric_batch_size(len(body.results))
    accepted, dropped = await publish_metric_events(
        request,
        [
            eval_test_case_metric_event(
                tenant_id=principal.tenant_id,
                eval_run_id=body.evalRunId,
                result=result,
            )
            for result in body.results
        ],
    )
    return {"evalRunId": body.evalRunId, "accepted": accepted, "dropped": dropped}


@router.get(
    "/api/admin/rag/stats",
    response_model=RagStatsResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/rag/stats",
    response_model=RagStatsResponse,
    response_model_by_alias=True,
)
async def rag_stats(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> RagStatsResponse:
    rows = await require_rag_diagnostics_store(request).stats_by_collection(
        tenant_id=principal.tenant_id
    )
    return rag_stats_response(tenant_id=principal.tenant_id, rows=rows)


@router.post(
    "/api/admin/rag/seed-policy",
    response_model=PolicyRagSeedResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/rag/seed-policy",
    response_model=PolicyRagSeedResponse,
    response_model_by_alias=True,
)
async def seed_policy_rag(
    request: Request,
    body: PolicyRagSeedRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> PolicyRagSeedResponse:
    started_at = datetime.now(UTC)
    sink = require_rag_diagnostics_store(request)
    keys: list[str] = []
    chunk_count = 0
    for entry in body.entries:
        try:
            seeded_chunks = await seed_policy_rag_entry(
                sink=sink,
                tenant_id=principal.tenant_id,
                entry=entry,
            )
        except Exception:
            seeded_chunks = None
        if seeded_chunks is None:
            continue
        chunk_count += seeded_chunks
        keys.append(entry.key)
    duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
    return PolicyRagSeedResponse(
        documentCount=len(keys),
        chunkCount=chunk_count,
        keys=keys,
        durationMs=duration_ms,
    )


@router.get("/api/admin/rag-analytics/status")
@router.get("/v1/admin/rag-analytics/status")
async def rag_analytics_status(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> list[dict[str, object]]:
    return await require_rag_diagnostics_store(request).rag_analytics_status_summary(
        tenant_id=principal.tenant_id
    )


@router.get("/api/admin/rag-analytics/by-channel")
@router.get("/v1/admin/rag-analytics/by-channel")
async def rag_analytics_by_channel(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    days: int = Query(default=30, ge=1, le=90),
) -> list[dict[str, object]]:
    from_time = datetime.now(UTC) - timedelta(days=days)
    return await require_rag_diagnostics_store(request).rag_analytics_by_channel(
        tenant_id=principal.tenant_id,
        from_time=from_time,
    )


@router.get("/api/admin/conversation-analytics/by-channel")
@router.get("/v1/admin/conversation-analytics/by-channel")
async def conversation_analytics_by_channel(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    days: int = Query(default=30, ge=1, le=90),
) -> list[dict[str, object]]:
    from_time = datetime.now(UTC) - timedelta(days=days)
    runs = await conversation_runs_since(
        request, tenant_id=principal.tenant_id, from_time=from_time
    )
    return conversation_by_channel_rows(runs)


@router.get("/api/admin/conversation-analytics/failure-patterns")
@router.get("/v1/admin/conversation-analytics/failure-patterns")
async def conversation_analytics_failure_patterns(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    days: int = Query(default=30, ge=1, le=90),
) -> list[dict[str, object]]:
    from_time = datetime.now(UTC) - timedelta(days=days)
    runs = await conversation_runs_since(
        request, tenant_id=principal.tenant_id, from_time=from_time
    )
    return conversation_failure_pattern_rows(runs)


@router.get("/api/admin/conversation-analytics/latency-distribution")
@router.get("/v1/admin/conversation-analytics/latency-distribution")
async def conversation_analytics_latency_distribution(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    days: int = Query(default=7, ge=1, le=90),
) -> list[dict[str, object]]:
    from_time = datetime.now(UTC) - timedelta(days=days)
    runs = await conversation_runs_since(
        request, tenant_id=principal.tenant_id, from_time=from_time
    )
    return conversation_latency_distribution_rows(runs)


@router.get("/api/admin/followup-suggestions/stats")
@router.get("/v1/admin/followup-suggestions/stats")
async def followup_suggestion_stats(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    hours: int = Query(default=24),
) -> dict[str, object]:
    del principal
    window_hours = max(1, min(hours, 168))
    stats = await maybe_await(
        require_followup_suggestion_store(request).aggregate_stats(
            window_hours=window_hours,
        )
    )
    return {"windowHours": window_hours, **dict(stats)}


@router.get(
    "/api/admin/platform/health",
    response_model=PlatformHealthResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/platform/health",
    response_model=PlatformHealthResponse,
    response_model_by_alias=True,
)
async def platform_health(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> PlatformHealthResponse:
    del principal
    active_alert_count = await active_alerts_count(request)
    stats = await response_cache_stats(request)
    return PlatformHealthResponse(
        pipelineBufferUsage=0.0,
        pipelineDropRate=0.0,
        pipelineWriteLatencyMs=0.0,
        # Pipeline gauges are not instrumented yet. Keep the retained numeric
        # fields for compatibility, but make the absence explicit so clients
        # never interpret these placeholders as live zeroes.
        pipelineMetricsAvailable=False,
        responseCacheEnabled=bool(stats.get("enabled", False)),
        activeAlerts=active_alert_count,
        cacheExactHits=int_stat(stats, "total_exact_hits"),
        cacheSemanticHits=int_stat(stats, "total_semantic_hits"),
        cacheMisses=int_stat(stats, "total_misses"),
    )


@router.get(
    "/api/admin/platform/vectorstore/stats",
    response_model=VectorStoreStatsResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/platform/vectorstore/stats",
    response_model=VectorStoreStatsResponse,
    response_model_by_alias=True,
)
async def platform_vectorstore_stats(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> VectorStoreStatsResponse:
    rows = await optional_rag_stats_rows(request, tenant_id=principal.tenant_id)
    return VectorStoreStatsResponse(
        available=rows is not None,
        documentCount=sum(row.document_count for row in rows or []),
    )


@router.post("/api/admin/task-memory/maintenance/purge-expired")
@router.post("/v1/admin/task-memory/maintenance/purge-expired")
async def purge_expired_task_memory(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> dict[str, object]:
    service = require_task_memory_maintenance(request)
    deleted = int(await maybe_await(service.purge_expired()))
    await record_task_memory_maintenance_audit(
        request=request,
        principal=principal,
        action_name="purge_expired",
        detail=f"deleted={deleted}",
    )
    return {"deleted": deleted, "actor": current_actor(principal)}


@router.post("/api/admin/task-memory/maintenance/purge-terminal")
@router.post("/v1/admin/task-memory/maintenance/purge-terminal")
async def purge_terminal_task_memory(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
    olderThanDays: int = 30,
) -> dict[str, object]:
    if olderThanDays < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="olderThanDays must be >= 1",
        )
    service = require_task_memory_maintenance(request)
    cutoff = datetime.now(UTC) - timedelta(days=olderThanDays)
    purge = getattr(service, "purge_terminal_older_than", None)
    if purge is None:
        purge = getattr(service, "purgeTerminalOlderThan", None)
    if purge is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TaskMemoryMaintenance is not configured",
        )
    deleted = int(await maybe_await(purge(cutoff)))
    await record_task_memory_maintenance_audit(
        request=request,
        principal=principal,
        action_name="purge_terminal",
        detail=f"olderThanDays={olderThanDays} deleted={deleted} cutoff={cutoff.isoformat()}",
    )
    return {"deleted": deleted, "cutoff": cutoff.isoformat()}


@router.get(
    "/api/admin/retention",
    response_model=RetentionPolicyResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/retention",
    response_model=RetentionPolicyResponse,
    response_model_by_alias=True,
)
async def get_retention_policy(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> RetentionPolicyResponse:
    del principal
    return await retention_policy_response(request)


@router.put(
    "/api/admin/retention",
    response_model=RetentionPolicyResponse,
    response_model_by_alias=True,
)
@router.put(
    "/v1/admin/retention",
    response_model=RetentionPolicyResponse,
    response_model_by_alias=True,
)
async def update_retention_policy(
    request: Request,
    body: UpdateRetentionRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> RetentionPolicyResponse:
    store = runtime_settings_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="RuntimeSettingsService is not configured",
        )
    updates = retention_updates(body)
    for key, value in updates.items():
        await maybe_await(
            store.set(
                RuntimeSettingUpdate(
                    tenant_id=GLOBAL_TENANT_ID,
                    key=key,
                    value=str(value),
                    value_type="INT",
                    category="retention",
                    updated_by=principal.user_id,
                )
            )
        )
    await record_admin_audit_if_configured(
        request=request,
        tenant_id=principal.tenant_id,
        category="retention",
        action=AdminAuditAction.UPDATE,
        actor=current_actor(principal),
        resource_type="retention_policy",
        resource_id=None,
        detail=str(updates),
    )
    return await retention_policy_response(request)


@router.get(
    "/api/admin/platform/cache/stats",
    response_model=CacheStatsResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/platform/cache/stats",
    response_model=CacheStatsResponse,
    response_model_by_alias=True,
)
async def cache_stats(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> CacheStatsResponse:
    del principal
    cache = response_cache(request)
    if cache is None:
        return cache_stats_response(None)
    stats = await maybe_await(cache.stats())
    return cache_stats_response(cast(dict[str, object], stats))


@router.get(
    "/api/admin/traces",
    response_model=list[TraceSummaryResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/traces",
    response_model=list[TraceSummaryResponse],
    response_model_by_alias=True,
)
async def list_traces(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[TraceSummaryResponse]:
    del days
    runs = await require_trace_run_store(request).list_recent_runs(
        tenant_id=principal.tenant_id,
        limit=limit,
    )
    filtered = [
        run
        for run in runs
        if status_filter is None or run.status.lower() == status_filter.strip().lower()
    ]
    return [trace_summary_response(run) for run in filtered]


@router.get("/api/admin/debug/replay")
@router.get("/v1/admin/debug/replay")
async def list_debug_replay_captures(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
    limit: int = 50,
) -> list[dict[str, object]]:
    store = debug_replay_store(request)
    if store is None:
        return []
    captures = await maybe_await(store.list(principal.tenant_id, max(1, min(limit, 200))))
    return [debug_replay_response(capture) for capture in captures]


@router.get("/api/admin/debug/replay/{capture_id}")
@router.get("/v1/admin/debug/replay/{capture_id}")
async def get_debug_replay_capture(
    request: Request,
    capture_id: UUID,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> dict[str, object]:
    store = debug_replay_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DebugReplayStore not configured",
        )
    capture = await maybe_await(store.find_by_id(capture_id))
    if capture is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"replay capture not found: {capture_id}",
        )
    if str(capture_value(capture, "tenantId", "tenant_id")) != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"replay capture not found: {capture_id}",
        )
    return debug_replay_response(capture)


@router.get("/api/admin/observability/smoke/diagnostics")
@router.get("/v1/admin/observability/smoke/diagnostics")
async def get_observability_smoke_diagnostics(
    request: Request,
    _: Annotated[AuthPrincipal, Depends(require_permission("settings:read"))],
) -> dict[str, object]:
    settings = get_container(request).settings
    return observability_smoke_diagnostics(
        config=ObservabilitySmokeConfig(
            trace_exporter=settings.observability_trace_exporter,
            langsmith_project=settings.observability_langsmith_project
            or "reactor-observability-smoke",
            langsmith_endpoint=settings.observability_langsmith_endpoint
            or "https://api.smith.langchain.com",
        ),
        environ=observability_smoke_environ(settings),
    )


@router.post("/api/admin/provider/smoke")
@router.post("/v1/admin/provider/smoke")
async def run_admin_provider_smoke(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> dict[str, Any]:
    settings = get_container(request).settings
    report = await asyncio.to_thread(run_configured_backend_provider_smoke, settings)
    provider = str(report.get("provider", settings.default_model_provider))
    model = str(report.get("model", settings.default_model))
    report_status = str(report.get("status", "failed"))
    await record_admin_audit_if_configured(
        request=request,
        tenant_id=principal.tenant_id,
        category="release_smoke",
        action=AdminAuditAction.SIMULATE,
        actor=current_actor(principal),
        resource_type="provider",
        resource_id=f"{provider}:{model}",
        detail=f"status={report_status} ok={str(report.get('ok') is True).lower()}",
    )
    return report


@router.post("/api/admin/slack/smoke")
@router.post("/v1/admin/slack/smoke")
async def run_admin_slack_smoke(
    body: ExternalSideEffectSmokeRequest,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> dict[str, Any]:
    del body
    settings = get_container(request).settings
    report = await asyncio.to_thread(run_configured_slack_smoke, settings)
    target_mapping = safe_object_mapping(report.get("liveTarget")) or {}
    channel_id = optional_string(target_mapping.get("channelId")) or "unconfigured"
    report_status = str(report.get("status", "failed"))
    await record_admin_audit_if_configured(
        request=request,
        tenant_id=principal.tenant_id,
        category="release_smoke",
        action=AdminAuditAction.SIMULATE,
        actor=current_actor(principal),
        resource_type="slack",
        resource_id=channel_id,
        detail=(
            f"status={report_status} ok={str(report.get('ok') is True).lower()} "
            "external_side_effects=confirmed"
        ),
    )
    return report


@router.post("/api/admin/a2a/smoke")
@router.post("/v1/admin/a2a/smoke")
async def run_admin_a2a_smoke(
    body: ExternalSideEffectSmokeRequest,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> dict[str, Any]:
    del body
    report = await asyncio.to_thread(run_configured_a2a_smoke)
    base_url = optional_string(report.get("base_url")) or ""
    host = urlsplit(base_url).hostname or "unconfigured"
    report_status = str(report.get("status", "failed"))
    await record_admin_audit_if_configured(
        request=request,
        tenant_id=principal.tenant_id,
        category="release_smoke",
        action=AdminAuditAction.SIMULATE,
        actor=current_actor(principal),
        resource_type="a2a",
        resource_id=host,
        detail=(
            f"status={report_status} ok={str(report.get('ok') is True).lower()} "
            "external_side_effects=confirmed"
        ),
    )
    return report


@router.post("/api/admin/context-manifest/diagnostics")
@router.post("/v1/admin/context-manifest/diagnostics")
async def diagnose_context_manifest(
    body: ContextManifestDiagnosticsRequest,
    _: Annotated[AuthPrincipal, Depends(require_permission("settings:read"))],
) -> dict[str, object]:
    return context_manifest_diagnostics(body.context_manifest)


@router.get("/api/admin/graph/topology")
@router.get("/v1/admin/graph/topology")
async def get_graph_topology(
    _: Annotated[AuthPrincipal, Depends(require_permission("settings:read"))],
) -> dict[str, object]:
    return graph_topology_evidence()


@router.get("/api/admin/checkpoints/diagnostics")
@router.get("/v1/admin/checkpoints/diagnostics")
async def get_checkpoint_diagnostics(
    _: Annotated[AuthPrincipal, Depends(require_permission("settings:read"))],
) -> dict[str, object]:
    provenance = checkpoint_provenance_evidence()
    diagnostics = provenance.get("diagnosticsSurface")
    if isinstance(diagnostics, dict):
        return {
            "source": provenance["source"],
            "forkApiPaths": diagnostics["forkApiPaths"],
            "stateHistoryApiPaths": diagnostics["stateHistoryApiPaths"],
            "trustedMetadataKeys": diagnostics["trustedMetadataKeys"],
            "userMetadataStrippedKeys": diagnostics["userMetadataStrippedKeys"],
            "replayCoverage": provenance["replayCoverage"],
            "storageSemantics": provenance["storageSemantics"],
        }
    return {
        "source": provenance["source"],
        "forkApiPaths": ["/v1/runs/{run_id}/fork"],
        "stateHistoryApiPaths": [
            "/api/admin/debug/state-history/{run_id}",
            "/v1/admin/debug/state-history/{run_id}",
        ],
        "trustedMetadataKeys": [
            "source",
            "forkedFromRunId",
            "forkedFromThreadId",
            "forkedFromCheckpointNs",
            "forkedFromCheckpointId",
            "forkTargetThreadId",
            "forkTargetCheckpointNs",
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
        ],
        "replayCoverage": provenance["replayCoverage"],
        "storageSemantics": provenance["storageSemantics"],
    }


@router.get("/api/admin/durable-queue/diagnostics")
@router.get("/v1/admin/durable-queue/diagnostics")
async def get_durable_queue_diagnostics(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:read"))],
) -> dict[str, object]:
    store = require_durable_store(request)
    rows = await maybe_await(store.durable_queue_diagnostics(tenant_id=principal.tenant_id))
    return durable_queue_diagnostics_response(tenant_id=principal.tenant_id, rows=rows)


@router.post("/api/admin/durable-queue/release-expired")
@router.post("/v1/admin/durable-queue/release-expired")
async def release_expired_durable_queue_leases(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> dict[str, object]:
    store = require_durable_store(request)
    released = int(
        await maybe_await(store.release_expired_run_queue(tenant_id=principal.tenant_id))
    )
    await record_durable_queue_audit(
        request=request,
        principal=principal,
        action_name="release_expired",
        detail=f"released={released}",
    )
    return {
        "status": "released",
        "tenantId": principal.tenant_id,
        "released": released,
        "actor": current_actor(principal),
    }


@router.get("/api/admin/debug/state-history/{run_id}")
@router.get("/v1/admin/debug/state-history/{run_id}")
async def get_debug_state_history(
    request: Request,
    run_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
    limit: int = Query(default=25, ge=1, le=100),
) -> dict[str, object]:
    run = await admin_load_tenant_session(request, run_id, tenant_id=principal.tenant_id)
    checkpointer = graph_checkpointer(request)
    if checkpointer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="graph checkpoint history is not configured",
        )
    history = await read_graph_state_history(
        checkpointer,
        run_id=run.run_id,
        tenant_id=principal.tenant_id,
        thread_id=run.thread_id,
        checkpoint_ns=run.checkpoint_ns,
        limit=limit,
    )
    response = history.as_response()
    next_actions = state_history_next_actions(response)
    if next_actions:
        response["nextActions"] = next_actions
    return response


def state_history_next_actions(history: Mapping[str, object]) -> list[dict[str, str]]:
    run_id = history_text_value(history, "runId", "run_id")
    if run_id is None:
        return []
    quoted_run_id = quote(run_id)
    actions = [
        {
            "id": "diagnose-run",
            "label": "Inspect this run's current diagnostics",
            "command": f"reactor-runs diagnose {quoted_run_id} --output table",
        },
        {
            "id": "replay-stream",
            "label": "Replay this run's persisted stream events",
            "command": f"reactor-runs replay {quoted_run_id} --output table",
        },
    ]
    checkpoint_action = state_history_latest_checkpoint_action(history, quoted_run_id)
    if checkpoint_action is not None:
        actions.append(checkpoint_action)
    return actions


def state_history_latest_checkpoint_action(
    history: Mapping[str, object],
    quoted_run_id: str,
) -> dict[str, str] | None:
    checkpoint_ns = history_text_value(history, "checkpointNs", "checkpoint_ns")
    if history.get("namespaceFallbackUsed") is True:
        resolved_checkpoint_ns = state_history_resolved_checkpoint_ns(history)
        if resolved_checkpoint_ns is not None:
            checkpoint_ns = resolved_checkpoint_ns
    entries = history.get("entries")
    if not isinstance(entries, Sequence) or isinstance(entries, str | bytes | bytearray):
        return None
    latest_entry: Mapping[str, object] | None = None
    for entry in cast(Sequence[object], entries):
        if isinstance(entry, Mapping):
            latest_entry = cast(Mapping[str, object], entry)
            break
    if latest_entry is None:
        return None
    checkpoint_id = history_text_value(
        latest_entry,
        "checkpointId",
        "checkpoint_id",
    )
    if checkpoint_ns is None or checkpoint_id is None:
        return None
    return {
        "id": "fork-latest-checkpoint",
        "label": "Fork this run from its latest LangGraph checkpoint",
        "command": (
            f"reactor-runs fork {quoted_run_id} --checkpoint-ns {quote(checkpoint_ns)} "
            f"--checkpoint-id {quote(checkpoint_id)} --output table"
        ),
    }


def state_history_resolved_checkpoint_ns(history: Mapping[str, object]) -> str | None:
    for key in ("resolvedCheckpointNs", "resolved_checkpoint_ns"):
        value = history.get(key)
        if isinstance(value, str):
            return value.strip()
    return None


def history_text_value(mapping: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


@router.get(
    "/api/admin/traces/{trace_id}/spans",
    response_model=list[TraceSpanResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/traces/{trace_id}/spans",
    response_model=list[TraceSpanResponse],
    response_model_by_alias=True,
)
async def trace_spans(
    request: Request,
    trace_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> list[TraceSpanResponse]:
    store = require_trace_run_store(request)
    runs = await store.list_recent_runs(tenant_id=principal.tenant_id, limit=200)
    run = next((item for item in runs if trace_id_from_run(item) == trace_id), None)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace not found: {trace_id}",
        )
    events = await store.list_events(
        run_id=run.run_id,
        tenant_id=principal.tenant_id,
        after_sequence=0,
    )
    return [
        trace_span_response(trace_id=trace_id, run_id=run.run_id, event=event) for event in events
    ]


@router.get(
    "/api/admin/metrics/latency/summary",
    response_model=LatencySummaryResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/metrics/latency/summary",
    response_model=LatencySummaryResponse,
    response_model_by_alias=True,
)
async def latency_summary(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    days: int = Query(default=7, ge=1, le=90),
) -> LatencySummaryResponse:
    del days
    runs = await require_trace_run_store(request).list_recent_runs(
        tenant_id=principal.tenant_id,
        limit=500,
    )
    return latency_summary_response([duration_ms_from_run(run) for run in runs])


@router.get(
    "/api/admin/metrics/latency/timeseries",
    response_model=list[LatencyTimeseriesPointResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/metrics/latency/timeseries",
    response_model=list[LatencyTimeseriesPointResponse],
    response_model_by_alias=True,
)
async def latency_timeseries(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    days: int = Query(default=7, ge=1, le=90),
) -> list[LatencyTimeseriesPointResponse]:
    del days
    runs = await require_trace_run_store(request).list_recent_runs(
        tenant_id=principal.tenant_id,
        limit=500,
    )
    return latency_timeseries_response(runs)


@router.post(
    "/api/admin/platform/cache/invalidate",
    response_model=CacheInvalidationResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/platform/cache/invalidate",
    response_model=CacheInvalidationResponse,
    response_model_by_alias=True,
)
async def invalidate_cache(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> CacheInvalidationResponse:
    cache = response_cache(request)
    if cache is None:
        return CacheInvalidationResponse(
            invalidated=False,
            cacheEnabled=False,
            message="Response cache is disabled",
        )
    invalidated = bool(await maybe_await(cache.invalidate_all()))
    await record_cache_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.INVALIDATE_ALL,
        resource_id=None,
    )
    return CacheInvalidationResponse(
        invalidated=invalidated,
        cacheEnabled=True,
        message="Response cache invalidated",
    )


@router.post(
    "/api/admin/platform/cache/invalidate-key",
    response_model=CacheKeyInvalidationResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/platform/cache/invalidate-key",
    response_model=CacheKeyInvalidationResponse,
    response_model_by_alias=True,
)
async def invalidate_cache_key(
    request: Request,
    body: CacheKeyInvalidationRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> CacheKeyInvalidationResponse:
    key = body.key.strip()
    if not key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="key is required")
    cache = response_cache(request)
    if cache is None:
        return CacheKeyInvalidationResponse(invalidated=False, cacheEnabled=False)
    invalidated = bool(await maybe_await(cache.invalidate(key)))
    await record_cache_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.INVALIDATE_KEY,
        resource_id=key,
    )
    return CacheKeyInvalidationResponse(invalidated=invalidated, cacheEnabled=True)


@router.post(
    "/api/admin/platform/cache/invalidate-by-pattern",
    response_model=CachePatternInvalidationResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/platform/cache/invalidate-by-pattern",
    response_model=CachePatternInvalidationResponse,
    response_model_by_alias=True,
)
async def invalidate_cache_by_pattern(
    request: Request,
    body: CachePatternInvalidationRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> CachePatternInvalidationResponse:
    pattern = body.pattern.strip()
    if not pattern:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="pattern is required")
    cache = response_cache(request)
    if cache is None:
        return CachePatternInvalidationResponse(invalidatedCount=0, cacheEnabled=False)
    invalidated_count = int(await maybe_await(cache.invalidate_by_pattern(pattern)))
    await record_cache_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.INVALIDATE_PATTERN,
        resource_id=pattern,
    )
    return CachePatternInvalidationResponse(
        invalidatedCount=invalidated_count,
        cacheEnabled=True,
    )


@router.get(
    "/api/admin/platform/pricing",
    response_model=list[ModelPricingResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/platform/pricing",
    response_model=list[ModelPricingResponse],
    response_model_by_alias=True,
)
async def list_platform_pricing(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> list[ModelPricingResponse]:
    del principal
    rows = await maybe_await(require_model_pricing_store(request).find_all())
    return [model_pricing_response(row) for row in rows]


@router.post(
    "/api/admin/platform/pricing",
    response_model=ModelPricingResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/platform/pricing",
    response_model=ModelPricingResponse,
    response_model_by_alias=True,
)
async def save_platform_pricing(
    request: Request,
    body: ModelPricingRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> ModelPricingResponse:
    pricing = model_pricing_from_request(body)
    try:
        saved = await maybe_await(require_model_pricing_store(request).save(pricing))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    await record_platform_pricing_audit(request=request, principal=principal, pricing=saved)
    return model_pricing_response(saved)


@router.get(
    "/api/admin/platform/users/by-email",
    response_model=AdminUserResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/platform/users/by-email",
    response_model=AdminUserResponse,
    response_model_by_alias=True,
)
async def get_platform_user_by_email(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("user:read"))],
    email: str,
) -> AdminUserResponse:
    del principal
    normalized_email = email.strip()
    if not normalized_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email is required")
    user = await require_user_store(request).find_by_email(normalized_email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found: {normalized_email}",
        )
    return admin_user_response(user)


@router.post(
    "/api/admin/platform/users/{user_id}/role",
    response_model=AdminUserResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/platform/users/{user_id}/role",
    response_model=AdminUserResponse,
    response_model_by_alias=True,
)
async def update_platform_user_role(
    request: Request,
    user_id: str,
    body: UpdateUserRoleRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("user:write"))],
) -> AdminUserResponse:
    next_role = parse_role(body.role)
    if next_role == UserRole.USER and body.role.strip().upper() != UserRole.USER.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid role: {body.role}",
        )
    retains_developer_scope = next_role in {UserRole.ADMIN, UserRole.ADMIN_DEVELOPER}
    if principal.user_id == user_id and not retains_developer_scope:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cannot remove developer scope from current actor",
        )
    store = require_user_store(request)
    user = await store.find_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found: {user_id}",
        )
    updated = await store.update(
        UserRecord(
            id=user.id,
            email=user.email,
            name=user.name,
            password_hash=user.password_hash,
            role=next_role,
            tenant_id=user.tenant_id,
            created_at=user.created_at,
        )
    )
    await record_admin_audit_if_configured(
        request=request,
        tenant_id=principal.tenant_id,
        category="platform_user",
        action=AdminAuditAction.ROLE_UPDATE,
        actor=current_actor(principal),
        resource_type="user",
        resource_id=user_id,
        detail=f"role:{user.role.value}->{next_role.value}",
    )
    return admin_user_response(updated)


@router.get(
    "/api/admin/platform/tenants",
    response_model=list[TenantResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/platform/tenants",
    response_model=list[TenantResponse],
    response_model_by_alias=True,
)
async def list_tenants(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("tenant:read"))],
    tenant_status: str | None = Query(default=None, alias="status"),
) -> list[TenantResponse]:
    del principal
    status_filter = parse_tenant_status_filter(tenant_status)
    tenants = await require_tenant_store(request).find_all(status=status_filter)
    return [tenant_response(tenant) for tenant in tenants]


@router.post(
    "/api/admin/platform/tenants",
    response_model=TenantResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/admin/platform/tenants",
    response_model=TenantResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_platform_tenant(
    request: Request,
    body: TenantCreateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("tenant:write"))],
) -> TenantResponse:
    plan = parse_tenant_plan(body.plan)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid tenant plan: {body.plan}",
        )
    try:
        tenant = await create_tenant(
            require_tenant_store(request),
            name=body.name,
            slug=body.slug,
            plan=plan,
            billing_email=body.billingEmail,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await record_platform_tenant_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.CREATE,
        tenant=tenant,
        detail=f"slug={tenant.slug};plan={tenant.plan.value}",
    )
    return tenant_response(tenant)


@router.get(
    "/api/admin/platform/tenants/analytics",
    response_model=list[TenantAnalyticsSummaryResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/platform/tenants/analytics",
    response_model=list[TenantAnalyticsSummaryResponse],
    response_model_by_alias=True,
)
async def platform_tenant_analytics(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> list[TenantAnalyticsSummaryResponse]:
    del principal
    tenants = await require_tenant_store(request).find_all()
    summaries: list[TenantAnalyticsSummaryResponse] = []
    for tenant in tenants:
        usage = await current_month_usage(request, tenant_id=tenant.id)
        summaries.append(
            TenantAnalyticsSummaryResponse(
                tenantId=tenant.id,
                tenantName=tenant.name,
                plan=tenant.plan.value,
                requests=usage.requests,
                cost=money_string(usage.cost_usd),
                quotaUsagePercent=usage_percent(
                    usage.requests,
                    tenant.quota.max_requests_per_month,
                ),
            )
        )
    return summaries


@router.get(
    "/api/admin/platform/tenants/{tenant_id}",
    response_model=TenantResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/platform/tenants/{tenant_id}",
    response_model=TenantResponse,
    response_model_by_alias=True,
)
async def get_tenant(
    request: Request,
    tenant_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("tenant:read"))],
) -> TenantResponse:
    del principal
    tenant = await require_tenant_store(request).find_by_id(tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant not found: {tenant_id}",
        )
    return tenant_response(tenant)


@router.post(
    "/api/admin/platform/tenants/{tenant_id}/suspend",
    response_model=TenantResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/platform/tenants/{tenant_id}/suspend",
    response_model=TenantResponse,
    response_model_by_alias=True,
)
async def suspend_platform_tenant(
    request: Request,
    tenant_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("tenant:write"))],
) -> TenantResponse:
    try:
        tenant = await suspend_tenant(require_tenant_store(request), tenant_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant not found: {tenant_id}",
        ) from exc
    await record_platform_tenant_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.SUSPEND,
        tenant=tenant,
    )
    return tenant_response(tenant)


@router.post(
    "/api/admin/platform/tenants/{tenant_id}/activate",
    response_model=TenantResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/platform/tenants/{tenant_id}/activate",
    response_model=TenantResponse,
    response_model_by_alias=True,
)
async def activate_platform_tenant(
    request: Request,
    tenant_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("tenant:write"))],
) -> TenantResponse:
    try:
        tenant = await activate_tenant(require_tenant_store(request), tenant_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant not found: {tenant_id}",
        ) from exc
    await record_platform_tenant_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.ACTIVATE,
        tenant=tenant,
    )
    return tenant_response(tenant)


@router.get("/api/admin/sessions/overview")
@router.get("/v1/admin/sessions/overview")
async def admin_sessions_overview(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("session:read"))],
    period: str = Query(default="7d", max_length=32),
) -> dict[str, object]:
    days = admin_period_days(period)
    from_time = datetime.now(UTC) - timedelta(days=days)
    runs = [
        run
        for run in await require_trace_run_store(request).list_recent_runs(
            tenant_id=principal.tenant_id,
            limit=500,
        )
        if parse_datetime(run.created_at) >= from_time
    ]
    status_counts: dict[str, int] = {}
    for run in runs:
        status_counts[run.status] = status_counts.get(run.status, 0) + 1
    return {
        "period": period,
        "days": days,
        "totalSessions": len(runs),
        "statusCounts": dict(sorted(status_counts.items())),
        "uniqueUsers": len({run.user_id for run in runs}),
    }


@router.get("/api/admin/sessions")
@router.get("/v1/admin/sessions")
async def admin_list_sessions(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("session:read"))],
    q: str | None = Query(default=None, max_length=200),
    user_id: str | None = Query(default=None, alias="userId", max_length=128),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
) -> dict[str, object]:
    result = await admin_session_page(
        request,
        tenant_id=principal.tenant_id,
        user_id=user_id,
        q=q,
        offset=offset,
        limit=limit,
    )
    return {
        "items": [admin_session_summary(run) for run in result.items],
        "total": result.total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/api/admin/sessions/{session_id}")
@router.get("/v1/admin/sessions/{session_id}")
async def admin_get_session(
    request: Request,
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("session:read"))],
) -> dict[str, object]:
    session = await admin_load_tenant_session(request, session_id, tenant_id=principal.tenant_id)
    return admin_session_detail(session)


@router.delete("/api/admin/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/v1/admin/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_session(
    request: Request,
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response:
    require_platform_admin_role(principal)
    session = await admin_load_tenant_session(request, session_id, tenant_id=principal.tenant_id)
    deleted = await require_trace_run_store(request).delete_session(run_id=session.run_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    await record_admin_session_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.DELETE,
        session_id=session.run_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/admin/sessions/{session_id}/export", response_model=None)
@router.get("/v1/admin/sessions/{session_id}/export", response_model=None)
async def admin_export_session(
    request: Request,
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("session:export"))],
    format: str = Query(default="json", pattern="^(json|markdown)$"),
) -> Response | dict[str, object]:
    session = await admin_load_tenant_session(request, session_id, tenant_id=principal.tenant_id)
    if format == "markdown":
        return Response(
            content=admin_session_markdown(session),
            media_type="text/markdown",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{safe_admin_filename(session_id)}.md"'
                )
            },
        )
    return {
        "sessionId": session.run_id,
        "exportedAt": datetime.now(UTC).isoformat(),
        "messages": admin_session_messages(session),
    }


@router.get("/api/admin/users")
@router.get("/v1/admin/users")
async def admin_session_users(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("session:read"))],
    q: str | None = Query(default=None, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
) -> dict[str, object]:
    result = await admin_session_page(
        request,
        tenant_id=principal.tenant_id,
        user_id=None,
        q=None,
        offset=0,
        limit=500,
    )
    rows = admin_session_user_rows(result.items)
    if q and q.strip():
        needle = q.strip().lower()
        rows = [row for row in rows if needle in str(row["userId"]).lower()]
    return {
        "items": rows[offset : offset + limit],
        "total": len(rows),
        "offset": offset,
        "limit": limit,
    }


@router.get("/api/admin/users/{user_id}/sessions")
@router.get("/v1/admin/users/{user_id}/sessions")
async def admin_user_sessions(
    request: Request,
    user_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("session:read"))],
    q: str | None = Query(default=None, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
) -> dict[str, object]:
    result = await admin_session_page(
        request,
        tenant_id=principal.tenant_id,
        user_id=user_id,
        q=q,
        offset=offset,
        limit=limit,
    )
    return {
        "items": [admin_session_summary(run) for run in result.items],
        "total": result.total,
        "offset": offset,
        "limit": limit,
    }


@router.post("/api/admin/sessions/{session_id}/tags")
@router.post("/v1/admin/sessions/{session_id}/tags")
async def admin_add_session_tag(
    request: Request,
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    body: Annotated[dict[str, object], Body(default_factory=dict)],
) -> dict[str, object]:
    require_platform_admin_role(principal)
    session = await admin_load_tenant_session(request, session_id, tenant_id=principal.tenant_id)
    label = str(body.get("label", "")).strip()
    if not label:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="label is required")
    tag_id = f"tag_{abs(hash((session.run_id, label))) % 10_000_000}"
    return {
        "id": tag_id,
        "sessionId": session.run_id,
        "label": label,
        "comment": str(body.get("comment")).strip() if body.get("comment") is not None else None,
        "createdBy": current_actor(principal),
    }


@router.delete(
    "/api/admin/sessions/{session_id}/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@router.delete(
    "/v1/admin/sessions/{session_id}/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def admin_remove_session_tag(
    request: Request,
    session_id: str,
    tag_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response:
    require_platform_admin_role(principal)
    await admin_load_tenant_session(request, session_id, tenant_id=principal.tenant_id)
    if not tag_id.strip():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/api/admin/token-cost/by-session",
    response_model=list[TokenCostRowResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/token-cost/by-session",
    response_model=list[TokenCostRowResponse],
    response_model_by_alias=True,
)
async def token_cost_by_session(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    session_id: str = Query(alias="sessionId", min_length=1),
) -> list[TokenCostRowResponse]:
    rows = await maybe_await(
        require_usage_ledger(request).by_session(principal.tenant_id, session_id.strip())
    )
    return [token_cost_row_response(row) for row in rows]


@router.get(
    "/api/admin/token-cost/daily",
    response_model=list[DailyTokenCostResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/token-cost/daily",
    response_model=list[DailyTokenCostResponse],
    response_model_by_alias=True,
)
async def daily_token_cost(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    days: int = Query(default=30, ge=1, le=90),
) -> list[DailyTokenCostResponse]:
    rows = await maybe_await(
        require_usage_ledger(request).daily(
            principal.tenant_id,
            datetime.now().astimezone() - timedelta(days=days),
        )
    )
    return [daily_token_cost_response(row) for row in rows]


@router.get(
    "/api/admin/token-cost/top-expensive",
    response_model=list[TopExpensiveRunResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/token-cost/top-expensive",
    response_model=list[TopExpensiveRunResponse],
    response_model_by_alias=True,
)
async def top_expensive_token_cost(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[TopExpensiveRunResponse]:
    rows = await maybe_await(
        require_usage_ledger(request).top_expensive(
            principal.tenant_id,
            datetime.now().astimezone() - timedelta(days=days),
            limit=limit,
        )
    )
    return [top_expensive_run_response(row) for row in rows]


@router.get("/api/admin/users/usage/top")
@router.get("/v1/admin/users/usage/top")
async def users_usage_top(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    days: int = Query(default=30),
    limit: int = Query(default=20),
) -> list[UserUsageSummaryResponse]:
    from_time, to_time = usage_window(days, max_days=365)
    runs = await tenant_runs_between(
        request,
        tenant_id=principal.tenant_id,
        from_time=from_time,
        to_time=to_time,
    )
    usage_records = await usage_records_between(
        request,
        tenant_id=principal.tenant_id,
        from_time=from_time,
        to_time=to_time,
    )
    return top_users(runs, usage_records)[: max(1, min(limit, 100))]


@router.get("/api/admin/users/usage/cost")
@router.get("/v1/admin/users/usage/cost")
async def users_usage_cost(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    days: int = Query(default=30),
    limit: int = Query(default=20),
) -> list[dict[str, object]]:
    from_time, to_time = usage_window(days, max_days=365)
    runs = await tenant_runs_between(
        request,
        tenant_id=principal.tenant_id,
        from_time=from_time,
        to_time=to_time,
    )
    usage_records = await usage_records_between(
        request,
        tenant_id=principal.tenant_id,
        from_time=from_time,
        to_time=to_time,
    )
    return users_usage_cost_rows(runs, usage_records, limit=max(1, min(limit, 100)))


@router.get("/api/admin/users/usage/daily")
@router.get("/v1/admin/users/usage/daily")
async def users_usage_daily(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    days: int = Query(default=30),
) -> list[dict[str, object]]:
    from_time, to_time = usage_window(days, max_days=90)
    runs = await tenant_runs_between(
        request,
        tenant_id=principal.tenant_id,
        from_time=from_time,
        to_time=to_time,
    )
    usage_records = await usage_records_between(
        request,
        tenant_id=principal.tenant_id,
        from_time=from_time,
        to_time=to_time,
    )
    return users_usage_daily_rows(runs, usage_records)


@router.get("/api/admin/users/usage/by-model")
@router.get("/v1/admin/users/usage/by-model")
async def users_usage_by_model(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    days: int = Query(default=7),
) -> list[dict[str, object]]:
    from_time, to_time = usage_window(days, max_days=90)
    usage_records = await usage_records_between(
        request,
        tenant_id=principal.tenant_id,
        from_time=from_time,
        to_time=to_time,
    )
    return users_usage_by_model_rows(usage_records)


@router.get(
    "/api/admin/platform/alerts/rules",
    response_model=list[AlertRuleResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/platform/alerts/rules",
    response_model=list[AlertRuleResponse],
    response_model_by_alias=True,
)
async def list_alert_rules(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> list[AlertRuleResponse]:
    rules = await maybe_await(
        require_alert_rule_store(request).find_rules_for_tenant(principal.tenant_id)
    )
    return [alert_rule_response(rule) for rule in rules]


@router.post(
    "/api/admin/platform/alerts/rules",
    response_model=AlertRuleResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/platform/alerts/rules",
    response_model=AlertRuleResponse,
    response_model_by_alias=True,
)
async def save_alert_rule(
    request: Request,
    body: AlertRuleRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> AlertRuleResponse:
    try:
        rule = alert_rule_from_request(body, tenant_id=principal.tenant_id)
        saved = await maybe_await(require_alert_rule_store(request).save_rule(rule))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return alert_rule_response(saved)


@router.delete("/api/admin/platform/alerts/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/v1/admin/platform/alerts/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    request: Request,
    rule_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response:
    deleted = await maybe_await(
        require_alert_rule_store(request).delete_rule(rule_id, tenant_id=principal.tenant_id)
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert rule not found: {rule_id}",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/api/admin/platform/alerts",
    response_model=list[AlertInstanceResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/platform/alerts",
    response_model=list[AlertInstanceResponse],
    response_model_by_alias=True,
)
async def active_alerts(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> list[AlertInstanceResponse]:
    alerts = await maybe_await(
        require_alert_rule_store(request).find_active_alerts(tenant_id=principal.tenant_id)
    )
    return [alert_instance_response(alert) for alert in alerts]


@router.get(
    "/api/admin/tenant/quota",
    response_model=TenantQuotaUsageResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/tenant/quota",
    response_model=TenantQuotaUsageResponse,
    response_model_by_alias=True,
)
async def tenant_quota(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> TenantQuotaUsageResponse:
    tenant = await resolve_current_tenant(request, principal)
    usage = await current_month_usage(request, tenant_id=tenant.id)
    return TenantQuotaUsageResponse(
        tenantId=tenant.id,
        quota=tenant_quota_response(tenant),
        usage=TenantUsageResponse(
            requests=usage.requests,
            tokens=usage.tokens,
            costUsd=money_string(usage.cost_usd),
        ),
        requestUsagePercent=usage_percent(usage.requests, tenant.quota.max_requests_per_month),
        tokenUsagePercent=usage_percent(usage.tokens, tenant.quota.max_tokens_per_month),
    )


@router.get(
    "/api/admin/tenant/slo",
    response_model=TenantSloResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/tenant/slo",
    response_model=TenantSloResponse,
    response_model_by_alias=True,
)
async def tenant_slo(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> TenantSloResponse:
    tenant = await resolve_current_tenant(request, principal)
    error_budget = tenant_error_budget(request, tenant_id=tenant.id)
    return TenantSloResponse(
        tenantId=tenant.id,
        sloAvailability=tenant.slo_availability,
        sloLatencyP99Ms=tenant.slo_latency_p99_ms,
        currentAvailability=getattr(error_budget, "current_availability", 1.0),
        latencyP99Ms=0,
        errorBudgetRemaining=getattr(error_budget, "budget_remaining", 1.0),
    )


@router.get(
    "/api/admin/tenant/alerts",
    response_model=list[AlertInstanceResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/tenant/alerts",
    response_model=list[AlertInstanceResponse],
    response_model_by_alias=True,
)
async def tenant_alerts(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> list[AlertInstanceResponse]:
    tenant = await resolve_current_tenant(request, principal)
    alerts = await maybe_await(require_alert_rule_store(request).find_active_alerts())
    return [alert_instance_response(alert) for alert in alerts if alert.tenant_id == tenant.id]


@router.get(
    "/api/admin/tenant/overview",
    response_model=TenantOverviewDashboardResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/tenant/overview",
    response_model=TenantOverviewDashboardResponse,
    response_model_by_alias=True,
)
async def tenant_overview_dashboard(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    from_ms: int | None = Query(default=None, alias="fromMs"),
    to_ms: int | None = Query(default=None, alias="toMs"),
) -> TenantOverviewDashboardResponse:
    tenant = await resolve_current_tenant(request, principal)
    from_time, to_time = resolve_dashboard_time_range(from_ms, to_ms)
    runs = await tenant_runs_between(
        request, tenant_id=tenant.id, from_time=from_time, to_time=to_time
    )
    usage = await current_month_usage(request, tenant_id=tenant.id)
    durations = [duration_ms_from_run(run) for run in runs]
    success_count = len([run for run in runs if run.status == "completed"])
    return TenantOverviewDashboardResponse(
        totalRequests=usage.requests,
        successRate=round(success_count / len(runs), 6) if runs else 1.0,
        avgResponseTimeMs=int(sum(durations) / len(durations)) if durations else 0,
        apdexScore=apdex_score(durations),
        sloAvailability=1.0,
        errorBudgetRemaining=1.0,
        monthlyCost=money_string(usage.cost_usd),
        activeAlerts=await tenant_active_alert_count(request, tenant_id=tenant.id),
    )


@router.get(
    "/api/admin/tenant/usage",
    response_model=TenantUsageDashboardResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/tenant/usage",
    response_model=TenantUsageDashboardResponse,
    response_model_by_alias=True,
)
async def tenant_usage_dashboard(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    from_ms: int | None = Query(default=None, alias="fromMs"),
    to_ms: int | None = Query(default=None, alias="toMs"),
) -> TenantUsageDashboardResponse:
    tenant = await resolve_current_tenant(request, principal)
    from_time, to_time = resolve_dashboard_time_range(from_ms, to_ms)
    runs = await tenant_runs_between(
        request, tenant_id=tenant.id, from_time=from_time, to_time=to_time
    )
    usage_records = await usage_records_between(
        request, tenant_id=tenant.id, from_time=from_time, to_time=to_time
    )
    return TenantUsageDashboardResponse(
        timeSeries=run_time_series(runs),
        channelDistribution=channel_distribution(runs),
        topUsers=top_users(runs, usage_records),
    )


@router.get(
    "/api/admin/tenant/quality",
    response_model=TenantQualityDashboardResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/tenant/quality",
    response_model=TenantQualityDashboardResponse,
    response_model_by_alias=True,
)
async def tenant_quality_dashboard(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    from_ms: int | None = Query(default=None, alias="fromMs"),
    to_ms: int | None = Query(default=None, alias="toMs"),
) -> TenantQualityDashboardResponse:
    tenant = await resolve_current_tenant(request, principal)
    from_time, to_time = resolve_dashboard_time_range(from_ms, to_ms)
    runs = await tenant_runs_between(
        request, tenant_id=tenant.id, from_time=from_time, to_time=to_time
    )
    durations = sorted(duration_ms_from_run(run) for run in runs)
    return TenantQualityDashboardResponse(
        latencyP50=percentile_value(durations, 0.50),
        latencyP95=percentile_value(durations, 0.95),
        latencyP99=percentile_value(durations, 0.99),
        errorDistribution=error_distribution(runs),
    )


@router.get(
    "/api/admin/tenant/tools",
    response_model=TenantToolDashboardResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/tenant/tools",
    response_model=TenantToolDashboardResponse,
    response_model_by_alias=True,
)
async def tenant_tools_dashboard(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    from_ms: int | None = Query(default=None, alias="fromMs"),
    to_ms: int | None = Query(default=None, alias="toMs"),
) -> TenantToolDashboardResponse:
    tenant = await resolve_current_tenant(request, principal)
    from_time, to_time = resolve_dashboard_time_range(from_ms, to_ms)
    invocations = await tool_invocations_between(
        request, tenant_id=tenant.id, from_time=from_time, to_time=to_time
    )
    ranking = tool_ranking(invocations)
    return TenantToolDashboardResponse(
        toolRanking=ranking,
        slowestTools=sorted(ranking, key=lambda item: item.p95DurationMs, reverse=True)[:5],
        statusCounts=tool_invocation_status_counts(invocations),
    )


@router.get(
    "/api/admin/tenant/cost",
    response_model=TenantCostDashboardResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/tenant/cost",
    response_model=TenantCostDashboardResponse,
    response_model_by_alias=True,
)
async def tenant_cost_dashboard(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    from_ms: int | None = Query(default=None, alias="fromMs"),
    to_ms: int | None = Query(default=None, alias="toMs"),
) -> TenantCostDashboardResponse:
    tenant = await resolve_current_tenant(request, principal)
    from_time, to_time = resolve_dashboard_time_range(from_ms, to_ms)
    usage = await current_month_usage(request, tenant_id=tenant.id)
    costs = await cost_by_model(request, tenant_id=tenant.id, from_time=from_time, to_time=to_time)
    return TenantCostDashboardResponse(
        monthlyCost=money_string(usage.cost_usd),
        costByModel={model: money_string(cost) for model, cost in costs.items()},
    )


@router.get("/api/admin/tenant/export/executions")
@router.get("/v1/admin/tenant/export/executions")
async def export_tenant_executions(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("tenant:export"))],
    from_ms: int | None = Query(default=None, alias="fromMs"),
    to_ms: int | None = Query(default=None, alias="toMs"),
) -> Response:
    tenant = await resolve_current_tenant(request, principal)
    from_time, to_time = resolve_dashboard_time_range(from_ms, to_ms)
    runs = await tenant_runs_between(
        request, tenant_id=tenant.id, from_time=from_time, to_time=to_time
    )
    invocations = await tool_invocations_between(
        request, tenant_id=tenant.id, from_time=from_time, to_time=to_time
    )
    return Response(
        content=build_execution_export_csv(runs, invocations),
        media_type="text/csv; charset=UTF-8",
        headers={"Content-Disposition": 'attachment; filename="executions.csv"'},
    )


@router.get("/api/admin/tenant/export/tools")
@router.get("/v1/admin/tenant/export/tools")
async def export_tenant_tools(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("tenant:export"))],
    from_ms: int | None = Query(default=None, alias="fromMs"),
    to_ms: int | None = Query(default=None, alias="toMs"),
) -> Response:
    tenant = await resolve_current_tenant(request, principal)
    from_time, to_time = resolve_dashboard_time_range(from_ms, to_ms)
    invocations = await tool_invocations_between(
        request, tenant_id=tenant.id, from_time=from_time, to_time=to_time
    )
    return Response(
        content=build_tool_export_csv(invocations),
        media_type="text/csv; charset=UTF-8",
        headers={"Content-Disposition": 'attachment; filename="tool_calls.csv"'},
    )


@router.get("/api/admin/evals/runs")
@router.get("/v1/admin/evals/runs")
async def list_eval_dashboard_runs(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("eval:read"))],
    days: int = Query(default=30, ge=1, le=90),
) -> list[dict[str, object]]:
    from_time = datetime.now(UTC) - timedelta(days=days)
    return await require_eval_result_store(request).analytics_runs(
        tenant_id=principal.tenant_id,
        from_time=from_time,
    )


@router.get("/api/admin/evals/pass-rate")
@router.get("/v1/admin/evals/pass-rate")
async def list_eval_dashboard_pass_rate(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("eval:read"))],
    days: int = Query(default=30, ge=1, le=90),
) -> list[dict[str, object]]:
    from_time = datetime.now(UTC) - timedelta(days=days)
    return await require_eval_result_store(request).analytics_pass_rate(
        tenant_id=principal.tenant_id,
        from_time=from_time,
    )


@router.get("/api/admin/slack-activity/channels")
@router.get("/v1/admin/slack-activity/channels")
async def list_slack_activity_channels(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
    days: int = Query(default=30, ge=1, le=90),
) -> list[dict[str, object]]:
    from_time = datetime.now(UTC) - timedelta(days=days)
    runs = await slack_runs_since(request, tenant_id=principal.tenant_id, from_time=from_time)
    usage_by_run = await usage_records_by_run_id(
        request,
        tenant_id=principal.tenant_id,
        run_ids=[run.run_id for run in runs],
    )
    return slack_channel_activity_rows(runs, usage_by_run)


@router.get("/api/admin/slack-activity/daily")
@router.get("/v1/admin/slack-activity/daily")
async def list_slack_activity_daily(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
    days: int = Query(default=30, ge=1, le=90),
) -> list[dict[str, object]]:
    from_time = datetime.now(UTC) - timedelta(days=days)
    runs = await slack_runs_since(request, tenant_id=principal.tenant_id, from_time=from_time)
    return slack_daily_activity_rows(runs)


@router.post(
    "/api/admin/platform/alerts/{alert_id}/resolve",
    response_model=AlertInstanceResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/platform/alerts/{alert_id}/resolve",
    response_model=AlertInstanceResponse,
    response_model_by_alias=True,
)
async def resolve_alert(
    request: Request,
    alert_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> AlertInstanceResponse:
    store = require_alert_rule_store(request)
    resolved = await maybe_await(
        store.resolve_alert(
            alert_id,
            tenant_id=principal.tenant_id,
            actor=current_actor(principal),
        )
    )
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert not found: {alert_id}",
        )
    alert = alert_by_id(store, alert_id, tenant_id=principal.tenant_id)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert not found: {alert_id}",
        )
    return alert_instance_response(alert)


@router.post(
    "/api/admin/platform/alerts/evaluate",
    response_model=AlertEvaluationResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/platform/alerts/evaluate",
    response_model=AlertEvaluationResponse,
    response_model_by_alias=True,
)
async def evaluate_alerts(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> AlertEvaluationResponse:
    del principal
    store = require_alert_rule_store(request)
    result = await AsyncAlertEvaluator(store).evaluate_all()
    return AlertEvaluationResponse(
        status="evaluation complete",
        createdAlerts=len(result.created_alerts),
    )


def admin_audit_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "admin_audit_store", None)
    return accessor() if accessor is not None else None


def require_admin_audit_store(request: Request):
    store = admin_audit_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin audit persistence is not configured",
        )
    return store


def usage_ledger(request: Request):
    container = get_container(request)
    accessor = getattr(container, "usage_ledger", None)
    return accessor() if accessor is not None else None


def require_usage_ledger(request: Request):
    ledger = usage_ledger(request)
    if ledger is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="usage ledger persistence is not configured",
        )
    return ledger


def model_pricing_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "model_pricing_store", None)
    return accessor() if accessor is not None else None


def require_model_pricing_store(request: Request):
    store = model_pricing_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="model pricing persistence is not configured",
        )
    return store


def alert_rule_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "alert_rule_store", None)
    return accessor() if accessor is not None else None


def require_alert_rule_store(request: Request):
    store = alert_rule_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="alert rule persistence is not configured",
        )
    return store


def require_memory_proposal_review_store(request: Request) -> MemoryProposalReviewStore:
    container = get_container(request)
    accessor = getattr(container, "memory_store", None)
    store = accessor() if accessor is not None else None
    if (
        store is None
        or not hasattr(store, "list_proposals")
        or not hasattr(store, "get_proposal")
        or not hasattr(store, "get_memory_item")
        or not hasattr(store, "save_promotion")
        or not hasattr(store, "save_rejection")
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="memory proposal review persistence is not configured",
        )
    return cast(MemoryProposalReviewStore, store)


def memory_proposal_review_response(
    proposal: MemoryProposalRecord,
) -> MemoryProposalReviewResponse:
    return MemoryProposalReviewResponse(
        id=proposal.id,
        tenantId=proposal.tenant_id,
        status=proposal.status,
        proposedContent=proposal.proposed_content,
        subjectType=proposal.namespace.subject_type,
        subjectId=proposal.namespace.subject_id,
        memoryType=proposal.namespace.memory_type,
        visibility=proposal.namespace.visibility,
        extractionModel=proposal.extraction_model,
        extractionPromptVersion=proposal.extraction_prompt_version,
        confidence=proposal.confidence,
        decisionReason=proposal.decision_reason,
        createdAt=proposal.created_at.isoformat(),
    )


def memory_proposal_review_queue_item_response(
    proposal: MemoryProposalRecord,
) -> MemoryProposalReviewQueueItemResponse:
    return MemoryProposalReviewQueueItemResponse(
        id=proposal.id,
        tenantId=proposal.tenant_id,
        status=proposal.status,
        proposedContent=proposal.proposed_content,
        subjectType=proposal.namespace.subject_type,
        subjectId=proposal.namespace.subject_id,
        memoryType=proposal.namespace.memory_type,
        visibility=proposal.namespace.visibility,
        extractionModel=proposal.extraction_model,
        extractionPromptVersion=proposal.extraction_prompt_version,
        confidence=proposal.confidence,
        decisionReason=proposal.decision_reason,
        maintenance=memory_maintenance_response(proposal),
        nextAction=memory_proposal_review_next_action(proposal),
        nextActions=memory_proposal_review_next_actions(proposal),
        createdAt=proposal.created_at.isoformat(),
    )


def memory_proposal_review_next_action(proposal: MemoryProposalRecord) -> str | None:
    if proposal.status != "proposed" or proposal.namespace.subject_type != "user":
        return None
    subject_id = proposal.namespace.subject_id.strip()
    proposal_id = proposal.id.strip()
    if not subject_id or not proposal_id:
        return None
    return f"reactor-memory get --target-user-id {quote(subject_id)} --output table"


def memory_proposal_review_next_actions(proposal: MemoryProposalRecord) -> list[MemoryNextAction]:
    if proposal.status != "proposed" or proposal.namespace.subject_type != "user":
        return []
    subject_id = proposal.namespace.subject_id.strip()
    proposal_id = proposal.id.strip()
    if not subject_id or not proposal_id:
        return []
    actions = [
        MemoryNextAction(
            id="inspect-memory",
            label="Inspect this user's active memory before review",
            command=f"reactor-memory get --target-user-id {quote(subject_id)} --output table",
        ),
        MemoryNextAction(
            id="approve-memory",
            label="Approve this proposed memory",
            command=(
                f"reactor-memory approve {quote(proposal_id)} "
                "--reason 'reviewed and approved memory' --output table"
            ),
        ),
        MemoryNextAction(
            id="reject-memory",
            label="Reject this proposed memory",
            command=(
                f"reactor-memory reject {quote(proposal_id)} "
                "--reason 'sensitive or inaccurate memory' --output table"
            ),
        ),
    ]
    if memory_maintenance_response(proposal) is not None:
        actions.append(
            MemoryNextAction(
                id="review-memory-dependencies",
                label="Review LangMem dependency compatibility before memory release",
                command=MEMORY_DEPENDENCY_REVIEW_COMMAND,
            )
        )
    actions.append(
        MemoryNextAction(
            id="verify-memory-lifecycle",
            label="Verify memory lifecycle hardening before closing the review",
            preflightFile=RELEASE_SMOKE_PREFLIGHT_FILE,
            preflightEnvTemplate=RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
            replatformReadinessFile=REPLATFORM_READINESS_FILE,
            smokePlanFile=RELEASE_SMOKE_PLAN_FILE,
            releaseEvidenceFile=RELEASE_EVIDENCE_FILE,
            releaseReadinessFile=RELEASE_READINESS_FILE,
            readinessReportArg=f"--readiness-report hardening_suite={HARDENING_SUITE_REPORT_FILE}",
            requiredReadinessReports=["hardening_suite"],
            readinessReports={"hardening_suite": HARDENING_SUITE_REPORT_FILE},
            command=MEMORY_LIFECYCLE_GATE_ACTION,
        )
    )
    return actions


def memory_review_item_response(item: MemoryItemRecord) -> MemoryReviewItemResponse:
    return MemoryReviewItemResponse(
        id=item.id,
        tenantId=item.tenant_id,
        status=item.status,
        content=item.content,
        sourceId=item.source_id,
        subjectType=item.namespace.subject_type,
        subjectId=item.namespace.subject_id,
        memoryType=item.namespace.memory_type,
        visibility=item.namespace.visibility,
        confidence=item.confidence,
    )


def approved_memory_next_action(
    item: MemoryItemRecord,
    *,
    superseded_items: Sequence[MemoryItemRecord] = (),
) -> str | None:
    if item.status != "active" or item.namespace.subject_type != "user":
        return None
    subject_id = item.namespace.subject_id.strip()
    if not subject_id:
        return None
    quoted_subject_id = quote(subject_id)
    return f"reactor-memory get --target-user-id {quoted_subject_id} --output table"


def approved_memory_next_actions(
    item: MemoryItemRecord,
    *,
    superseded_items: Sequence[MemoryItemRecord] = (),
    include_dependency_review: bool = False,
) -> list[MemoryNextAction]:
    if item.status != "active" or item.namespace.subject_type != "user":
        return []
    subject_id = item.namespace.subject_id.strip()
    if not subject_id:
        return []
    quoted_subject_id = quote(subject_id)
    actions = [
        MemoryNextAction(
            id="inspect-memory",
            label="Inspect the approved user's active memory",
            command=f"reactor-memory get --target-user-id {quoted_subject_id} --output table",
        ),
        MemoryNextAction(
            id="review-proposals",
            label="Review remaining proposed memories for this user",
            command=(
                "reactor-memory proposals --status proposed "
                f"--subject-id {quoted_subject_id} --output table"
            ),
        ),
    ]
    if include_dependency_review:
        actions.append(
            MemoryNextAction(
                id="review-memory-dependencies",
                label="Review LangMem dependency compatibility before memory release",
                command=MEMORY_DEPENDENCY_REVIEW_COMMAND,
            )
        )
    if superseded_items:
        actions.append(
            MemoryNextAction(
                id="verify-superseded-exclusion",
                label="Verify superseded memory is excluded from model context",
                command=(
                    "uv run pytest tests/unit/test_prompt_assembler.py -q "
                    "-k excludes_superseded_memory"
                ),
            )
        )
    actions.append(
        MemoryNextAction(
            id="verify-memory-lifecycle",
            label="Verify memory lifecycle hardening before closing the review",
            preflightFile=RELEASE_SMOKE_PREFLIGHT_FILE,
            preflightEnvTemplate=RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
            replatformReadinessFile=REPLATFORM_READINESS_FILE,
            smokePlanFile=RELEASE_SMOKE_PLAN_FILE,
            releaseEvidenceFile=RELEASE_EVIDENCE_FILE,
            releaseReadinessFile=RELEASE_READINESS_FILE,
            readinessReportArg=f"--readiness-report hardening_suite={HARDENING_SUITE_REPORT_FILE}",
            requiredReadinessReports=["hardening_suite"],
            readinessReports={"hardening_suite": HARDENING_SUITE_REPORT_FILE},
            command=MEMORY_LIFECYCLE_GATE_ACTION,
        )
    )
    return actions


MEMORY_DEPENDENCY_REVIEW_COMMAND = "uv pip show langmem trustcall langgraph"
MEMORY_DEPENDENCY_REMEDIATION_COMMAND = (
    "monitor upstream trustcall/langmem compatibility; keep "
    "dependency warning visible until "
    "trustcall stops importing langgraph.constants.Send or "
    "Reactor replaces the dependency path"
)


def memory_maintenance_response(
    proposal: MemoryProposalRecord,
) -> MemoryMaintenanceResponse | None:
    contract = proposal.source_payload.get("langmem_manager_contract")
    if not isinstance(contract, Mapping):
        return None
    contract_mapping = cast(Mapping[object, object], contract)
    if (
        contract_mapping.get("factory") != "langmem.create_memory_manager"
        or contract_mapping.get("invoke_api") != "ainvoke"
        or contract_mapping.get("max_steps") != 1
        or contract_mapping.get("enable_deletes") is not False
        or contract_mapping.get("application_owns_deletes") is not True
    ):
        return None
    store_factory = contract_mapping.get("storeFactory") or contract_mapping.get("store_factory")
    return MemoryMaintenanceResponse(
        manager="create_memory_manager",
        storeManager=(
            "create_memory_store_manager"
            if store_factory == "langmem.create_memory_store_manager"
            else None
        ),
        operation="ainvoke",
        maxSteps=1,
        deletePolicy="reactor_owned",
        dependencyReviewCommand=MEMORY_DEPENDENCY_REVIEW_COMMAND,
        dependencyRemediationCommand=MEMORY_DEPENDENCY_REMEDIATION_COMMAND,
        sensitivity=memory_sensitivity_response(proposal),
    )


def memory_sensitivity_response(
    proposal: MemoryProposalRecord,
) -> MemorySensitivityResponse | None:
    sensitivity = proposal.source_payload.get("sensitivity")
    if not isinstance(sensitivity, Mapping):
        return None
    sensitivity_mapping = cast(Mapping[object, object], sensitivity)
    status_value = sensitivity_mapping.get("status")
    policy_value = sensitivity_mapping.get("policy")
    markers_value = sensitivity_mapping.get("markers")
    if not isinstance(status_value, str) or not status_value.strip():
        return None
    if not isinstance(policy_value, str) or not policy_value.strip():
        return None
    markers: list[str] = []
    if isinstance(markers_value, Sequence) and not isinstance(markers_value, str | bytes):
        markers = [
            marker.strip()
            for marker in cast(Sequence[object], markers_value)
            if isinstance(marker, str) and marker.strip()
        ]
    source_value = sensitivity_mapping.get("source")
    return MemorySensitivityResponse(
        status=status_value.strip(),
        policy=policy_value.strip(),
        markers=markers,
        source=(
            source_value.strip() if isinstance(source_value, str) and source_value.strip() else None
        ),
    )


def sensitive_memory_approval_block_detail(
    proposal: MemoryProposalRecord,
) -> dict[str, object]:
    detail: dict[str, object] = {
        "reason": "sensitive_memory_requires_rejection_or_redaction",
        "message": "sensitive memory proposals require rejection or redaction",
        "proposalId": proposal.id,
        "rejectAction": (
            f"reactor-memory reject {quote(proposal.id)} "
            "--reason 'sensitive or inaccurate memory' --output table"
        ),
        "reviewQueueAction": (
            "reactor-memory proposals --status proposed "
            f"--subject-id {quote(proposal.namespace.subject_id)} --output table"
        ),
    }
    sensitivity = memory_sensitivity_response(proposal)
    if sensitivity is not None:
        detail["sensitivity"] = sensitivity.model_dump(by_alias=True)
    detail["nextActions"] = [
        action.model_dump(by_alias=True)
        for action in sensitive_memory_approval_next_actions(proposal)
    ]
    return detail


def sensitive_memory_approval_next_actions(
    proposal: MemoryProposalRecord,
) -> list[MemoryNextAction]:
    proposal_id = proposal.id.strip()
    subject_id = proposal.namespace.subject_id.strip()
    if not proposal_id or not subject_id:
        return []
    return [
        MemoryNextAction(
            id="reject-memory",
            label="Reject this sensitive memory proposal",
            command=(
                f"reactor-memory reject {quote(proposal_id)} "
                "--reason 'sensitive or inaccurate memory' --output table"
            ),
        ),
        MemoryNextAction(
            id="review-proposals",
            label="Review remaining proposed memories for this user",
            command=(
                "reactor-memory proposals --status proposed "
                f"--subject-id {quote(subject_id)} --output table"
            ),
        ),
        MemoryNextAction(
            id="verify-memory-lifecycle",
            label="Verify memory lifecycle hardening before closing the review",
            preflightFile=RELEASE_SMOKE_PREFLIGHT_FILE,
            preflightEnvTemplate=RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
            replatformReadinessFile=REPLATFORM_READINESS_FILE,
            smokePlanFile=RELEASE_SMOKE_PLAN_FILE,
            releaseEvidenceFile=RELEASE_EVIDENCE_FILE,
            releaseReadinessFile=RELEASE_READINESS_FILE,
            readinessReportArg=f"--readiness-report hardening_suite={HARDENING_SUITE_REPORT_FILE}",
            requiredReadinessReports=["hardening_suite"],
            readinessReports={"hardening_suite": HARDENING_SUITE_REPORT_FILE},
            command=MEMORY_LIFECYCLE_GATE_ACTION,
        ),
    ]


def require_rag_diagnostics_store(request: Request):
    store = get_container(request).faq_document_sink()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG diagnostics persistence is not configured",
        )
    return store


def durable_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "durable_store", None)
    return accessor() if accessor is not None else None


def require_durable_store(request: Request):
    store = durable_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="durable queue persistence is not configured",
        )
    return store


def response_cache(request: Request):
    container = get_container(request)
    accessor = getattr(container, "response_cache", None)
    return accessor() if accessor is not None else None


async def response_cache_stats(request: Request) -> dict[str, object]:
    cache = response_cache(request)
    if cache is None:
        return {}
    stats = await maybe_await(cache.stats())
    return cast(dict[str, object], stats)


async def active_alerts_count(request: Request) -> int:
    store = alert_rule_store(request)
    if store is None:
        return 0
    alerts = await maybe_await(store.find_active_alerts())
    return len(alerts)


async def optional_rag_stats_rows(
    request: Request, *, tenant_id: str
) -> list[RagStatsRecord] | None:
    store = get_container(request).faq_document_sink()
    if store is None:
        return None
    rows_result = store.stats_by_collection(tenant_id=tenant_id)
    rows = await rows_result if isawaitable(rows_result) else rows_result
    return list(cast(Sequence[RagStatsRecord], rows))


def trace_run_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "run_store", None)
    return accessor() if accessor is not None else None


def require_trace_run_store(request: Request):
    store = trace_run_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="trace persistence is not configured",
        )
    return store


def require_platform_admin_role(principal: AuthPrincipal) -> None:
    if principal.role is not UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")


async def admin_session_page(
    request: Request,
    *,
    tenant_id: str,
    user_id: str | None,
    q: str | None,
    offset: int,
    limit: int,
) -> SessionListRecord:
    store = require_trace_run_store(request)
    result = await store.list_sessions(
        tenant_id=tenant_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    if not q or not q.strip():
        return result
    needle = q.strip().lower()
    filtered = [
        run
        for run in result.items
        if needle in run.run_id.lower()
        or needle in run.user_id.lower()
        or needle in run.input_text.lower()
        or needle in (run.response_text or "").lower()
    ]
    return SessionListRecord(items=filtered, total=len(filtered))


async def admin_load_tenant_session(
    request: Request,
    session_id: str,
    *,
    tenant_id: str,
) -> SessionRunRecord:
    session = await require_trace_run_store(request).find_session(run_id=session_id)
    if session is None or session.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def admin_session_summary(session: SessionRunRecord) -> dict[str, object]:
    return {
        "sessionId": session.run_id,
        "threadId": session.thread_id,
        "userId": session.user_id,
        "status": session.status,
        "preview": session.input_text[:160],
        "createdAt": session.created_at,
        "updatedAt": session.updated_at,
        "channel": optional_metadata_text(session, "channel") or "api",
        "traceId": trace_id_from_run(session),
    }


def admin_session_detail(session: SessionRunRecord) -> dict[str, object]:
    return {
        **admin_session_summary(session),
        "messages": admin_session_messages(session),
        "metadata": dict(session.metadata),
    }


def admin_session_messages(session: SessionRunRecord) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = [
        {"role": "user", "content": session.input_text, "timestamp": session.created_at}
    ]
    if session.response_text:
        messages.append(
            {"role": "assistant", "content": session.response_text, "timestamp": session.updated_at}
        )
    return messages


def admin_session_markdown(session: SessionRunRecord) -> str:
    lines = [f"# Session: {session.run_id}", ""]
    for message in admin_session_messages(session):
        lines.extend([f"## {message['role']}", "", str(message["content"]), ""])
    return "\n".join(lines)


def safe_admin_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value)[:100]


def admin_period_days(period: str) -> int:
    normalized = period.strip().lower()
    if normalized.endswith("d") and normalized[:-1].isdigit():
        return max(1, min(int(normalized[:-1]), 365))
    if normalized in {"today", "1day"}:
        return 1
    if normalized in {"7days", "week"}:
        return 7
    if normalized in {"30days", "month"}:
        return 30
    if normalized.isdigit():
        return max(1, min(int(normalized), 365))
    return 7


def admin_session_user_rows(runs: Sequence[SessionRunRecord]) -> list[dict[str, object]]:
    grouped: dict[str, list[SessionRunRecord]] = {}
    for run in runs:
        grouped.setdefault(run.user_id, []).append(run)
    rows: list[dict[str, object]] = []
    for user_id, user_runs in grouped.items():
        ordered = sorted(user_runs, key=lambda run: parse_datetime(run.updated_at), reverse=True)
        rows.append(
            {
                "userId": user_id,
                "sessionCount": len(user_runs),
                "lastActiveAt": ordered[0].updated_at,
                "lastSessionId": ordered[0].run_id,
            }
        )
    return sorted(rows, key=lambda row: str(row["lastActiveAt"]), reverse=True)


async def record_admin_session_audit(
    *,
    request: Request,
    principal: AuthPrincipal,
    action: AdminAuditAction,
    session_id: str,
) -> None:
    store = admin_audit_store(request)
    if store is None:
        return
    await store.save(
        AdminAuditLog(
            category="session",
            action=action,
            actor=current_actor(principal),
            resource_type="session",
            resource_id=session_id,
        ),
        tenant_id=principal.tenant_id,
    )


def require_eval_result_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "eval_result_store", None)
    store = accessor() if accessor is not None else None
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="eval result persistence is not configured",
        )
    return store


def require_followup_suggestion_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "followup_suggestion_store", None)
    store = accessor() if accessor is not None else None
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="followup suggestion store is not configured",
        )
    return store


def tenant_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "tenant_store", None)
    return accessor() if accessor is not None else None


def user_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "user_store", None)
    return accessor() if accessor is not None else None


def require_user_store(request: Request):
    store = user_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="user persistence is not configured",
        )
    return store


def runtime_settings_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "runtime_settings_store", None)
    return accessor() if accessor is not None else None


def debug_replay_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "debug_replay_store", None)
    return accessor() if accessor is not None else None


def graph_checkpointer(request: Request):
    return getattr(get_container(request), "checkpointer", None)


def task_memory_maintenance(request: Request):
    container = get_container(request)
    accessor = getattr(container, "task_memory_maintenance", None)
    service = accessor() if accessor is not None else None
    if service is not None:
        return service
    fallback = getattr(container, "memory_store", None)
    store = fallback() if fallback is not None else None
    if store is not None and hasattr(store, "purge_expired"):
        return store
    return None


def require_task_memory_maintenance(request: Request):
    service = task_memory_maintenance(request)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TaskMemoryMaintenance is not configured",
        )
    return service


def require_tenant_store(request: Request):
    store = tenant_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tenant persistence is not configured",
        )
    return store


async def record_cache_audit(
    *,
    request: Request,
    principal: AuthPrincipal,
    action: AdminAuditAction,
    resource_id: str | None,
) -> None:
    store = admin_audit_store(request)
    if store is None:
        return
    await record_admin_audit(
        store=store,
        tenant_id=principal.tenant_id,
        category="platform_cache",
        action=action,
        actor=current_actor(principal),
        resource_type="response_cache",
        resource_id=resource_id,
    )


async def record_platform_tenant_audit(
    *,
    request: Request,
    principal: AuthPrincipal,
    action: AdminAuditAction,
    tenant: TenantRecord,
    detail: str | None = None,
) -> None:
    store = admin_audit_store(request)
    if store is None:
        return
    await record_admin_audit(
        store=store,
        tenant_id=principal.tenant_id,
        category="platform_tenant",
        action=action,
        actor=current_actor(principal),
        resource_type="tenant",
        resource_id=tenant.id,
        detail=detail,
    )


async def record_platform_pricing_audit(
    *,
    request: Request,
    principal: AuthPrincipal,
    pricing: ModelPricing,
) -> None:
    store = admin_audit_store(request)
    if store is None:
        return
    await record_admin_audit(
        store=store,
        tenant_id=principal.tenant_id,
        category="platform_pricing",
        action=AdminAuditAction.UPDATE,
        actor=current_actor(principal),
        resource_type="model_pricing",
        resource_id=pricing.id,
    )


async def record_admin_audit_if_configured(
    *,
    request: Request,
    tenant_id: str,
    category: str,
    action: AdminAuditAction,
    actor: str,
    resource_type: str | None,
    resource_id: str | None,
    detail: str | None = None,
) -> None:
    store = admin_audit_store(request)
    if store is None:
        return
    await record_admin_audit(
        store=store,
        tenant_id=tenant_id,
        category=category,
        action=action,
        actor=actor,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
    )


async def record_task_memory_maintenance_audit(
    *,
    request: Request,
    principal: AuthPrincipal,
    action_name: str,
    detail: str,
) -> None:
    await record_admin_audit_if_configured(
        request=request,
        tenant_id=principal.tenant_id,
        category="task_memory_maintenance",
        action=AdminAuditAction.DELETE,
        actor=current_actor(principal),
        resource_type="task_memory",
        resource_id=action_name,
        detail=detail,
    )


async def record_durable_queue_audit(
    *,
    request: Request,
    principal: AuthPrincipal,
    action_name: str,
    detail: str,
) -> None:
    await record_admin_audit_if_configured(
        request=request,
        tenant_id=principal.tenant_id,
        category="durable_queue",
        action=AdminAuditAction.UPDATE,
        actor=current_actor(principal),
        resource_type="run_queue",
        resource_id=action_name,
        detail=detail,
    )


async def record_tool_reconciliation_audit(
    *,
    request: Request,
    principal: AuthPrincipal,
    marked: int,
    older_than_seconds: int,
) -> None:
    await record_admin_audit_if_configured(
        request=request,
        tenant_id=principal.tenant_id,
        category="tool_invocation_reconciliation",
        action=AdminAuditAction.UPDATE,
        actor=current_actor(principal),
        resource_type="tool_invocation",
        resource_id="reconcile_stale",
        detail=f"marked={marked} older_than_seconds={older_than_seconds}",
    )


async def resolve_current_tenant(request: Request, principal: AuthPrincipal) -> TenantRecord:
    store = require_tenant_store(request)
    tenant = await store.find_by_id(principal.tenant_id)
    if tenant is None:
        tenant = await store.find_by_slug(principal.tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return tenant


async def current_month_usage(request: Request, *, tenant_id: str) -> TenantUsageSummary:
    ledger = usage_ledger(request)
    if ledger is None:
        return TenantUsageSummary(tenant_id=tenant_id)
    accessor = getattr(ledger, "current_month_usage", None)
    if accessor is None:
        return TenantUsageSummary(tenant_id=tenant_id)
    summary = await maybe_await(accessor(tenant_id))
    return TenantUsageSummary(
        tenant_id=tenant_id,
        requests=int(getattr(summary, "requests", 0)),
        tokens=int(getattr(summary, "tokens", 0)),
        cost_usd=cast(Decimal, getattr(summary, "cost_usd", Decimal("0"))),
    )


def resolve_dashboard_time_range(
    from_ms: int | None, to_ms: int | None
) -> tuple[datetime, datetime]:
    to_time = (
        datetime.fromtimestamp(to_ms / 1000, tz=UTC) if to_ms is not None else datetime.now(UTC)
    )
    from_time = (
        datetime.fromtimestamp(from_ms / 1000, tz=UTC)
        if from_ms is not None
        else to_time - timedelta(days=30)
    )
    return from_time, to_time


def usage_window(days: int, *, max_days: int) -> tuple[datetime, datetime]:
    to_time = datetime.now(UTC)
    clamped_days = max(1, min(days, max_days))
    return to_time - timedelta(days=clamped_days), to_time


async def tenant_runs_between(
    request: Request,
    *,
    tenant_id: str,
    from_time: datetime,
    to_time: datetime,
) -> list[SessionRunRecord]:
    store = trace_run_store(request)
    if store is None:
        return []
    runs = await store.list_recent_runs(tenant_id=tenant_id, limit=500)
    return [run for run in runs if from_time <= parse_datetime(run.created_at) < to_time]


async def slack_runs_since(
    request: Request,
    *,
    tenant_id: str,
    from_time: datetime,
) -> list[SessionRunRecord]:
    runs = await require_trace_run_store(request).list_recent_runs(tenant_id=tenant_id, limit=500)
    return [
        run for run in runs if parse_datetime(run.created_at) >= from_time and is_slack_run(run)
    ]


async def conversation_runs_since(
    request: Request,
    *,
    tenant_id: str,
    from_time: datetime,
) -> list[SessionRunRecord]:
    runs = await require_trace_run_store(request).list_recent_runs(tenant_id=tenant_id, limit=500)
    return [run for run in runs if parse_datetime(run.created_at) >= from_time]


async def usage_records_by_run_id(
    request: Request,
    *,
    tenant_id: str,
    run_ids: Sequence[str],
) -> dict[str, list[UsageLedgerRecord]]:
    ledger = usage_ledger(request)
    if ledger is None:
        return {}
    rows_by_run: dict[str, list[UsageLedgerRecord]] = {}
    for run_id in run_ids:
        rows = await maybe_await(ledger.by_session(tenant_id, run_id))
        rows_by_run[run_id] = [row for row in rows if row.run_id == run_id]
    return rows_by_run


async def usage_records_between(
    request: Request,
    *,
    tenant_id: str,
    from_time: datetime,
    to_time: datetime,
) -> list[UsageLedgerRecord]:
    ledger = usage_ledger(request)
    if ledger is None:
        return []
    accessor = getattr(ledger, "records_between", None)
    if accessor is None:
        return []
    return list(await maybe_await(accessor(tenant_id, from_time, to_time)))


async def cost_by_model(
    request: Request,
    *,
    tenant_id: str,
    from_time: datetime,
    to_time: datetime,
) -> dict[str, Decimal]:
    ledger = usage_ledger(request)
    if ledger is None:
        return {}
    accessor = getattr(ledger, "cost_by_model", None)
    if accessor is None:
        return {}
    return cast(dict[str, Decimal], await maybe_await(accessor(tenant_id, from_time, to_time)))


async def tool_invocations_between(
    request: Request,
    *,
    tenant_id: str,
    from_time: datetime,
    to_time: datetime,
    limit: int = 500,
    status: str | None = None,
) -> list[ToolInvocationRecord]:
    container = get_container(request)
    accessor = getattr(container, "tool_invocation_store", None)
    store = accessor() if accessor is not None else None
    if store is None:
        return []
    return list(
        await store.list_between(
            tenant_id=tenant_id,
            from_time=from_time,
            to_time=to_time,
            limit=limit,
            status=status,
        )
    )


def require_tool_invocation_store(request: Request) -> Any:
    container = get_container(request)
    accessor = getattr(container, "tool_invocation_store", None)
    store = accessor() if accessor is not None else None
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tool invocation persistence is not configured",
        )
    return store


async def tenant_active_alert_count(request: Request, *, tenant_id: str) -> int:
    store = alert_rule_store(request)
    if store is None:
        return 0
    alerts = await maybe_await(store.find_active_alerts())
    return len([alert for alert in alerts if alert.tenant_id == tenant_id])


def tenant_error_budget(request: Request, *, tenant_id: str) -> object | None:
    store = alert_rule_store(request)
    if store is None:
        return None
    accessor = getattr(store, "error_budget", None)
    return accessor(tenant_id) if accessor is not None else None


async def record_admin_audit(
    *,
    store: Any,
    tenant_id: str,
    category: str,
    action: AdminAuditAction,
    actor: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: str | None = None,
) -> None:
    try:
        await store.save(
            AdminAuditLog(
                category=category,
                action=action,
                actor=actor,
                resource_type=resource_type,
                resource_id=resource_id,
                detail=detail,
            ),
            tenant_id=tenant_id,
        )
    except TypeError:
        await store.save(
            AdminAuditLog(
                category=category,
                action=action,
                actor=actor,
                resource_type=resource_type,
                resource_id=resource_id,
                detail=detail,
            )
        )
    except Exception:
        return


async def build_doctor_report(request: Request, *, tenant_id: str) -> DoctorReportResponse:
    generated_at = datetime.now(UTC).isoformat()
    sections = [
        doctor_section(
            name="FastAPI Runtime",
            status="OK",
            checks=[
                doctor_check(
                    name="application",
                    status="OK",
                    detail="FastAPI router is responding",
                )
            ],
            message="runtime available",
        ),
        await runtime_settings_doctor_section(request, tenant_id=tenant_id),
        await rag_store_doctor_section(request, tenant_id=tenant_id),
    ]
    status_value = doctor_overall_status(sections)
    return DoctorReportResponse(
        generatedAt=generated_at,
        status=status_value,
        allHealthy=status_value != "ERROR",
        summary=doctor_summary_text(sections),
        sections=sections,
    )


async def runtime_settings_doctor_section(
    request: Request, *, tenant_id: str
) -> DoctorSectionResponse:
    try:
        container = get_container(request)
        accessor = getattr(container, "runtime_settings_store", None)
        store = accessor() if accessor is not None else None
        if store is None:
            return doctor_section(
                name="Runtime Settings",
                status="SKIPPED",
                checks=[
                    doctor_check(
                        name="store",
                        status="SKIPPED",
                        detail="runtime settings store is not configured",
                    )
                ],
                message="not configured",
            )
        list_settings = getattr(store, "list", None)
        if list_settings is not None:
            await maybe_await(list_settings(tenant_id=tenant_id))
        return doctor_section(
            name="Runtime Settings",
            status="OK",
            checks=[
                doctor_check(
                    name="store",
                    status="OK",
                    detail="runtime settings store is configured",
                )
            ],
            message="configured",
        )
    except Exception:
        return doctor_section(
            name="Runtime Settings",
            status="ERROR",
            checks=[
                doctor_check(
                    name="store",
                    status="ERROR",
                    detail="runtime settings diagnostics failed",
                )
            ],
            message="diagnostics failed",
        )


async def rag_store_doctor_section(request: Request, *, tenant_id: str) -> DoctorSectionResponse:
    try:
        rows = await optional_rag_stats_rows(request, tenant_id=tenant_id)
        if rows is None:
            return doctor_section(
                name="RAG Store",
                status="SKIPPED",
                checks=[
                    doctor_check(
                        name="stats",
                        status="SKIPPED",
                        detail="RAG diagnostics persistence is not configured",
                    )
                ],
                message="not configured",
            )
        documents = sum(row.document_count for row in rows)
        chunks = sum(row.chunk_count for row in rows)
        return doctor_section(
            name="RAG Store",
            status="OK",
            checks=[
                doctor_check(
                    name="stats",
                    status="OK",
                    detail=f"documents={documents}, chunks={chunks}",
                )
            ],
            message="configured",
        )
    except Exception:
        return doctor_section(
            name="RAG Store",
            status="ERROR",
            checks=[
                doctor_check(
                    name="stats",
                    status="ERROR",
                    detail="RAG diagnostics failed",
                )
            ],
            message="diagnostics failed",
        )


def doctor_check(*, name: str, status: str, detail: str) -> DoctorCheckResponse:
    return DoctorCheckResponse(name=name, status=status, detail=detail)


def doctor_section(
    *,
    name: str,
    status: str,
    checks: list[DoctorCheckResponse],
    message: str,
) -> DoctorSectionResponse:
    return DoctorSectionResponse(name=name, status=status, checks=checks, message=message)


def doctor_overall_status(sections: Sequence[DoctorSectionResponse]) -> str:
    statuses = {section.status for section in sections}
    if "ERROR" in statuses:
        return "ERROR"
    if "WARN" in statuses:
        return "WARN"
    return "OK"


def doctor_summary_text(sections: Sequence[DoctorSectionResponse]) -> str:
    counts = {status_name: 0 for status_name in ("OK", "WARN", "ERROR", "SKIPPED")}
    for section in sections:
        counts[section.status] = counts.get(section.status, 0) + 1
    return (
        f"{len(sections)} sections - OK {counts['OK']}, WARN {counts['WARN']}, "
        f"ERROR {counts['ERROR']}, SKIPPED {counts['SKIPPED']}"
    )


def render_doctor_response(
    report: DoctorReportResponse, *, request: Request, summary_only: bool
) -> Response:
    status_code = (
        status.HTTP_500_INTERNAL_SERVER_ERROR if report.status == "ERROR" else status.HTTP_200_OK
    )
    headers = {"X-Doctor-Status": report.status}
    accepted = request.headers.get("accept", "").lower()
    if "text/markdown" in accepted or "text/x-markdown" in accepted:
        body = f"*[{report.status}]* {report.summary} _({report.generatedAt})_"
        return Response(
            content=body,
            status_code=status_code,
            media_type="text/markdown",
            headers=headers,
        )
    if "text/plain" in accepted:
        body = f"{report.status} | {report.summary} | {report.generatedAt}"
        return PlainTextResponse(content=body, status_code=status_code, headers=headers)
    payload: dict[str, object]
    if summary_only:
        payload = {
            "summary": report.summary,
            "status": report.status,
            "generatedAt": report.generatedAt,
            "allHealthy": report.allHealthy,
        }
    else:
        payload = report.model_dump(mode="json")
    return JSONResponse(content=payload, status_code=status_code, headers=headers)


async def mcp_summary(request: Request, *, tenant_id: str) -> McpStatusSummary:
    container = get_container(request)
    accessor = getattr(container, "mcp_registry_store", None)
    store = accessor() if accessor is not None else None
    if store is None:
        return McpStatusSummary(total=0, statusCounts={})
    servers = await store.list_servers(tenant_id)
    counts: dict[str, int] = {}
    for server in servers:
        counts[server.status] = counts.get(server.status, 0) + 1
    return McpStatusSummary(total=len(servers), statusCounts=counts)


async def durable_queue_summary(request: Request, *, tenant_id: str) -> DurableQueueSummaryResponse:
    store = durable_store(request)
    if store is None:
        return DurableQueueSummaryResponse(
            status="unavailable",
            tenantId=tenant_id,
            leaseRecovery={
                "retryableStatuses": ["queued", "retryable_failed"],
                "expiredLeaseAction": "retry_or_dead_letter",
                "deadLetterReason": "run_queue_lease_attempts_exhausted",
                "fencingTokenRequired": True,
            },
        )
    rows = await maybe_await(store.durable_queue_diagnostics(tenant_id=tenant_id))
    payload = durable_queue_diagnostics_response(tenant_id=tenant_id, rows=rows)
    return DurableQueueSummaryResponse(
        status=str(payload["status"]),
        tenantId=str(payload["tenantId"]),
        queueStatusCounts=cast(dict[str, int], payload["queueStatusCounts"]),
        queueBacklog=int_diagnostic_count(payload["queueBacklog"]),
        leasedCount=int_diagnostic_count(payload["leasedCount"]),
        deadLetterCount=int_diagnostic_count(payload["deadLetterCount"]),
        leaseRecovery=cast(dict[str, object], payload["leaseRecovery"]),
    )


async def scheduler_summary(request: Request, *, tenant_id: str) -> SchedulerOpsSummary:
    jobs = await scheduler_jobs(request, tenant_id=tenant_id)
    enabled_jobs = [job for job in jobs if job.enabled]
    running = count_status(jobs, JobExecutionStatus.RUNNING)
    failed = len(
        [
            job
            for job in enabled_jobs
            if job.last_status is not None and job.last_status == JobExecutionStatus.FAILED
        ]
    )
    agent_jobs = len([job for job in enabled_jobs if job.job_type == ScheduledJobType.AGENT])
    return SchedulerOpsSummary(
        totalJobs=len(jobs),
        enabledJobs=len(enabled_jobs),
        runningJobs=running,
        failedJobs=failed,
        attentionBacklog=running + failed,
        agentJobs=agent_jobs,
    )


async def scheduler_jobs(request: Request, *, tenant_id: str) -> list[ScheduledJobRecord]:
    container = get_container(request)
    accessor = getattr(container, "scheduler_store", None)
    store = accessor() if accessor is not None else None
    if store is None:
        return []
    return list(await store.list(tenant_id=tenant_id))


async def recent_scheduler_executions(
    request: Request, *, tenant_id: str, limit: int = 6
) -> list[RecentSchedulerExecutionSummary]:
    container = get_container(request)
    accessor = getattr(container, "scheduled_job_execution_store", None)
    store = accessor() if accessor is not None else None
    if store is None:
        return []
    executions: Sequence[ScheduledJobExecutionRecord] = await store.find_recent(
        tenant_id=tenant_id, limit=limit
    )
    return [
        RecentSchedulerExecutionSummary(
            id=execution.id,
            jobId=execution.job_id,
            jobName=execution.job_name,
            jobType=execution.job_type.value if execution.job_type is not None else None,
            status=execution.status.value,
            resultPreview=scheduler_result_preview(execution.result),
            failureReason=scheduler_failure_reason(execution.result),
            dryRun=execution.dry_run,
            durationMs=execution.duration_ms,
            startedAt=epoch_millis(execution.started_at),
            completedAt=optional_epoch_millis(execution.completed_at),
        )
        for execution in executions
    ]


async def approval_summary(request: Request, *, tenant_id: str) -> ApprovalOpsSummary:
    container = get_container(request)
    accessor = getattr(container, "approval_store", None)
    store = accessor() if accessor is not None else None
    if store is None:
        return ApprovalOpsSummary(pendingCount=0)
    pending = await store.list_pending(tenant_id=tenant_id)
    return ApprovalOpsSummary(pendingCount=len(pending))


def count_status(jobs: list[ScheduledJobRecord], status: JobExecutionStatus) -> int:
    return len([job for job in jobs if job.last_status is not None and job.last_status == status])


def audit_response(log: AdminAuditLog) -> AdminAuditResponse:
    return AdminAuditResponse(
        id=log.id,
        category=log.category,
        action=log.action.value,
        actor=masked_admin_account_ref(log.actor),
        resourceType=log.resource_type,
        resourceId=log.resource_id,
        detail=log.detail,
        createdAt=epoch_millis(log.created_at),
    )


async def find_admin_audit_log(request: Request, *, tenant_id: str, audit_id: str) -> AdminAuditLog:
    store = require_admin_audit_store(request)
    finder = getattr(store, "find_by_id", None)
    if callable(finder):
        log = cast(
            AdminAuditLog | None,
            await maybe_await(finder(tenant_id=tenant_id, audit_id=audit_id)),
        )
    else:
        rows = await store.list(tenant_id=tenant_id, limit=1000)
        log = next((row for row in rows if row.id == audit_id), None)
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="admin audit entry not found",
        )
    return log


def audit_rollback_preview_response(log: AdminAuditLog) -> AdminAuditRollbackPreviewResponse:
    return AdminAuditRollbackPreviewResponse(
        summary=(
            f"Audit entry {log.id} requires manual recovery; "
            "automatic rollback executor is not registered."
        ),
        changes=[],
        warnings=[
            "Automatic audit rollback is not registered for this entry.",
            "Use the owning admin console or stored resource history for manual recovery.",
        ],
        resourceLabel=audit_rollback_resource_label(log),
    )


def audit_rollback_resource_label(log: AdminAuditLog) -> str:
    if log.resource_type and log.resource_id:
        return f"{log.resource_type}:{log.resource_id}"
    if log.resource_id:
        return log.resource_id
    if log.resource_type:
        return log.resource_type
    return f"{log.action.value}:{log.id[:8]}"


def token_cost_row_response(record: UsageLedgerRecord) -> TokenCostRowResponse:
    return TokenCostRowResponse(
        runId=record.run_id,
        provider=record.provider,
        model=record.model,
        stepType=record.step_type,
        promptTokens=record.prompt_tokens,
        completionTokens=record.completion_tokens,
        totalTokens=record.total_tokens,
        estimatedCostUsd=money_string(record.estimated_cost_usd),
        occurredAt=epoch_millis(record.occurred_at),
    )


def daily_token_cost_response(summary: DailyUsageSummary) -> DailyTokenCostResponse:
    return DailyTokenCostResponse(
        day=summary.day.isoformat(),
        model=summary.model,
        promptTokens=summary.prompt_tokens,
        completionTokens=summary.completion_tokens,
        totalTokens=summary.total_tokens,
        totalCostUsd=money_string(summary.total_cost_usd),
    )


def top_expensive_run_response(summary: ExpensiveRunSummary) -> TopExpensiveRunResponse:
    return TopExpensiveRunResponse(
        runId=summary.run_id,
        totalTokens=summary.total_tokens,
        totalCostUsd=money_string(summary.total_cost_usd),
        model=summary.model,
        occurredAt=epoch_millis(summary.occurred_at),
    )


def model_pricing_from_request(body: ModelPricingRequest) -> ModelPricing:
    return ModelPricing(
        id=body.id,
        provider=body.provider,
        model=body.model,
        prompt_price_per_1m=body.promptPricePer1m,
        completion_price_per_1m=body.completionPricePer1m,
        cached_input_price_per_1m=body.cachedInputPricePer1m,
        reasoning_price_per_1m=body.reasoningPricePer1m,
        batch_prompt_price_per_1m=body.batchPromptPricePer1m,
        batch_completion_price_per_1m=body.batchCompletionPricePer1m,
        effective_from=body.effectiveFrom,
        effective_to=body.effectiveTo,
    )


def model_pricing_response(pricing: ModelPricing) -> ModelPricingResponse:
    return ModelPricingResponse(
        id=pricing.id,
        provider=pricing.provider,
        model=pricing.model,
        promptPricePer1m=money_string(pricing.prompt_price_per_1m),
        completionPricePer1m=money_string(pricing.completion_price_per_1m),
        cachedInputPricePer1m=money_string(pricing.cached_input_price_per_1m),
        reasoningPricePer1m=money_string(pricing.reasoning_price_per_1m),
        batchPromptPricePer1m=money_string(pricing.batch_prompt_price_per_1m),
        batchCompletionPricePer1m=money_string(pricing.batch_completion_price_per_1m),
        effectiveFrom=pricing.effective_from.isoformat(),
        effectiveTo=pricing.effective_to.isoformat() if pricing.effective_to is not None else None,
    )


def admin_user_response(user: UserRecord) -> AdminUserResponse:
    admin_scope = user.role.admin_scope()
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role.value,
        adminScope=admin_scope.value if admin_scope is not None else None,
        createdAt=user.created_at.isoformat(),
    )


async def retention_policy_response(request: Request) -> RetentionPolicyResponse:
    return RetentionPolicyResponse(
        sessionRetentionDays=await retention_setting_int(
            request, key="retention.session.days", default=90
        ),
        conversationRetentionDays=await retention_setting_int(
            request, key="retention.conversation.days", default=365
        ),
        auditRetentionDays=await retention_setting_int(
            request, key="retention.audit.days", default=730
        ),
        metricRetentionDays=await retention_setting_int(
            request, key="retention.metric.days", default=180
        ),
        checkpointRetentionDays=await retention_setting_int(
            request, key="retention.checkpoint.days", default=30
        ),
    )


async def retention_setting_int(request: Request, *, key: str, default: int) -> int:
    store = runtime_settings_store(request)
    if store is None:
        return default
    find = getattr(store, "find", None)
    if find is None:
        return default
    record = await maybe_await(find(key, tenant_id=GLOBAL_TENANT_ID))
    value = getattr(record, "value", None) if record is not None else None
    if value is None:
        return default
    try:
        return int(str(value))
    except ValueError:
        return default


def retention_updates(body: UpdateRetentionRequest) -> dict[str, int]:
    updates: dict[str, int] = {}
    if body.sessionRetentionDays is not None:
        updates["retention.session.days"] = body.sessionRetentionDays
    if body.conversationRetentionDays is not None:
        updates["retention.conversation.days"] = body.conversationRetentionDays
    if body.auditRetentionDays is not None:
        updates["retention.audit.days"] = body.auditRetentionDays
    if body.metricRetentionDays is not None:
        updates["retention.metric.days"] = body.metricRetentionDays
    if body.checkpointRetentionDays is not None:
        updates["retention.checkpoint.days"] = body.checkpointRetentionDays
    return updates


def debug_replay_response(capture: object) -> dict[str, object]:
    return {
        "id": str(capture_value(capture, "id")),
        "tenantId": str(capture_value(capture, "tenantId", "tenant_id")),
        "userHash": capture_value(capture, "userHash", "user_hash"),
        "capturedAt": stringified_capture_value(capture, "capturedAt", "captured_at"),
        "userPrompt": capture_value(capture, "userPrompt", "user_prompt"),
        "errorCode": capture_value(capture, "errorCode", "error_code"),
        "errorMessage": capture_value(capture, "errorMessage", "error_message"),
        "modelId": capture_value(capture, "modelId", "model_id"),
        "toolsAttempted": capture_value(capture, "toolsAttempted", "tools_attempted") or [],
        "expiresAt": stringified_capture_value(capture, "expiresAt", "expires_at"),
    }


def capture_value(capture: object, *names: str) -> object:
    if isinstance(capture, dict):
        mapping = cast(Mapping[str, object], capture)
        for name in names:
            if name in mapping:
                return mapping[name]
        return None
    for name in names:
        if hasattr(capture, name):
            return getattr(capture, name)
    return None


def stringified_capture_value(capture: object, *names: str) -> str | None:
    value = capture_value(capture, *names)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def slack_channel_activity_rows(
    runs: Sequence[SessionRunRecord],
    usage_by_run: dict[str, list[UsageLedgerRecord]],
) -> list[dict[str, object]]:
    buckets: dict[str, list[SessionRunRecord]] = {}
    for run in runs:
        buckets.setdefault(slack_channel_id(run), []).append(run)
    rows: list[dict[str, object]] = []
    for channel, channel_runs in buckets.items():
        usage = [record for run in channel_runs for record in usage_by_run.get(run.run_id, [])]
        rows.append(
            {
                "channel": channel,
                "session_count": len(channel_runs),
                "unique_users": len({slack_user_id(run) for run in channel_runs}),
                "total_tokens": sum(record.total_tokens for record in usage),
                "total_cost_usd": money_string(
                    sum((record.estimated_cost_usd for record in usage), Decimal("0"))
                ),
                "avg_latency_ms": int(
                    sum(duration_ms_from_run(run) for run in channel_runs) / len(channel_runs)
                ),
            }
        )
    return sorted(rows, key=session_count_sort_key, reverse=True)


def slack_daily_activity_rows(runs: Sequence[SessionRunRecord]) -> list[dict[str, object]]:
    buckets: dict[str, list[SessionRunRecord]] = {}
    for run in runs:
        buckets.setdefault(parse_datetime(run.created_at).date().isoformat(), []).append(run)
    rows: list[dict[str, object]] = []
    for day, day_runs in buckets.items():
        rows.append(
            {
                "day": day,
                "message_count": len(day_runs),
                "unique_users": len({slack_user_id(run) for run in day_runs}),
                "success_count": sum(1 for run in day_runs if run.status == "completed"),
                "failure_count": sum(1 for run in day_runs if run.status != "completed"),
            }
        )
    return sorted(rows, key=lambda row: str(row["day"]), reverse=True)


def conversation_by_channel_rows(runs: Sequence[SessionRunRecord]) -> list[dict[str, object]]:
    buckets: dict[str, list[SessionRunRecord]] = {}
    for run in runs:
        channel = optional_metadata_text(run, "channel") or "unknown"
        buckets.setdefault(channel, []).append(run)
    rows: list[dict[str, object]] = []
    for channel, channel_runs in buckets.items():
        success = sum(1 for run in channel_runs if run.status == "completed")
        failure = len(channel_runs) - success
        rows.append(
            {
                "channel": channel,
                "total": len(channel_runs),
                "success": success,
                "failure": failure,
                "success_rate": round(100.0 * success / len(channel_runs), 1),
                "avg_duration_ms": int(
                    sum(duration_ms_from_run(run) for run in channel_runs) / len(channel_runs)
                ),
            }
        )
    return sorted(rows, key=lambda row: total_sort_key(row), reverse=True)


def conversation_failure_pattern_rows(
    runs: Sequence[SessionRunRecord],
) -> list[dict[str, object]]:
    buckets: dict[str, list[SessionRunRecord]] = {}
    for run in runs:
        if run.status == "completed":
            continue
        error_class = optional_metadata_text(run, "error_class")
        if error_class is None:
            continue
        buckets.setdefault(error_class, []).append(run)
    rows: list[dict[str, object]] = []
    for error_class, failed_runs in buckets.items():
        rows.append(
            {
                "error_class": error_class,
                "count": len(failed_runs),
                "latest": max(parse_datetime(run.updated_at) for run in failed_runs).isoformat(
                    timespec="milliseconds"
                ),
            }
        )
    return sorted(rows, key=lambda row: total_count_sort_key(row), reverse=True)[:20]


def conversation_latency_distribution_rows(
    runs: Sequence[SessionRunRecord],
) -> list[dict[str, object]]:
    ordered_buckets = ("< 1s", "1-3s", "3-5s", "5-10s", "> 10s")
    counts = {bucket: 0 for bucket in ordered_buckets}
    for run in runs:
        counts[latency_bucket(duration_ms_from_run(run))] += 1
    return [{"bucket": bucket, "count": count} for bucket, count in counts.items() if count > 0]


def latency_bucket(duration_ms: int) -> str:
    if duration_ms < 1000:
        return "< 1s"
    if duration_ms < 3000:
        return "1-3s"
    if duration_ms < 5000:
        return "3-5s"
    if duration_ms < 10000:
        return "5-10s"
    return "> 10s"


def session_count_sort_key(row: dict[str, object]) -> int:
    value = row.get("session_count", 0)
    return value if isinstance(value, int) else 0


def total_sort_key(row: dict[str, object]) -> int:
    value = row.get("total", 0)
    return value if isinstance(value, int) else 0


def total_count_sort_key(row: dict[str, object]) -> int:
    value = row.get("count", 0)
    return value if isinstance(value, int) else 0


def tenant_response(tenant: TenantRecord) -> TenantResponse:
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        plan=tenant.plan.value,
        status=tenant.status.value,
        quota=TenantQuotaResponse(
            maxRequestsPerMonth=tenant.quota.max_requests_per_month,
            maxTokensPerMonth=tenant.quota.max_tokens_per_month,
            maxUsers=tenant.quota.max_users,
            maxAgents=tenant.quota.max_agents,
            maxMcpServers=tenant.quota.max_mcp_servers,
        ),
        billingCycleStart=tenant.billing_cycle_start,
        billingEmail=tenant.billing_email,
        sloAvailability=tenant.slo_availability,
        sloLatencyP99Ms=tenant.slo_latency_p99_ms,
        metadata=dict(tenant.metadata),
        createdAt=epoch_millis(tenant.created_at),
        updatedAt=epoch_millis(tenant.updated_at),
    )


def tenant_quota_response(tenant: TenantRecord) -> TenantQuotaResponse:
    return TenantQuotaResponse(
        maxRequestsPerMonth=tenant.quota.max_requests_per_month,
        maxTokensPerMonth=tenant.quota.max_tokens_per_month,
        maxUsers=tenant.quota.max_users,
        maxAgents=tenant.quota.max_agents,
        maxMcpServers=tenant.quota.max_mcp_servers,
    )


def run_time_series(runs: Sequence[SessionRunRecord]) -> list[TimeSeriesPointResponse]:
    buckets: dict[str, int] = {}
    for run in runs:
        bucket = parse_datetime(run.created_at).replace(minute=0, second=0, microsecond=0)
        key = bucket.isoformat()
        buckets[key] = buckets.get(key, 0) + 1
    return [
        TimeSeriesPointResponse(time=bucket, value=float(count))
        for bucket, count in sorted(buckets.items())
    ]


def channel_distribution(runs: Sequence[SessionRunRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for run in runs:
        channel = optional_metadata_text(run, "channel") or "unknown"
        counts[channel] = counts.get(channel, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def top_users(
    runs: Sequence[SessionRunRecord],
    usage_records: Sequence[UsageLedgerRecord],
) -> list[UserUsageSummaryResponse]:
    usage_by_run: dict[str, list[UsageLedgerRecord]] = {}
    for record in usage_records:
        usage_by_run.setdefault(record.run_id, []).append(record)
    summaries: dict[str, UserUsageAggregate] = {}
    for run in runs:
        summary = summaries.setdefault(
            run.user_id,
            UserUsageAggregate(
                requests=0,
                tokens=0,
                cost=Decimal("0"),
                last_activity=parse_datetime(run.updated_at),
            ),
        )
        records = usage_by_run.get(run.run_id, [])
        summary.requests += 1
        summary.tokens += sum(record.total_tokens for record in records)
        summary.cost += sum(
            (record.estimated_cost_usd for record in records),
            Decimal("0"),
        )
        summary.last_activity = max(summary.last_activity, parse_datetime(run.updated_at))
    rows = [
        UserUsageSummaryResponse(
            userLabel=user_id,
            requests=summary.requests,
            tokens=summary.tokens,
            costUsd=float(summary.cost),
            lastActivity=epoch_millis(summary.last_activity),
        )
        for user_id, summary in summaries.items()
    ]
    return sorted(rows, key=lambda row: (row.tokens, row.requests), reverse=True)[:10]


def users_usage_cost_rows(
    runs: Sequence[SessionRunRecord],
    usage_records: Sequence[UsageLedgerRecord],
    *,
    limit: int,
) -> list[dict[str, object]]:
    usage_by_run = usage_records_by_run(usage_records)
    summaries: dict[str, UserUsageAggregate] = {}
    durations: dict[str, list[int]] = {}
    for run in runs:
        user_id = run.user_id or f"channel:{optional_metadata_text(run, 'channel') or 'unknown'}"
        summary = summaries.setdefault(
            user_id,
            UserUsageAggregate(
                requests=0,
                tokens=0,
                cost=Decimal("0"),
                last_activity=parse_datetime(run.updated_at),
            ),
        )
        records = usage_by_run.get(run.run_id, [])
        summary.requests += 1
        summary.tokens += sum(record.total_tokens for record in records)
        summary.cost += sum(
            (record.estimated_cost_usd for record in records),
            Decimal("0"),
        )
        summary.last_activity = max(summary.last_activity, parse_datetime(run.updated_at))
        durations.setdefault(user_id, []).append(duration_ms_from_run(run))
    rows: list[dict[str, object]] = [
        {
            "user_id": user_id,
            "session_count": summary.requests,
            "total_tokens": summary.tokens,
            "total_cost_usd": money_string(summary.cost),
            "avg_latency_ms": int(sum(durations[user_id]) / len(durations[user_id])),
            "last_activity": summary.last_activity.isoformat(timespec="milliseconds"),
        }
        for user_id, summary in summaries.items()
    ]
    return sorted(rows, key=total_cost_sort_key, reverse=True)[:limit]


def users_usage_daily_rows(
    runs: Sequence[SessionRunRecord],
    usage_records: Sequence[UsageLedgerRecord],
) -> list[dict[str, object]]:
    usage_by_run = usage_records_by_run(usage_records)
    runs_by_day: dict[str, list[SessionRunRecord]] = {}
    for run in runs:
        runs_by_day.setdefault(parse_datetime(run.created_at).date().isoformat(), []).append(run)
    rows: list[dict[str, object]] = []
    for day, day_runs in runs_by_day.items():
        usage = [record for run in day_runs for record in usage_by_run.get(run.run_id, [])]
        unique_users = {run.user_id or optional_metadata_text(run, "channel") for run in day_runs}
        rows.append(
            {
                "day": day,
                "session_count": len({run.run_id for run in day_runs}),
                "total_tokens": sum(record.total_tokens for record in usage),
                "total_cost_usd": money_string(
                    sum((record.estimated_cost_usd for record in usage), Decimal("0"))
                ),
                "unique_users": len(unique_users),
            }
        )
    return sorted(rows, key=lambda row: str(row["day"]), reverse=True)


def users_usage_by_model_rows(
    usage_records: Sequence[UsageLedgerRecord],
) -> list[dict[str, object]]:
    buckets: dict[tuple[str, str], list[UsageLedgerRecord]] = {}
    for record in usage_records:
        buckets.setdefault((record.model or "unknown", record.provider), []).append(record)
    rows: list[dict[str, object]] = []
    for (model, provider), records in buckets.items():
        rows.append(
            {
                "model": model,
                "provider": provider,
                "call_count": len(records),
                "prompt_tokens": sum(record.prompt_tokens for record in records),
                "completion_tokens": sum(record.completion_tokens for record in records),
                "total_tokens": sum(record.total_tokens for record in records),
                "total_cost_usd": money_string(
                    sum((record.estimated_cost_usd for record in records), Decimal("0"))
                ),
                "last_activity": max(record.occurred_at for record in records).isoformat(),
            }
        )
    return sorted(rows, key=total_cost_sort_key, reverse=True)


def usage_records_by_run(
    usage_records: Sequence[UsageLedgerRecord],
) -> dict[str, list[UsageLedgerRecord]]:
    by_run: dict[str, list[UsageLedgerRecord]] = {}
    for record in usage_records:
        by_run.setdefault(record.run_id, []).append(record)
    return by_run


def total_cost_sort_key(row: dict[str, object]) -> Decimal:
    value = row.get("total_cost_usd", "0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float | str):
        return Decimal(str(value))
    return Decimal("0")


def error_distribution(runs: Sequence[SessionRunRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for run in runs:
        if run.status == "completed":
            continue
        error_class = optional_metadata_text(run, "error_class") or "unknown"
        counts[error_class] = counts.get(error_class, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def tool_ranking(records: Sequence[ToolInvocationRecord]) -> list[ToolUsageSummaryResponse]:
    groups: dict[str, list[ToolInvocationRecord]] = {}
    for record in records:
        groups.setdefault(record.tool_id, []).append(record)
    rows = [tool_usage_summary(tool_id, tool_records) for tool_id, tool_records in groups.items()]
    return sorted(rows, key=lambda row: row.calls, reverse=True)


def tool_invocation_status_counts(records: Sequence[ToolInvocationRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
    return dict(sorted(counts.items()))


def tool_lifecycle_attention_count(status_counts: Mapping[str, int]) -> int:
    return sum(
        status_counts.get(status_name, 0)
        for status_name in ("failed", "requires_reconciliation", "started")
    )


def tool_usage_summary(
    tool_id: str, records: Sequence[ToolInvocationRecord]
) -> ToolUsageSummaryResponse:
    durations = sorted(tool_duration_ms(record) for record in records)
    succeeded = len([record for record in records if record.status == "succeeded"])
    return ToolUsageSummaryResponse(
        toolName=tool_id,
        calls=len(records),
        successRate=round(succeeded / len(records), 6) if records else 0.0,
        avgDurationMs=int(sum(durations) / len(durations)) if durations else 0,
        p95DurationMs=percentile_value(durations, 0.95),
        mcpServerName=None,
    )


def tool_call_response(record: ToolInvocationRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "runId": record.run_id,
        "toolName": record.tool_id,
        "status": record.status,
        "success": record.status in {"succeeded", "completed"},
        "durationMs": tool_duration_ms(record),
        "approvalId": record.approval_id,
        "idempotencyKey": record.idempotency_key,
        "requestChecksum": record.request_checksum,
        "resultChecksum": record.result_checksum,
        "input": sanitized_tool_call_payload(record.input_payload),
        "output": sanitized_tool_call_payload(record.output_payload),
        "error": sanitized_tool_call_payload(record.error_payload),
        "startedAt": record.started_at.isoformat(),
        "completedAt": record.completed_at.isoformat() if record.completed_at is not None else None,
    }


def parse_tool_invocation_status_filter(raw_status: str | None) -> str | None:
    if raw_status is None or not raw_status.strip():
        return None
    try:
        return validate_tool_invocation_status(raw_status)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


def sanitized_tool_call_payload(payload: Mapping[str, Any] | None) -> dict[str, object] | None:
    if payload is None:
        return None
    sanitized = redact_trace_payload(sanitize_public_metadata_value(payload))
    if isinstance(sanitized, dict):
        return cast(dict[str, object], sanitized)
    return {}


def tool_duration_ms(record: ToolInvocationRecord) -> int:
    if record.completed_at is None:
        return 0
    return max(0, int((record.completed_at - record.started_at).total_seconds() * 1000))


def build_execution_export_csv(
    runs: Sequence[SessionRunRecord],
    invocations: Sequence[ToolInvocationRecord],
) -> str:
    tool_counts: dict[str, int] = {}
    for invocation in invocations:
        tool_counts[invocation.run_id] = tool_counts.get(invocation.run_id, 0) + 1
    lines = ["time,run_id,success,duration_ms,error_code,tool_count"]
    for run in sorted(runs, key=lambda item: parse_datetime(item.created_at), reverse=True):
        lines.append(
            ",".join(
                [
                    csv_escape(parse_datetime(run.created_at).isoformat()),
                    csv_escape(run.run_id),
                    bool_text(run.status == "completed"),
                    str(duration_ms_from_run(run)),
                    csv_escape(optional_metadata_text(run, "error_class") or ""),
                    str(tool_counts.get(run.run_id, 0)),
                ]
            )
        )
    return "\n".join(lines) + "\n"


def build_tool_export_csv(invocations: Sequence[ToolInvocationRecord]) -> str:
    lines = ["time,run_id,tool_name,success,duration_ms,error_class"]
    for invocation in sorted(invocations, key=lambda item: item.started_at, reverse=True):
        lines.append(
            ",".join(
                [
                    csv_escape(invocation.started_at.isoformat()),
                    csv_escape(invocation.run_id),
                    csv_escape(invocation.tool_id),
                    bool_text(invocation.status == "succeeded"),
                    str(tool_duration_ms(invocation)),
                    csv_escape(tool_error_class(invocation)),
                ]
            )
        )
    return "\n".join(lines) + "\n"


def tool_error_class(record: ToolInvocationRecord) -> str:
    if record.error_payload is None:
        return ""
    value = record.error_payload.get("error_class", "")
    return str(value) if value is not None else ""


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def apdex_score(durations: Sequence[int], threshold_ms: int = 1000) -> float:
    if not durations:
        return 1.0
    satisfied = len([duration for duration in durations if duration <= threshold_ms])
    tolerated = len(
        [duration for duration in durations if threshold_ms < duration <= threshold_ms * 4]
    )
    return round((satisfied + tolerated / 2) / len(durations), 6)


def usage_percent(usage: int, limit: int) -> float:
    if limit <= 0:
        return 0.0
    return round(usage / limit * 100, 6)


def parse_tenant_status_filter(raw_status: str | None) -> TenantStatus | None:
    if raw_status is None or not raw_status.strip():
        return None
    try:
        return TenantStatus(raw_status.strip().upper())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid tenant status: {raw_status}",
        ) from exc


def alert_rule_from_request(body: AlertRuleRequest, *, tenant_id: str | None = None) -> AlertRule:
    return AlertRule(
        id=body.id or "alert_rule",
        tenant_id=tenant_id if tenant_id is not None else body.tenantId,
        name=body.name,
        description=body.description,
        type=parse_alert_type(body.type),
        severity=parse_alert_severity(body.severity),
        metric=body.metric,
        threshold=body.threshold,
        window_minutes=body.windowMinutes,
        enabled=body.enabled,
        platform_only=body.platformOnly,
    )


def parse_alert_type(value: str) -> AlertType:
    try:
        return AlertType(value)
    except ValueError as error:
        raise ValueError(f"invalid alert type: {value}") from error


def parse_alert_severity(value: str) -> AlertSeverity:
    try:
        return AlertSeverity(value)
    except ValueError as error:
        raise ValueError(f"invalid alert severity: {value}") from error


def alert_rule_response(rule: AlertRule) -> AlertRuleResponse:
    return AlertRuleResponse(
        id=rule.id,
        tenantId=rule.tenant_id,
        name=rule.name,
        description=rule.description,
        type=rule.type.value,
        severity=rule.severity.value,
        metric=rule.metric,
        threshold=rule.threshold,
        windowMinutes=rule.window_minutes,
        enabled=rule.enabled,
        platformOnly=rule.platform_only,
        createdAt=epoch_millis(rule.created_at),
    )


def alert_instance_response(alert: AlertInstance) -> AlertInstanceResponse:
    return AlertInstanceResponse(
        id=alert.id,
        ruleId=alert.rule_id,
        tenantId=alert.tenant_id,
        severity=alert.severity.value,
        status=alert.status.value,
        message=alert.message,
        metricValue=alert.metric_value,
        threshold=alert.threshold,
        firedAt=epoch_millis(alert.fired_at),
        resolvedAt=optional_epoch_millis(alert.resolved_at),
        acknowledgedBy=alert.acknowledged_by,
    )


def alert_by_id(store: Any, alert_id: str, *, tenant_id: str | None = None) -> AlertInstance | None:
    raw_alerts = getattr(store, "alerts", None)
    if isinstance(raw_alerts, dict):
        alerts = cast(dict[str, object], raw_alerts)
        value = alerts.get(alert_id)
        if not isinstance(value, AlertInstance):
            return None
        if tenant_id is not None and value.tenant_id != tenant_id:
            return None
        return value
    return None


def money_string(value: object) -> str:
    return format(value, "f")


def rag_stats_response(*, tenant_id: str, rows: Sequence[RagStatsRecord]) -> RagStatsResponse:
    collections = [
        RagCollectionStatsResponse(
            collection=row.collection,
            sourceCount=row.source_count,
            documentCount=row.document_count,
            chunkCount=row.chunk_count,
            embeddedChunkCount=row.embedded_chunk_count,
            embeddingCoveragePercent=coverage_percent(row.embedded_chunk_count, row.chunk_count),
        )
        for row in rows
    ]
    total_sources = sum(row.source_count for row in rows)
    total_documents = sum(row.document_count for row in rows)
    total_chunks = sum(row.chunk_count for row in rows)
    embedded_chunks = sum(row.embedded_chunk_count for row in rows)
    return RagStatsResponse(
        tenantId=tenant_id,
        collections=collections,
        totalSources=total_sources,
        totalDocuments=total_documents,
        totalChunks=total_chunks,
        embeddedChunks=embedded_chunks,
        embeddingCoveragePercent=coverage_percent(embedded_chunks, total_chunks),
    )


async def seed_policy_rag_entry(*, sink: Any, tenant_id: str, entry: PolicyRagSeedEntry) -> int:
    now = datetime.now(UTC)
    key = entry.key.strip()
    content = entry.content.strip()
    source_uri = (
        entry.url.strip() if entry.url is not None and entry.url.strip() else f"policy-seed:{key}"
    )
    source_id = deterministic_rag_id("rag_src", f"{tenant_id}:{source_uri}")
    document_id = deterministic_rag_id("rag_doc", f"{tenant_id}:policy-seed:{key}")
    chunk_id = deterministic_rag_id("rag_chk", f"{tenant_id}:policy-seed:{key}:0")
    metadata = policy_rag_metadata(entry, source_uri=source_uri)
    saved_source_id = await maybe_await(
        sink.save_source(
            RagSourceMigrationRecord(
                id=source_id,
                tenant_id=tenant_id,
                collection="policy-seed",
                source_uri=source_uri,
                source_type="policy-seed",
                checksum=checksum(content),
                metadata=metadata,
                created_at=now,
            )
        )
    )
    await maybe_await(
        sink.save_document(
            RagDocumentMigrationRecord(
                id=document_id,
                tenant_id=tenant_id,
                source_id=str(saved_source_id or source_id),
                collection="policy-seed",
                title=entry.title.strip(),
                version=checksum(content)[:16],
                acl={"visibility": "tenant"},
                metadata=metadata,
                created_at=now,
            )
        )
    )
    await maybe_await(
        sink.save_chunk(
            RagChunkMigrationRecord(
                id=chunk_id,
                tenant_id=tenant_id,
                document_id=document_id,
                collection="policy-seed",
                chunk_index=0,
                content=content,
                content_hash=checksum(content),
                embedding=None,
                metadata=metadata,
                created_at=now,
            )
        )
    )
    return 1


def policy_rag_metadata(entry: PolicyRagSeedEntry, *, source_uri: str) -> dict[str, object]:
    key = entry.key.strip()
    metadata: dict[str, object] = {
        "source": "policy-seed",
        "source_key": f"policy-seed:{key}",
        "source_uri": source_uri,
        "key": key,
        "title": entry.title.strip(),
        "parent_document_id": f"policy-seed:{key}",
    }
    if entry.category is not None and entry.category.strip():
        metadata["category"] = entry.category.strip()
    if entry.spaceKey is not None and entry.spaceKey.strip():
        metadata["space_key"] = entry.spaceKey.strip()
    if entry.url is not None and entry.url.strip():
        metadata["url"] = entry.url.strip()
    return metadata


def cache_stats_response(stats: dict[str, object] | None) -> CacheStatsResponse:
    if stats is None:
        return CacheStatsResponse(
            enabled=False,
            semanticEnabled=False,
            totalExactHits=0,
            totalSemanticHits=0,
            totalMisses=0,
            hitRate=0.0,
            config=CacheConfigResponse(
                ttlMinutes=0,
                maxSize=0,
                similarityThreshold=0.0,
                maxCandidates=0,
                cacheableTemperature=0.0,
            ),
            cacheEnabled=False,
        )
    exact_hits = int_stat(stats, "total_exact_hits")
    semantic_hits = int_stat(stats, "total_semantic_hits")
    misses = int_stat(stats, "total_misses")
    total = exact_hits + semantic_hits + misses
    hit_rate = round((exact_hits + semantic_hits) / total, 6) if total else 0.0
    enabled = bool(stats.get("enabled", False))
    return CacheStatsResponse(
        enabled=enabled,
        semanticEnabled=bool(stats.get("semantic_enabled", False)),
        totalExactHits=exact_hits,
        totalSemanticHits=semantic_hits,
        totalMisses=misses,
        hitRate=hit_rate,
        config=CacheConfigResponse(
            ttlMinutes=int_stat(stats, "ttl_minutes"),
            maxSize=int_stat(stats, "max_size"),
            similarityThreshold=float_stat(stats, "similarity_threshold"),
            maxCandidates=int_stat(stats, "max_candidates"),
            cacheableTemperature=float_stat(stats, "cacheable_temperature"),
        ),
        cacheEnabled=enabled,
    )


def trace_summary_response(run: SessionRunRecord) -> TraceSummaryResponse:
    return TraceSummaryResponse(
        traceId=trace_id_from_run(run),
        runId=run.run_id,
        status=run.status,
        userId=run.user_id,
        threadId=run.thread_id,
        model=optional_metadata_text(run, "model"),
        durationMs=duration_ms_from_run(run),
        createdAt=epoch_millis(parse_datetime(run.created_at)),
        updatedAt=epoch_millis(parse_datetime(run.updated_at)),
    )


def trace_span_response(
    *,
    trace_id: str,
    run_id: str,
    event: RunEventRecord,
) -> TraceSpanResponse:
    return TraceSpanResponse(
        traceId=trace_id,
        runId=run_id,
        sequence=event.sequence,
        eventType=event.event_type,
        graphNode=optional_payload_text(event, "graph_node"),
        payload=public_run_event_payload(event.payload),
    )


def latency_summary_response(durations: Sequence[int]) -> LatencySummaryResponse:
    values = sorted(duration for duration in durations if duration >= 0)
    return LatencySummaryResponse(
        count=len(values),
        p50Ms=percentile_value(values, 0.50),
        p95Ms=percentile_value(values, 0.95),
        p99Ms=percentile_value(values, 0.99),
        maxMs=values[-1] if values else 0,
    )


def latency_timeseries_response(
    runs: Sequence[SessionRunRecord],
) -> list[LatencyTimeseriesPointResponse]:
    buckets: dict[str, list[int]] = {}
    for run in runs:
        bucket = parse_datetime(run.created_at).replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(bucket.isoformat(), []).append(duration_ms_from_run(run))
    return [
        LatencyTimeseriesPointResponse(
            bucket=bucket,
            averageMs=int(sum(values) / len(values)) if values else 0,
            count=len(values),
        )
        for bucket, values in sorted(buckets.items())
    ]


def percentile_value(values: Sequence[int], percentile: float) -> int:
    if not values:
        return 0
    index = max(0, min(len(values) - 1, int(round((len(values) - 1) * percentile))))
    return values[index]


def trace_id_from_run(run: SessionRunRecord) -> str:
    return optional_metadata_text(run, "trace_id") or run.run_id


def is_slack_run(run: SessionRunRecord) -> bool:
    channel = optional_metadata_text(run, "channel")
    return channel == "slack" or optional_metadata_text(run, "slackChannelId") is not None


def slack_channel_id(run: SessionRunRecord) -> str:
    return (
        optional_metadata_text(run, "slackChannelId")
        or optional_metadata_text(run, "slack_channel_id")
        or "slack"
    )


def slack_user_id(run: SessionRunRecord) -> str:
    return (
        optional_metadata_text(run, "slackUserId")
        or optional_metadata_text(run, "slack_user_id")
        or run.user_id
    )


def duration_ms_from_run(run: SessionRunRecord) -> int:
    value = run.metadata.get("durationMs", run.metadata.get("duration_ms", 0))
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value or "0")
    return 0


def optional_metadata_text(run: SessionRunRecord, key: str) -> str | None:
    value = run.metadata.get(key)
    return str(value) if value is not None else None


def optional_payload_text(event: RunEventRecord, key: str) -> str | None:
    value = event.payload.get(key)
    return str(value) if value is not None else None


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def int_stat(stats: dict[str, object], key: str) -> int:
    value = stats.get(key, 0)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value or "0")
    return 0


def float_stat(stats: dict[str, object], key: str) -> float:
    value = stats.get(key, 0.0)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return float(value or "0")
    return 0.0


def coverage_percent(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return int((numerator / denominator) * 100)


def durable_queue_diagnostics_response(
    *, tenant_id: str, rows: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    queue_counts = {
        "queued": 0,
        "leased": 0,
        "retryable_failed": 0,
        "dead_lettered": 0,
    }
    for row in rows:
        queue_status = str(row.get("queue_status", ""))
        if queue_status not in queue_counts:
            continue
        queue_count = int_diagnostic_count(row.get("queue_count"))
        dead_letter_count = int_diagnostic_count(row.get("dead_letter_count"))
        queue_counts[queue_status] += queue_count + dead_letter_count
    return {
        "status": "ready",
        "tenantId": tenant_id,
        "queueStatusCounts": queue_counts,
        "queueBacklog": (
            queue_counts["queued"] + queue_counts["leased"] + queue_counts["retryable_failed"]
        ),
        "leasedCount": queue_counts["leased"],
        "deadLetterCount": queue_counts["dead_lettered"],
        "leaseRecovery": {
            "retryableStatuses": ["queued", "retryable_failed"],
            "expiredLeaseAction": "retry_or_dead_letter",
            "deadLetterReason": "run_queue_lease_attempts_exhausted",
            "fencingTokenRequired": True,
        },
    }


def int_diagnostic_count(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        return int(value)
    return 0


async def maybe_await[T](value: T) -> T:
    if isawaitable(value):
        return cast(T, await value)
    return value


def build_audit_csv(rows: Sequence[AdminAuditLog]) -> str:
    lines = ["id,timestamp,category,action,actor,resource_type,resource_id,detail"]
    for row in rows:
        lines.append(
            ",".join(
                [
                    csv_escape(row.id),
                    csv_escape(row.created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")),
                    csv_escape(row.category),
                    csv_escape(row.action.value),
                    csv_escape(masked_admin_account_ref(row.actor)),
                    csv_escape(row.resource_type or ""),
                    csv_escape(row.resource_id or ""),
                    csv_escape(row.detail or ""),
                ]
            )
        )
    return "\n".join(lines) + "\n"


def csv_escape(value: str) -> str:
    if "," in value or '"' in value or "\n" in value:
        return f'"{value.replace('"', '""')}"'
    return value


def epoch_millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def optional_epoch_millis(value: datetime | None) -> int | None:
    return int(value.timestamp() * 1000) if value is not None else None


class Page[T]:
    def __init__(self, items: list[T], total: int, offset: int, limit: int) -> None:
        self.items = items
        self.total = total
        self.offset = offset
        self.limit = limit


def clamp_limit(raw: int) -> int:
    return max(1, min(raw, 200))


def paginate[T](items: Sequence[T], *, offset: int, limit: int) -> Page[T]:
    safe_offset = max(offset, 0)
    rows = list(items)
    total = len(rows)
    end = min(safe_offset + limit, total)
    page_items = [] if safe_offset >= total else rows[safe_offset:end]
    return Page(items=page_items, total=total, offset=safe_offset, limit=limit)

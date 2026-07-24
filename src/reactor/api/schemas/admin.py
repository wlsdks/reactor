from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class AdminCapabilitiesResponse(CamelModel):
    generatedAt: int
    source: str
    durable: bool
    paths: list[str]


class AdminAuditResponse(CamelModel):
    id: str
    category: str
    action: str
    actor: str
    resourceType: str | None = None
    resourceId: str | None = None
    detail: str | None = None
    createdAt: int


class PaginatedAdminAuditResponse(CamelModel):
    items: list[AdminAuditResponse]
    total: int
    offset: int
    limit: int


class AdminAuditRollbackPreviewChange(CamelModel):
    field: str | None = None
    from_: Any | None = Field(default=None, alias="from")
    to: Any | None = None
    description: str | None = None


class AdminAuditRollbackPreviewResponse(CamelModel):
    summary: str | None = None
    changes: list[AdminAuditRollbackPreviewChange] = Field(default_factory=lambda: [])
    warnings: list[str] = Field(default_factory=lambda: [])
    resourceLabel: str | None = None


class AdminAuditRollbackResultResponse(CamelModel):
    ok: bool
    message: str


class MemoryProposalReviewResponse(CamelModel):
    id: str
    tenantId: str
    status: str
    proposedContent: str
    subjectType: str
    subjectId: str
    memoryType: str
    visibility: str
    extractionModel: str
    extractionPromptVersion: str
    confidence: float
    decisionReason: str | None = None
    createdAt: str


class MemorySensitivityResponse(CamelModel):
    status: str
    policy: str
    markers: list[str] = Field(default_factory=lambda: [])
    source: str | None = None


class MemoryMaintenanceResponse(CamelModel):
    manager: str
    storeManager: str | None = None
    operation: str
    maxSteps: int
    deletePolicy: str
    dependencyReviewCommand: str | None = None
    dependencyRemediationCommand: str | None = None
    sensitivity: MemorySensitivityResponse | None = None


class MemoryNextAction(CamelModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    command: str = Field(min_length=1)
    preflightFile: str | None = Field(default=None, min_length=1)
    preflightEnvTemplate: str | None = Field(default=None, min_length=1)
    replatformReadinessFile: str | None = Field(default=None, min_length=1)
    smokePlanFile: str | None = Field(default=None, min_length=1)
    releaseEvidenceFile: str | None = Field(default=None, min_length=1)
    releaseReadinessFile: str | None = Field(default=None, min_length=1)
    readinessReportArg: str | None = Field(default=None, min_length=1)
    requiredReadinessReports: list[str] | None = None
    readinessReports: dict[str, str] | None = None


class MemoryProposalReviewQueueItemResponse(MemoryProposalReviewResponse):
    maintenance: MemoryMaintenanceResponse | None = None
    nextAction: str | None = None
    nextActions: list[MemoryNextAction] = Field(default_factory=lambda: [])


class MemoryProposalReviewQueueResponse(CamelModel):
    items: list[MemoryProposalReviewQueueItemResponse]
    count: int
    status: str
    subjectIdFilter: str | None = None


class MemoryProposalDecisionRequest(CamelModel):
    reason: str = Field(min_length=1, max_length=1000)
    supersedesMemoryId: str | None = Field(default=None, min_length=1, max_length=128)


class MemoryReviewItemResponse(CamelModel):
    id: str
    tenantId: str
    status: str
    content: str
    sourceId: str | None = None
    subjectType: str
    subjectId: str
    memoryType: str
    visibility: str
    confidence: float


class MemoryProposalApprovalResponse(CamelModel):
    proposal: MemoryProposalReviewResponse
    item: MemoryReviewItemResponse
    supersededItems: list[MemoryReviewItemResponse] = Field(default_factory=lambda: [])
    maintenance: MemoryMaintenanceResponse | None = None
    nextAction: str | None = None
    nextActions: list[MemoryNextAction] = Field(default_factory=lambda: [])


class AdminUserResponse(CamelModel):
    id: str
    email: str
    name: str
    role: str
    adminScope: str | None = None
    createdAt: str


class UpdateUserRoleRequest(CamelModel):
    role: str = Field(min_length=1)


class RetentionPolicyResponse(CamelModel):
    sessionRetentionDays: int
    conversationRetentionDays: int
    auditRetentionDays: int
    metricRetentionDays: int
    checkpointRetentionDays: int


class UpdateRetentionRequest(CamelModel):
    sessionRetentionDays: int | None = Field(default=None, ge=1)
    conversationRetentionDays: int | None = Field(default=None, ge=1)
    auditRetentionDays: int | None = Field(default=None, ge=1)
    metricRetentionDays: int | None = Field(default=None, ge=1)
    checkpointRetentionDays: int | None = Field(default=None, ge=1)


class DoctorCheckResponse(CamelModel):
    name: str
    status: str
    detail: str


class DoctorSectionResponse(CamelModel):
    name: str
    status: str
    checks: list[DoctorCheckResponse]
    message: str


class DoctorReportResponse(CamelModel):
    generatedAt: str
    status: str
    allHealthy: bool
    summary: str
    sections: list[DoctorSectionResponse]


class McpHealthMetricRequest(CamelModel):
    tenantId: str
    serverName: str
    status: str = "CONNECTED"
    responseTimeMs: int = 0
    errorClass: str | None = None
    errorMessage: str | None = Field(default=None, max_length=2000)
    toolCount: int = 0


class ToolCallMetricRequest(CamelModel):
    tenantId: str
    runId: str
    toolName: str
    toolSource: str | None = "mcp"
    mcpServerName: str | None = None
    callIndex: int | None = 0
    success: bool = True
    durationMs: int = 0
    errorClass: str | None = None
    errorMessage: str | None = Field(default=None, max_length=2000)


class EvalMetricResultRequest(CamelModel):
    tenantId: str
    evalRunId: str
    testCaseId: str
    pass_: bool = Field(alias="pass")
    score: float = 0.0
    latencyMs: int = 0
    tokenUsage: int = 0
    cost: Decimal | None = None
    assertionType: str | None = None
    failureClass: str | None = None
    failureDetail: str | None = None
    tags: list[str] | None = None


class EvalTestCaseMetricResult(CamelModel):
    testCaseId: str
    pass_: bool = Field(alias="pass")
    score: float = 0.0
    latencyMs: int = 0
    tokenUsage: int = 0
    cost: Decimal | None = None
    assertionType: str | None = None
    failureClass: str | None = None
    failureDetail: str | None = None
    tags: list[str] | None = None


class EvalRunMetricResultsRequest(CamelModel):
    tenantId: str
    evalRunId: str
    results: list[EvalTestCaseMetricResult]


class McpStatusSummary(CamelModel):
    total: int
    statusCounts: dict[str, int]


class SchedulerOpsSummary(CamelModel):
    totalJobs: int
    enabledJobs: int
    runningJobs: int
    failedJobs: int
    attentionBacklog: int
    agentJobs: int


class RecentSchedulerExecutionSummary(CamelModel):
    id: str
    jobId: str
    jobName: str
    jobType: str | None = None
    status: str
    resultPreview: str | None = None
    failureReason: str | None = None
    dryRun: bool
    durationMs: int
    startedAt: int
    completedAt: int | None = None


class ApprovalOpsSummary(CamelModel):
    pendingCount: int


class ResponseTrustSummary(CamelModel):
    unverifiedResponses: int = 0
    outputGuardRejected: int = 0
    outputGuardModified: int = 0
    boundaryFailures: int = 0


def empty_int_dict() -> dict[str, int]:
    return {}


def empty_object_list() -> list[dict[str, object]]:
    return []


def empty_object_dict() -> dict[str, object]:
    return {}


def empty_time_series() -> list[TimeSeriesPointResponse]:
    return []


class EmployeeValueSummary(CamelModel):
    observedResponses: int = 0
    groundedResponses: int = 0
    groundedRatePercent: int = 0
    blockedResponses: int = 0
    interactiveResponses: int = 0
    scheduledResponses: int = 0
    answerModes: dict[str, int] = Field(default_factory=empty_int_dict)
    channels: list[dict[str, object]] = Field(default_factory=empty_object_list)
    lanes: list[dict[str, object]] = Field(default_factory=empty_object_list)
    toolFamilies: list[dict[str, object]] = Field(default_factory=empty_object_list)
    topMissingQueries: list[dict[str, object]] = Field(default_factory=empty_object_list)


class RecentTrustEventSummary(CamelModel):
    occurredAt: int
    type: str
    severity: str
    action: str | None = None
    stage: str | None = None
    reason: str | None = None
    violation: str | None = None
    policy: str | None = None
    channel: str | None = None
    queryCluster: str | None = None
    queryLabel: str | None = None


class OpsMetricSnapshot(CamelModel):
    name: str
    meterCount: int
    measurements: dict[str, float]
    series: list[dict[str, object]] = Field(default_factory=empty_object_list)


class DurableQueueSummaryResponse(CamelModel):
    status: str
    tenantId: str
    queueStatusCounts: dict[str, int] = Field(default_factory=empty_int_dict)
    queueBacklog: int = 0
    leasedCount: int = 0
    deadLetterCount: int = 0
    leaseRecovery: dict[str, object] = Field(default_factory=empty_object_dict)


class ReleaseGateSummaryResponse(CamelModel):
    id: str
    status: str
    label: str | None = None


class ReleaseTagRecommendationResponse(CamelModel):
    status: str | None = None
    eligible: bool | None = None
    latestTag: str | None = None
    recommendedTag: str | None = None
    recommendedTagPattern: str | None = None
    recommendedVersionBump: str | None = None
    minorEligible: bool | None = None
    minorBoundaryReports: list[str] | None = None
    passedReports: list[str] | None = None
    warningReports: list[str] | None = None
    warningReviewRequired: bool | None = None
    missingEnv: list[str] | None = None
    missingEnvAnyOf: list[str] | None = None
    preflightEnvFileCommand: str | None = None
    releaseSmokeEnvFileCommand: str | None = None
    nextAction: str | None = None
    releaseReadinessCommand: str | None = None
    reason: str | None = None


class ProductCapabilityBoundarySummaryResponse(CamelModel):
    capability: str | None = None
    minorEligible: bool | None = None
    evidence: list[str] | None = None
    missingEvidence: list[str] | None = None
    sourceReport: str | None = None
    status: str | None = None


class LangSmithSyncSummaryResponse(CamelModel):
    datasetName: str | None = None
    exampleCount: int | None = None
    caseCount: int | None = None
    exampleIds: list[str] | None = None
    caseIds: list[str] | None = None
    metadataCaseIds: list[str] | None = None
    splitCounts: dict[str, int] | None = None
    secretFree: bool | None = None
    sdkContract: str | None = None
    sdkContractFields: dict[str, object] | None = None
    exampleContract: dict[str, object] | None = None


class ProviderUsageMetadataResponse(CamelModel):
    source: str | None = None
    present: bool | None = None
    inputTokens: int | None = None
    outputTokens: int | None = None
    totalTokens: int | None = None
    totalMatchesBreakdown: bool | None = None


class BackendProviderIntegrationSummaryResponse(CamelModel):
    status: str | None = None
    provider: str | None = None
    model: str | None = None
    requiredChecks: list[str] | None = None
    usageMetadata: ProviderUsageMetadataResponse | None = None


class SlackGatewaySmokeSummaryResponse(CamelModel):
    status: str | None = None
    gateway: str | None = None
    ingress: str | None = None
    currentThreadReplyRoute: str | None = None
    signatureVerificationRequired: bool | None = None
    responseUrlRouteSupported: bool | None = None
    mcpWriteOverlapForbidden: bool | None = None
    requiredChecks: list[str] | None = None


class RagDiagnosticsSurfaceSummaryResponse(CamelModel):
    status: str | None = None
    apiPaths: list[str] | None = None
    releaseReviewFields: list[str] | None = None


class RagVerificationSensorsSummaryResponse(CamelModel):
    covers: list[str] | None = None
    focusedTests: list[str] | None = None
    releaseReadinessContracts: list[str] | None = None


class ResearchAnswerContractSummaryResponse(CamelModel):
    profile: str | None = None
    citationStyle: str | None = None
    requiresCitationIds: bool | None = None
    requiresSourceLabels: bool | None = None
    fallbackResponseIncludesSources: bool | None = None
    uncitedClaimsAllowed: bool | None = None
    tracksMissingChunks: bool | None = None
    tracksContentHashMismatches: bool | None = None


class RagIngestionLifecycleSummaryResponse(CamelModel):
    status: str | None = None
    framework: str | None = None
    vectorStore: str | None = None
    embeddingBoundary: str | None = None
    sourceAllowlistRequired: bool | None = None
    mimeAllowlistRequired: bool | None = None
    sizeLimitRequired: bool | None = None
    aclMetadataRequired: bool | None = None
    aclBeforeRanking: bool | None = None
    rawAclRedactedFromModelContext: bool | None = None
    humanReviewRequiredForCapturedCandidates: bool | None = None
    quarantineBeforeIndex: bool | None = None
    backgroundRetries: bool | None = None
    checksumIdempotency: bool | None = None
    reindexAuditRequired: bool | None = None
    poisoningEvalCaseIds: list[str] | None = None
    diagnosticsSurface: RagDiagnosticsSurfaceSummaryResponse | None = None
    verificationSensors: RagVerificationSensorsSummaryResponse | None = None
    researchAnswerContract: ResearchAnswerContractSummaryResponse | None = None


class FeedbackReviewQueueSummaryResponse(CamelModel):
    status: str | None = None
    reviewStatus: str | None = None
    reviewNote: str | None = None
    candidateTag: str | None = None
    caseIds: list[str] | None = None
    reviewTags: list[str] | None = None
    feedbackRatingCounts: dict[str, int] | None = None
    feedbackSourceCounts: dict[str, int] | None = None
    workflowTagCounts: dict[str, int] | None = None
    expectedCitationCounts: dict[str, int] | None = None


class A2AAgentCardSummaryResponse(CamelModel):
    name: str | None = None
    interfaceCount: int | None = None
    interfaceProtocolBindings: list[str] | None = None
    interfaceProtocolVersions: list[str] | None = None
    wellKnownPath: str | None = None


class A2ADiagnosticsSummaryResponse(CamelModel):
    sdkAvailable: bool | None = None
    protocolVersion: str | None = None
    path: str | None = None


class A2AProtocolNegotiationSummaryResponse(CamelModel):
    requestHeader: str | None = None
    requestedVersion: str | None = None
    responseVersion: str | None = None
    majorMinorOnly: bool | None = None
    agentCardVersionsChecked: bool | None = None
    serverGeneratedTaskIds: bool | None = None
    sdkFastApiSurface: bool | None = None
    telemetryInstrumentation: str | None = None


class A2ATaskApiSummaryResponse(CamelModel):
    status: str | None = None
    taskStatus: str | None = None
    path: str | None = None


class A2AOperationalEvidenceSummaryResponse(CamelModel):
    auditRecorded: bool | None = None
    idempotencyEnforced: bool | None = None
    telemetryEnabled: bool | None = None
    pushOutboxRouted: bool | None = None


class A2AProtocolSummaryResponse(CamelModel):
    status: str | None = None
    agentCard: A2AAgentCardSummaryResponse | None = None
    diagnostics: A2ADiagnosticsSummaryResponse | None = None
    protocolNegotiation: A2AProtocolNegotiationSummaryResponse | None = None
    taskApi: A2ATaskApiSummaryResponse | None = None
    operationalEvidence: A2AOperationalEvidenceSummaryResponse | None = None
    secretFree: bool | None = None
    tlsRequired: bool | None = None


class DependencyWarningFindingSummaryResponse(CamelModel):
    package: str | None = None
    module: str | None = None
    deprecatedImport: str | None = None
    replacement: str | None = None
    severity: str | None = None


class DependencyWarningResolverCheckSummaryResponse(CamelModel):
    status: str | None = None
    command: str | None = None
    latestKnownFrom: str | None = None


class DependencyWarningsSummaryResponse(CamelModel):
    status: str | None = None
    source: str | None = None
    warningReports: list[str] | None = None
    warningReviewRequired: bool | None = None
    checkedPackages: list[str] | None = None
    installedVersions: dict[str, str] | None = None
    directPins: dict[str, str] | None = None
    pinSource: str | None = None
    findings: list[DependencyWarningFindingSummaryResponse] | None = None
    findingCount: int | None = None
    reviewCommand: str | None = None
    remediationCommand: str | None = None
    resolverCheck: DependencyWarningResolverCheckSummaryResponse | None = None


class ReleaseReadinessProvenanceSummaryResponse(CamelModel):
    status: str
    commitSha: str | None = None
    expectedCommitSha: str | None = None
    generatedAt: str | None = None
    inputHash: str | None = None
    verifiedCurrentHead: bool = False
    reason: str | None = None


class ReleaseReadinessSummaryResponse(CamelModel):
    status: str
    recommendedTag: str | None = None
    recommendedVersionBump: str | None = None
    minorEligible: bool | None = None
    blockingReports: list[str] = Field(default_factory=lambda: [])
    warningReports: list[str] = Field(default_factory=lambda: [])
    requiredReports: list[str] | None = None
    missingReports: list[str] | None = None
    requiredEnvAnyOf: list[list[str]] | None = None
    missingEnvAnyOf: list[str] | None = None
    recommendedEnv: list[str] | None = None
    tagRecommendation: ReleaseTagRecommendationResponse | None = None
    productCapabilityBoundary: ProductCapabilityBoundarySummaryResponse | None = None
    gates: list[ReleaseGateSummaryResponse] = Field(default_factory=lambda: [])
    langsmithSync: LangSmithSyncSummaryResponse | None = None
    ragIngestionLifecycle: RagIngestionLifecycleSummaryResponse | None = None
    feedbackReviewQueue: FeedbackReviewQueueSummaryResponse | None = None
    backendProviderIntegration: BackendProviderIntegrationSummaryResponse | None = None
    slackGatewaySmoke: SlackGatewaySmokeSummaryResponse | None = None
    a2aProtocol: A2AProtocolSummaryResponse | None = None
    dependencyWarnings: DependencyWarningsSummaryResponse | None = None
    provenance: ReleaseReadinessProvenanceSummaryResponse | None = None
    syncedAt: int | str | None = None


class OpsDashboardResponse(CamelModel):
    generatedAt: int
    ragEnabled: bool
    mcp: McpStatusSummary
    scheduler: SchedulerOpsSummary
    recentSchedulerExecutions: list[RecentSchedulerExecutionSummary]
    approvals: ApprovalOpsSummary
    durableQueue: DurableQueueSummaryResponse
    toolLifecycleStatusCounts: dict[str, int] = Field(default_factory=empty_int_dict)
    toolLifecycleAttentionCount: int = 0
    responseTrust: ResponseTrustSummary
    employeeValue: EmployeeValueSummary
    recentTrustEvents: list[RecentTrustEventSummary]
    metrics: list[OpsMetricSnapshot]
    releaseReadiness: ReleaseReadinessSummaryResponse | None = None


class RagCollectionStatsResponse(CamelModel):
    collection: str
    sourceCount: int
    documentCount: int
    chunkCount: int
    embeddedChunkCount: int
    embeddingCoveragePercent: int


class RagStatsResponse(CamelModel):
    tenantId: str
    collections: list[RagCollectionStatsResponse]
    totalSources: int
    totalDocuments: int
    totalChunks: int
    embeddedChunks: int
    embeddingCoveragePercent: int


class PolicyRagSeedEntry(CamelModel):
    key: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=100_000)
    category: str | None = Field(default=None, max_length=64)
    spaceKey: str | None = Field(default=None, max_length=64)
    url: str | None = Field(default=None, max_length=500)


class PolicyRagSeedRequest(CamelModel):
    entries: list[PolicyRagSeedEntry] = Field(min_length=1, max_length=50)


class PolicyRagSeedResponse(CamelModel):
    documentCount: int
    chunkCount: int
    keys: list[str]
    durationMs: int


class CacheConfigResponse(CamelModel):
    ttlMinutes: int
    maxSize: int
    similarityThreshold: float
    maxCandidates: int
    cacheableTemperature: float


class CacheStatsResponse(CamelModel):
    enabled: bool
    semanticEnabled: bool
    totalExactHits: int
    totalSemanticHits: int
    totalMisses: int
    hitRate: float
    config: CacheConfigResponse
    cacheEnabled: bool


class CacheInvalidationResponse(CamelModel):
    invalidated: bool
    cacheEnabled: bool
    message: str


class PlatformHealthResponse(CamelModel):
    pipelineBufferUsage: float
    pipelineDropRate: float
    pipelineWriteLatencyMs: float
    pipelineMetricsAvailable: bool = False
    responseCacheEnabled: bool = False
    activeAlerts: int
    cacheExactHits: int
    cacheSemanticHits: int
    cacheMisses: int


class VectorStoreStatsResponse(CamelModel):
    available: bool
    documentCount: int


class CacheKeyInvalidationRequest(CamelModel):
    key: str


class CacheKeyInvalidationResponse(CamelModel):
    invalidated: bool
    cacheEnabled: bool


class CachePatternInvalidationRequest(CamelModel):
    pattern: str


class CachePatternInvalidationResponse(CamelModel):
    invalidatedCount: int
    cacheEnabled: bool


class TenantQuotaResponse(CamelModel):
    maxRequestsPerMonth: int
    maxTokensPerMonth: int
    maxUsers: int
    maxAgents: int
    maxMcpServers: int


class TenantResponse(CamelModel):
    id: str
    name: str
    slug: str
    plan: str
    status: str
    quota: TenantQuotaResponse
    billingCycleStart: int
    billingEmail: str | None = None
    sloAvailability: float
    sloLatencyP99Ms: int
    metadata: dict[str, object]
    createdAt: int
    updatedAt: int


class TenantCreateRequest(CamelModel):
    name: str
    slug: str
    plan: str = "FREE"
    billingEmail: str | None = None


class TenantUsageResponse(CamelModel):
    requests: int
    tokens: int
    costUsd: str


class TenantQuotaUsageResponse(CamelModel):
    tenantId: str
    quota: TenantQuotaResponse
    usage: TenantUsageResponse
    requestUsagePercent: float
    tokenUsagePercent: float


class TenantAnalyticsSummaryResponse(CamelModel):
    tenantId: str
    tenantName: str
    plan: str
    requests: int
    cost: str
    quotaUsagePercent: float


class TenantSloResponse(CamelModel):
    tenantId: str
    sloAvailability: float
    sloLatencyP99Ms: int
    currentAvailability: float
    latencyP99Ms: int
    errorBudgetRemaining: float


class TimeSeriesPointResponse(CamelModel):
    time: str
    value: float


class UserUsageSummaryResponse(CamelModel):
    userLabel: str
    requests: int
    tokens: int
    costUsd: float
    lastActivity: int | None = None


class TenantOverviewDashboardResponse(CamelModel):
    totalRequests: int
    successRate: float
    avgResponseTimeMs: int
    apdexScore: float
    sloAvailability: float
    errorBudgetRemaining: float
    monthlyCost: str
    activeAlerts: int = 0


class TenantUsageDashboardResponse(CamelModel):
    timeSeries: list[TimeSeriesPointResponse]
    channelDistribution: dict[str, int]
    topUsers: list[UserUsageSummaryResponse]
    avgTurnsPerSession: float = 0.0
    sessionAbandonRate: float = 0.0
    sessionResolveRate: float = 0.0


class TenantQualityDashboardResponse(CamelModel):
    successRateTrend: list[TimeSeriesPointResponse] = Field(default_factory=empty_time_series)
    apdexTrend: list[TimeSeriesPointResponse] = Field(default_factory=empty_time_series)
    latencyP50: int
    latencyP95: int
    latencyP99: int
    errorDistribution: dict[str, int]


class ToolUsageSummaryResponse(CamelModel):
    toolName: str
    calls: int
    successRate: float
    avgDurationMs: int
    p95DurationMs: int
    mcpServerName: str | None = None


class TenantToolDashboardResponse(CamelModel):
    toolRanking: list[ToolUsageSummaryResponse]
    slowestTools: list[ToolUsageSummaryResponse]
    statusCounts: dict[str, int] = Field(default_factory=empty_int_dict)


class TenantCostDashboardResponse(CamelModel):
    monthlyCost: str
    dailyCostTrend: list[TimeSeriesPointResponse] = Field(default_factory=empty_time_series)
    costByModel: dict[str, str]
    costPerResolution: str = "0"
    cachedTokenRatio: float = 0.0
    budgetUsagePercent: float = 0.0


class TraceSummaryResponse(CamelModel):
    traceId: str
    runId: str
    status: str
    userId: str
    threadId: str
    model: str | None = None
    durationMs: int
    createdAt: int
    updatedAt: int


class TraceSpanResponse(CamelModel):
    traceId: str
    runId: str
    sequence: int
    eventType: str
    graphNode: str | None = None
    payload: dict[str, object]


class LatencySummaryResponse(CamelModel):
    count: int
    p50Ms: int
    p95Ms: int
    p99Ms: int
    maxMs: int


class LatencyTimeseriesPointResponse(CamelModel):
    bucket: str
    averageMs: int
    count: int


class TokenCostRowResponse(CamelModel):
    runId: str
    provider: str
    model: str
    stepType: str
    promptTokens: int
    completionTokens: int
    totalTokens: int
    estimatedCostUsd: str
    occurredAt: int


class DailyTokenCostResponse(CamelModel):
    day: str
    model: str
    promptTokens: int
    completionTokens: int
    totalTokens: int
    totalCostUsd: str


class TopExpensiveRunResponse(CamelModel):
    runId: str
    totalTokens: int
    totalCostUsd: str
    model: str
    occurredAt: int


class ModelPricingRequest(CamelModel):
    id: str
    provider: str
    model: str
    promptPricePer1m: Decimal = Decimal("0")
    completionPricePer1m: Decimal = Decimal("0")
    cachedInputPricePer1m: Decimal = Decimal("0")
    reasoningPricePer1m: Decimal = Decimal("0")
    batchPromptPricePer1m: Decimal = Decimal("0")
    batchCompletionPricePer1m: Decimal = Decimal("0")
    effectiveFrom: datetime
    effectiveTo: datetime | None = None


class ModelPricingResponse(CamelModel):
    id: str
    provider: str
    model: str
    promptPricePer1m: str
    completionPricePer1m: str
    cachedInputPricePer1m: str
    reasoningPricePer1m: str
    batchPromptPricePer1m: str
    batchCompletionPricePer1m: str
    effectiveFrom: str
    effectiveTo: str | None = None


class AlertRuleRequest(CamelModel):
    id: str | None = None
    tenantId: str | None = None
    name: str
    description: str = ""
    type: str = "STATIC_THRESHOLD"
    severity: str = "WARNING"
    metric: str
    threshold: float = 0.0
    windowMinutes: int = 15
    enabled: bool = True
    platformOnly: bool = False


class AlertRuleResponse(CamelModel):
    id: str
    tenantId: str | None = None
    name: str
    description: str
    type: str
    severity: str
    metric: str
    threshold: float
    windowMinutes: int
    enabled: bool
    platformOnly: bool
    createdAt: int


class AlertInstanceResponse(CamelModel):
    id: str
    ruleId: str
    tenantId: str | None = None
    severity: str
    status: str
    message: str
    metricValue: float
    threshold: float
    firedAt: int
    resolvedAt: int | None = None
    acknowledgedBy: str | None = None


class AlertEvaluationResponse(CamelModel):
    status: str
    createdAlerts: int

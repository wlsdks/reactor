export interface McpStatusSummary {
  total: number
  statusCounts: Record<string, number>
}

export interface OpsMetricSeries {
  timestamp: number
  value: number
}

export interface OpsMetricSnapshot {
  name: string
  meterCount: number
  measurements: Record<string, number>
  series?: OpsMetricSeries[]
}

export interface DashboardMcpReadinessSummary {
  totalServers: number
  checkedServers: number
  readyCount: number
  attentionCount: number
  unsupportedCount: number
  disconnectedCount: number
}

export interface DashboardSchedulerSummary {
  totalJobs: number
  enabledJobs: number
  runningJobs: number
  failedJobs: number
  attentionBacklog: number
  agentJobs: number
}

export interface DashboardRecentSchedulerExecution {
  id: string
  jobId: string
  jobName: string
  jobType: string | null
  status: string
  resultPreview: string | null
  failureReason: string | null
  dryRun: boolean
  durationMs: number
  startedAt: number
  completedAt: number | null
}

export interface DashboardApprovalSummary {
  pendingCount: number
}

export interface DashboardResponseTrustSummary {
  unverifiedResponses: number
  outputGuardRejected: number
  outputGuardModified: number
  boundaryFailures: number
}

export interface DashboardEmployeeValueBucket {
  key: string
  count: number
}

export interface DashboardEmployeeValueLane {
  answerMode: string
  observedResponses: number
  groundedResponses: number
  blockedResponses: number
  groundedRatePercent: number
}

export interface DashboardMissingQuery {
  queryCluster: string
  queryLabel: string
  count: number
  lastOccurredAt: number
  blockReason?: string | null
}

export interface DashboardEmployeeValueSummary {
  observedResponses: number
  groundedResponses: number
  groundedRatePercent: number
  blockedResponses: number
  interactiveResponses: number
  scheduledResponses: number
  answerModes: Record<string, number>
  channels: DashboardEmployeeValueBucket[]
  lanes: DashboardEmployeeValueLane[]
  toolFamilies: DashboardEmployeeValueBucket[]
  topMissingQueries: DashboardMissingQuery[]
}

export interface DashboardRecentTrustEvent {
  occurredAt: number
  type: string
  severity: string
  action?: string | null
  stage?: string | null
  reason?: string | null
  violation?: string | null
  policy?: string | null
  channel?: string | null
  queryCluster?: string | null
  queryLabel?: string | null
}

export type DashboardCardType = 'issues' | 'mcp' | 'guard' | 'quality' | 'scheduler'

export interface DashboardReleaseGateSummary {
  id: 'rag' | 'feedback' | 'langsmith' | 'slack' | 'a2a' | 'provider'
  status: 'passed' | 'warning' | 'blocked' | 'missing'
  label?: string
}

export interface DashboardReleaseTagRecommendation {
  status?: 'passed' | 'blocked' | 'eligible_with_warnings' | 'defer' | 'missing' | string | null
  eligible?: boolean | null
  latestTag?: string | null
  recommendedTag?: string | null
  recommendedTagPattern?: string | null
  recommendedVersionBump?: string | null
  minorEligible?: boolean | null
  minorBoundaryReports?: string[] | null
  passedReports?: string[] | null
  warningReports?: string[] | null
  warningReviewRequired?: boolean | null
  missingEnv?: string[] | null
  missingEnvAnyOf?: string[] | null
  preflightEnvFileCommand?: string | null
  releaseSmokeEnvFileCommand?: string | null
  nextAction?: string | null
  releaseReadinessCommand?: string | null
  reason?: string | null
}

export interface DashboardReleaseAggregateSummary {
  blocked?: number | null
  failed?: number | null
  passed?: number | null
  skipped?: number | null
  total?: number | null
}

export interface DashboardReleaseNextAction {
  id?: string | null
  label?: string | null
  command?: string | null
  missingEnv?: string[] | null
  preflightEnvFileCommand?: string | null
  releaseSmokeEnvFileCommand?: string | null
  remediationCommand?: string | null
}

export interface DashboardReleaseReadinessItem {
  name?: string | null
  status?: string | null
  ok?: boolean | null
  artifact?: string | null
  mode?: string | null
  scope?: string | null
  failure?: string | null
  owner?: string | null
  preflightMissingEnv?: string[] | null
  nextActions?: DashboardReleaseNextAction[] | null
}

export interface DashboardReleaseReadinessSummary {
  status: 'passed' | 'blocked' | 'eligible_with_warnings' | 'missing'
  summary?: DashboardReleaseAggregateSummary | null
  failureSummary?: string | null
  readyNextActionIds?: string[] | null
  nextActionStates?: Record<string, string> | null
  items?: DashboardReleaseReadinessItem[] | null
  recommendedTag?: string | null
  recommendedVersionBump?: string | null
  minorEligible?: boolean | null
  blockingReports?: string[]
  warningReports?: string[]
  warnings?: Array<{
    name?: string | null
    status?: string | null
    source?: string | null
    remediation?: string | null
    remediationCommand?: string | null
    reviewCommand?: string | null
    findings?: Array<{
      package?: string | null
      module?: string | null
      deprecatedImport?: string | null
      replacement?: string | null
      severity?: string | null
    }> | null
  }> | null
  requiredReports?: string[] | null
  missingReports?: string[] | null
  requiredEnvAnyOf?: string[][] | null
  missingEnvAnyOf?: string[] | null
  recommendedEnv?: string[] | null
  tagRecommendation?: DashboardReleaseTagRecommendation | null
  productCapabilityBoundary?: {
    capability?: string | null
    minorEligible?: boolean | null
    evidence?: string[] | null
    missingEvidence?: string[] | null
    sourceReport?: string | null
    status?: string | null
  } | null
  gates?: DashboardReleaseGateSummary[]
  langsmithSync?: {
    datasetName?: string | null
    exampleCount?: number | null
    caseCount?: number | null
    exampleIds?: string[] | null
    caseIds?: string[] | null
    metadataCaseIds?: string[] | null
    splitCounts?: Record<string, number> | null
    secretFree?: boolean | null
    sdkContract?: string | null
    sdkContractFields?: Record<string, unknown> | null
    exampleContract?: Record<string, unknown> | null
  } | null
  ragIngestionLifecycle?: {
    status?: string | null
    framework?: string | null
    vectorStore?: string | null
    embeddingBoundary?: string | null
    sourceAllowlistRequired?: boolean | null
    mimeAllowlistRequired?: boolean | null
    sizeLimitRequired?: boolean | null
    aclMetadataRequired?: boolean | null
    aclBeforeRanking?: boolean | null
    rawAclRedactedFromModelContext?: boolean | null
    humanReviewRequiredForCapturedCandidates?: boolean | null
    quarantineBeforeIndex?: boolean | null
    backgroundRetries?: boolean | null
    checksumIdempotency?: boolean | null
    reindexAuditRequired?: boolean | null
    poisoningEvalCaseIds?: string[] | null
    diagnosticsSurface?: {
      status?: string | null
      apiPaths?: string[] | null
      releaseReviewFields?: string[] | null
    } | null
    verificationSensors?: {
      covers?: string[] | null
      focusedTests?: string[] | null
      releaseReadinessContracts?: string[] | null
    } | null
    researchAnswerContract?: {
      profile?: string | null
      citationStyle?: string | null
      requiresCitationIds?: boolean | null
      requiresSourceLabels?: boolean | null
      fallbackResponseIncludesSources?: boolean | null
      uncitedClaimsAllowed?: boolean | null
      tracksMissingChunks?: boolean | null
      tracksContentHashMismatches?: boolean | null
    } | null
  } | null
  feedbackReviewQueue?: {
    status?: string | null
    reviewStatus?: string | null
    reviewNote?: string | null
    candidateTag?: string | null
    caseIds?: string[] | null
    reviewTags?: string[] | null
    feedbackRatingCounts?: Record<string, number> | null
    feedbackSourceCounts?: Record<string, number> | null
    workflowTagCounts?: Record<string, number> | null
    expectedCitationCounts?: Record<string, number> | null
    promotionProvenance?: {
      caseId?: string | null
      sourceRunId?: string | null
      runFile?: string | null
      caseFile?: string | null
      diagnosticsApi?: string | null
      remediationCommand?: string | null
      promotionCoverage?: Record<string, boolean | number | string | null> | null
      citationMarkerContract?: Record<string, boolean | number | string | string[] | null> | null
    }[] | null
  } | null
  backendProviderIntegration?: {
    status?: string | null
    provider?: string | null
    model?: string | null
    requiredChecks?: string[] | null
    usageMetadata?: {
      source?: string | null
      present?: boolean | null
      inputTokens?: number | null
      outputTokens?: number | null
      totalTokens?: number | null
      totalMatchesBreakdown?: boolean | null
    } | null
  } | null
  slackGatewaySmoke?: {
    status?: string | null
    gateway?: string | null
    workspaceId?: string | null
    workspaceName?: string | null
    channelId?: string | null
    botUserId?: string | null
    ingress?: string | null
    currentThreadReplyRoute?: string | null
    signatureVerificationRequired?: boolean | null
    responseUrlRouteSupported?: boolean | null
    mcpWriteOverlapForbidden?: boolean | null
    authTestOk?: boolean | null
    feedbackActionRoute?: string | null
    evalPromotionRoute?: string | null
    requiredChecks?: string[] | null
  } | null
  a2aProtocol?: {
    status?: string | null
    agentCard?: {
      name?: string | null
      interfaceCount?: number | null
      interfaceProtocolBindings?: string[] | null
      interfaceProtocolVersions?: string[] | null
      wellKnownPath?: string | null
    } | null
    diagnostics?: {
      sdkAvailable?: boolean | null
      protocolVersion?: string | null
      path?: string | null
    } | null
    protocolNegotiation?: {
      requestHeader?: string | null
      requestedVersion?: string | null
      responseVersion?: string | null
      majorMinorOnly?: boolean | null
      agentCardVersionsChecked?: boolean | null
      serverGeneratedTaskIds?: boolean | null
      sdkFastApiSurface?: boolean | null
      telemetryInstrumentation?: string | null
    } | null
    taskApi?: {
      status?: string | null
      taskStatus?: string | null
      path?: string | null
    } | null
    operationalEvidence?: {
      auditRecorded?: boolean | null
      idempotencyEnforced?: boolean | null
      telemetryEnabled?: boolean | null
      pushOutboxRouted?: boolean | null
    } | null
    secretFree?: boolean | null
    tlsRequired?: boolean | null
  } | null
  provenance?: {
    status?: string | null
    commitSha?: string | null
    expectedCommitSha?: string | null
    generatedAt?: string | null
    inputHash?: string | null
    verifiedCurrentHead?: boolean | null
    reason?: string | null
  } | null
  dependencyWarnings?: {
    status?: string | null
    source?: string | null
    warningReports?: string[] | null
    warningReviewRequired?: boolean | null
    checkedPackages?: string[] | null
    installedVersions?: Record<string, string> | null
    directPins?: Record<string, string> | null
    pinSource?: string | null
    findings?: Array<{
      package?: string | null
      module?: string | null
      deprecatedImport?: string | null
      replacement?: string | null
      severity?: string | null
    }> | null
    findingCount?: number | null
    reviewCommand?: string | null
    remediationCommand?: string | null
    resolverCheck?: {
      status?: string | null
      command?: string | null
      latestKnownFrom?: string | null
    } | null
  } | null
  syncedAt?: number | string | null
}

export interface DashboardResponse {
  generatedAt: number
  ragEnabled: boolean
  mcp: McpStatusSummary
  scheduler: DashboardSchedulerSummary
  recentSchedulerExecutions: DashboardRecentSchedulerExecution[]
  approvals: DashboardApprovalSummary
  responseTrust: DashboardResponseTrustSummary
  employeeValue: DashboardEmployeeValueSummary
  recentTrustEvents: DashboardRecentTrustEvent[]
  metrics: OpsMetricSnapshot[]
  releaseReadiness?: DashboardReleaseReadinessSummary | null
}

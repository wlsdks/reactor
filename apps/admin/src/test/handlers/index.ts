// Re-export all mock data for test files that import them directly
export { mockUser } from './auth'
export { mockPersonas } from './personas'
export { mockPromptTemplates } from './prompts'
export { mockApprovals } from './approvals'
export { mockSessions, mockSessionDetail, mockModels } from './sessions'
export { mockFeedback } from './feedback'
export { mockAuditLogs } from './audit'
export { mockToolPolicy, mockMcpSecurity, mockOutputGuardRules, mockOutputGuardAudits } from './governance'
export { mockMcpServers, mockMcpServerDetail, mockMcpPreflight, mockMcpAccessPolicy } from './mcp-servers'
export { mockDashboard, mockMetricNames } from './dashboard'
export { mockSchedulerJobs, mockSchedulerExecutions } from './scheduler'
export { mockPromptExperiments, mockPromptTrials, mockPromptExperimentReport } from './prompt-lab'
export { mockDocumentCandidates, mockRagIngestionPolicy } from './documents'
export {
  mockPlatformHealth, mockTenants, mockTenantAnalytics, mockModelPricing,
  mockAlertRules, mockActiveAlerts, mockTenantOverview, mockTenantUsage,
  mockTenantQuality, mockTenantCost, mockTenantQuota, mockTenantSlo, mockTenantAlerts,
} from './platform-admin'
export { mockProactiveChannels } from './integrations'
export { mockSlackBots } from './slack-bots'
export { mockCapabilities } from './capabilities'
export { mockToolAccuracy, mockToolStats } from './tool-stats'
export { mockTraces } from './traces'
export { mockSessionCosts, mockDailyCost, mockTopExpensive } from './token-cost'
export { mockInputGuardStages } from './input-guard'
export { mockLatencySummary, mockLatencyTimeSeries } from './latency'
export { mockUsageDashboard } from './usage'
export { mockRoles } from './rbac'
export { mockModelsRegistry } from './model-registry'
export { mockSlackChannels, mockSlackDaily } from './slack-activity'
export { mockRetentionPolicy } from './retention'
export { mockRagStatuses, mockRagByChannel } from './rag-analytics'
export { mockChannelConversationStats, mockFailurePatterns, mockLatencyBuckets } from './conversation-analytics'
export { mockCacheStats, mockVectorStoreStats } from './rag-cache'
export { mockDoctorReport, mockDoctorSummary } from './doctor'
export { mockDebugReplayCaptures } from './debug-replay'
export { mockAgentSpecs } from './agent-specs'

// Import handler arrays from each module
import { authHandlers } from './auth'
import { personasHandlers } from './personas'
import { promptsHandlers } from './prompts'
import { approvalsHandlers } from './approvals'
import { sessionsHandlers } from './sessions'
import { feedbackHandlers } from './feedback'
import { auditHandlers } from './audit'
import { governanceHandlers } from './governance'
import { mcpServersHandlers } from './mcp-servers'
import { dashboardHandlers } from './dashboard'
import { schedulerHandlers } from './scheduler'
import { promptLabHandlers } from './prompt-lab'
import { documentsHandlers } from './documents'
import { platformAdminHandlers } from './platform-admin'
import { integrationsHandlers } from './integrations'
import { slackBotsHandlers } from './slack-bots'
import { capabilitiesHandlers } from './capabilities'
import { toolStatsHandlers } from './tool-stats'
import { tracesHandlers } from './traces'
import { tokenCostHandlers } from './token-cost'
import { inputGuardHandlers } from './input-guard'
import { latencyHandlers } from './latency'
import { usageHandlers } from './usage'
import { rbacHandlers } from './rbac'
import { modelRegistryHandlers } from './model-registry'
import { slackActivityHandlers } from './slack-activity'
import { retentionHandlers } from './retention'
import { ragAnalyticsHandlers } from './rag-analytics'
import { conversationAnalyticsHandlers } from './conversation-analytics'
import { ragCacheHandlers } from './rag-cache'
import { slackFaqHandlers } from './slack-faq'
import { doctorHandlers } from './doctor'
import { debugReplayHandlers } from './debug-replay'
import { metricIngestionHandlers } from './metric-ingestion'
import { agentSpecsHandlers } from './agent-specs'

export const handlers = [
  ...authHandlers,
  ...personasHandlers,
  ...promptsHandlers,
  ...approvalsHandlers,
  ...sessionsHandlers,
  ...feedbackHandlers,
  ...auditHandlers,
  ...governanceHandlers,
  ...mcpServersHandlers,
  ...dashboardHandlers,
  ...schedulerHandlers,
  ...promptLabHandlers,
  ...documentsHandlers,
  ...platformAdminHandlers,
  ...integrationsHandlers,
  ...slackBotsHandlers,
  ...capabilitiesHandlers,
  ...toolStatsHandlers,
  ...tracesHandlers,
  ...tokenCostHandlers,
  ...inputGuardHandlers,
  ...latencyHandlers,
  ...usageHandlers,
  ...rbacHandlers,
  ...modelRegistryHandlers,
  ...slackActivityHandlers,
  ...retentionHandlers,
  ...ragAnalyticsHandlers,
  ...conversationAnalyticsHandlers,
  ...ragCacheHandlers,
  ...slackFaqHandlers,
  ...doctorHandlers,
  ...debugReplayHandlers,
  ...metricIngestionHandlers,
  ...agentSpecsHandlers,
]

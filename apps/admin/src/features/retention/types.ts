export interface RetentionPolicy {
  sessionRetentionDays: number
  conversationRetentionDays: number
  auditRetentionDays: number
  metricRetentionDays: number
  checkpointRetentionDays: number
}

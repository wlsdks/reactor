import { z } from 'zod/v4'

export const retentionPolicySchema = z.object({
  sessionRetentionDays: z.number().min(1).max(3650),
  conversationRetentionDays: z.number().min(1).max(3650),
  auditRetentionDays: z.number().min(1).max(3650),
  metricRetentionDays: z.number().min(1).max(3650),
  checkpointRetentionDays: z.number().min(1).max(3650),
})

export type RetentionPolicyFormValues = z.infer<typeof retentionPolicySchema>

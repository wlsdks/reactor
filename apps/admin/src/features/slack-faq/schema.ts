import { z } from 'zod/v4'
import i18n from 'i18next'

function maxMsg(max: number): string {
  return i18n.t('common.validation.maxLength', { max })
}

export const createFaqChannelSchema = z.object({
  channelId: z
    .string()
    .min(1, i18n.t('common.validation.required'))
    .max(64, maxMsg(64)),
  channelName: z.string().max(128, maxMsg(128)).optional(),
  enabled: z.boolean().optional(),
  autoReplyMode: z.enum(['OFF', 'AUTO', 'SUGGEST']).optional(),
  confidenceThreshold: z.number().min(0).max(1).optional(),
  daysBack: z.number().int().min(1).max(365).optional(),
  reIngestIntervalHours: z.number().int().min(1).max(720).optional(),
})

export const updateFaqChannelSchema = createFaqChannelSchema
  .partial()
  .omit({ channelId: true })

export const faqProbeSchema = z.object({
  query: z
    .string()
    .min(1, i18n.t('common.validation.required'))
    .max(2000, maxMsg(2000)),
  topK: z.number().int().min(1).max(20).optional(),
})

export const faqDryRunSchema = z.object({
  query: z
    .string()
    .min(1, i18n.t('common.validation.required'))
    .max(2000, maxMsg(2000)),
  userId: z.string().max(128, maxMsg(128)).optional(),
  asMention: z.boolean().optional(),
})

export type CreateFaqChannelFormValues = z.infer<typeof createFaqChannelSchema>
export type UpdateFaqChannelFormValues = z.infer<typeof updateFaqChannelSchema>
export type FaqProbeFormValues = z.infer<typeof faqProbeSchema>
export type FaqDryRunFormValues = z.infer<typeof faqDryRunSchema>

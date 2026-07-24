import { z } from 'zod/v4'
import i18n from 'i18next'

/**
 * Schemas for the policy-RAG bulk-seed flow on the Documents page.
 *
 * Constraints mirror the BE contract in
 * `reactor/modules/admin/.../PolicyRagSeedModels.kt`:
 *  - 1 ≤ entries ≤ 50
 *  - key: required, ≤ 128
 *  - title: required, ≤ 300
 *  - content: required, ≤ 100,000
 *  - category, spaceKey: optional, ≤ 64
 *  - url: optional, valid URL, ≤ 500
 *
 * Error messages are i18n keys looked up at parse time so the same schema
 * works for both the paste-JSON tab (which surfaces the first issue inline)
 * and the manual fieldarray tab (which feeds react-hook-form via zodResolver).
 */
function maxMsg(max: number): string {
  return i18n.t('common.validation.maxLength', { max })
}

export const policySeedEntrySchema = z.object({
  key: z
    .string()
    .min(1, i18n.t('common.validation.required'))
    .max(128, maxMsg(128)),
  title: z
    .string()
    .min(1, i18n.t('common.validation.required'))
    .max(300, maxMsg(300)),
  content: z
    .string()
    .min(1, i18n.t('common.validation.required'))
    .max(100_000, maxMsg(100_000)),
  category: z.string().max(64, maxMsg(64)).optional(),
  spaceKey: z.string().max(64, maxMsg(64)).optional(),
  url: z
    .string()
    .url(i18n.t('common.validation.url'))
    .max(500, maxMsg(500))
    .optional(),
})

export const bulkSeedSchema = z.object({
  entries: z
    .array(policySeedEntrySchema)
    .min(1, i18n.t('documentsPage.bulkSeed.error.minEntries'))
    .max(50, i18n.t('documentsPage.bulkSeed.error.maxEntries')),
})

export type BulkSeedFormValues = z.infer<typeof bulkSeedSchema>
export type PolicySeedEntryFormValues = z.infer<typeof policySeedEntrySchema>

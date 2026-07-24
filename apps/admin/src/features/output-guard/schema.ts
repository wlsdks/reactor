import { z } from 'zod/v4'
import i18n from 'i18next'

function maxMsg(max: number): string {
  return i18n.t('common.validation.maxLength', { max })
}

export const ruleFormSchema = z.object({
  name: z.string().min(1, i18n.t('outputGuardPage.validation.nameRequired')).max(255, maxMsg(255)),
  pattern: z.string().min(1, i18n.t('outputGuardPage.validation.patternRequired')).max(10000, maxMsg(10000)),
  action: z.enum(['MASK', 'REJECT']),
  priority: z.number().min(1).max(10000),
  enabled: z.boolean(),
})

export type RuleFormValues = z.infer<typeof ruleFormSchema>

/**
 * Convert comma-separated keywords into a regex alternation group.
 * Each keyword is regex-escaped so special characters are treated literally.
 */
export function keywordsToPattern(keywords: string): string {
  const words = keywords
    .split(',')
    .map((w) => w.trim())
    .filter(Boolean)
  if (words.length === 0) return ''
  const escaped = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  return `(?:${escaped.join('|')})`
}

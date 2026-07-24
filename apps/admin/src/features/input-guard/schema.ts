import { z } from 'zod/v4'
import i18n from 'i18next'

/**
 * R463: Input Guard custom rule form schema.
 *
 * Pattern validity (regex compile) is checked server-side and surfaced via
 * setError('root'). We only enforce structural constraints here.
 */
export const inputGuardRuleSchema = z.object({
  name: z.string().trim().min(1, i18n.t('common.validation.required')).max(120)
    .describe('inputGuard.rules.hintName'),
  pattern: z.string().trim().min(1, i18n.t('common.validation.required')).max(5000)
    .describe('inputGuard.rules.hintPattern'),
  patternType: z.enum(['regex', 'keyword']),
  action: z.enum(['block', 'warn', 'flag']),
  priority: z.number().int().min(0).max(10000)
    .describe('inputGuard.rules.hintPriority'),
  category: z.string().trim().max(32),
  description: z.string().trim().max(5000).optional().or(z.literal('')),
  enabled: z.boolean(),
})

export type InputGuardRuleFormValues = z.infer<typeof inputGuardRuleSchema>

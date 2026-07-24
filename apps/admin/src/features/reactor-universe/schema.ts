import { z } from 'zod/v4'
import i18n from 'i18next'

function maxMsg(max: number): string {
  return i18n.t('common.validation.maxLength', { max })
}

export const agentSpecSchema = z.object({
  name: z
    .string()
    .min(1, i18n.t('common.validation.required'))
    .max(255, maxMsg(255)),
  description: z.string().max(2000, maxMsg(2000)),
  toolNames: z.string().max(2000, maxMsg(2000)),
  keywords: z.string().max(2000, maxMsg(2000)),
  systemPrompt: z.string().max(50000, maxMsg(50000)),
  mode: z.enum(['REACT', 'STANDARD', 'PLAN_EXECUTE']),
  enabled: z.boolean(),
})

export type AgentSpecFormValues = z.infer<typeof agentSpecSchema>

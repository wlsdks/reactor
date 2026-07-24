import { z } from 'zod/v4'
import i18n from 'i18next'

function maxMsg(max: number): string {
  return i18n.t('common.validation.maxLength', { max })
}

export const personaFormSchema = z.object({
  name: z.string().min(1, i18n.t('common.validation.required')).max(255, maxMsg(255)),
  systemPrompt: z.string().min(1, i18n.t('common.validation.required')).max(50000, maxMsg(50000)),
  icon: z.string().max(50, maxMsg(50)),
  description: z.string().max(2000, maxMsg(2000)),
  responseGuideline: z.string().max(5000, maxMsg(5000)),
  welcomeMessage: z.string().max(1000, maxMsg(1000)),
  promptTemplateId: z.string().max(255, maxMsg(255)),
  isDefault: z.boolean(),
  isActive: z.boolean(),
})

export type PersonaFormValues = z.infer<typeof personaFormSchema>

// Keep backward compatibility alias
export const createPersonaSchema = personaFormSchema
export type CreatePersonaFormValues = PersonaFormValues

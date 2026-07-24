import { z } from 'zod/v4'
import i18n from 'i18next'

export const slackBotCreateSchema = z.object({
  name: z.string().min(1, i18n.t('common.validation.required')).max(255)
    .describe('slackBotsTab.hint.name'),
  workspace: z.string().min(1, i18n.t('common.validation.required')).max(255)
    .describe('slackBotsTab.hint.workspace'),
  botToken: z.string().min(1, i18n.t('common.validation.required')).max(255)
    .describe('slackBotsTab.hint.botToken'),
  appToken: z.string().min(1, i18n.t('common.validation.required')).max(255)
    .describe('slackBotsTab.hint.appToken'),
  signingSecret: z.string().min(1, i18n.t('common.validation.required')).max(255)
    .describe('slackBotsTab.hint.signingSecret'),
  description: z.string().max(2000).optional(),
  isActive: z.boolean().optional(),
})

export type SlackBotCreateFormValues = z.infer<typeof slackBotCreateSchema>

export const slackBotUpdateSchema = z.object({
  name: z.string().min(1, i18n.t('common.validation.required')).max(255),
  workspace: z.string().min(1, i18n.t('common.validation.required')).max(255),
  botToken: z.string().max(255).optional(),
  appToken: z.string().max(255).optional(),
  signingSecret: z.string().max(255).optional(),
  description: z.string().max(2000).optional(),
  isActive: z.boolean().optional(),
})

export type SlackBotUpdateFormValues = z.infer<typeof slackBotUpdateSchema>

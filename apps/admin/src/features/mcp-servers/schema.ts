import { z } from 'zod/v4'
import i18n from 'i18next'

function maxMsg(max: number): string {
  return i18n.t('common.validation.maxLength', { max })
}

export const mcpServerSchema = z.object({
  name: z
    .string()
    .min(1, i18n.t('common.validation.required'))
    .max(255, maxMsg(255))
    .regex(/^[a-z0-9][a-z0-9-]*$/, i18n.t('mcpServers.validation.urlSafeLowercase')),
  transportType: z.enum(['STDIO', 'STREAMABLE_HTTP']),
  configRaw: z.string().max(50000, maxMsg(50000)).refine(
    (v) => {
      try {
        const p: unknown = JSON.parse(v)
        return typeof p === 'object' && p !== null && !Array.isArray(p)
      } catch {
        return false
      }
    },
    i18n.t('mcpServers.invalidJsonObject'),
  ),
  tags: z
    .array(z.string().regex(/^[a-z0-9-]+:[a-z0-9-]+$/i, i18n.t('mcpServers.validation.tagKeyValue')))
    .max(50, i18n.t('common.validation.maxItems', { max: 50 })),
})

export type McpServerFormValues = z.infer<typeof mcpServerSchema>

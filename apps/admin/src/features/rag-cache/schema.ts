import { z } from 'zod/v4'

export const ragPolicySchema = z.object({
  enabled: z.boolean(),
  requireReview: z.boolean(),
  allowedChannels: z.array(z.string().max(255)),
  minQueryChars: z.number().int().min(0).max(10000),
  minResponseChars: z.number().int().min(0).max(10000),
  blockedPatterns: z.array(z.string().max(500)),
})

export type RagPolicyFormValues = z.infer<typeof ragPolicySchema>

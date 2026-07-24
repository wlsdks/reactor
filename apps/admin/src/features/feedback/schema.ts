import { z } from 'zod/v4'

/** R465: review workflow form schema. */
export const reviewUpdateSchema = z.object({
  status: z.enum(['inbox', 'done']).optional(),
  tags: z.array(z.string().max(32)).max(16).optional(),
  note: z.string().max(2000).optional().or(z.literal('')),
})

export type ReviewUpdateFormValues = z.infer<typeof reviewUpdateSchema>

/** 표준 review 태그 — UI 칩 선택지. 자유 입력도 가능하지만 우선순위는 이 셋. */
export const STANDARD_REVIEW_TAGS = ['actionable', 'resolved', 'false-positive', 'needs-followup'] as const

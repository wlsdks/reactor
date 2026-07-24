import { z } from 'zod/v4'
import i18n from 'i18next'

function maxMsg(max: number): string {
  return i18n.t('common.validation.maxLength', { max })
}

export const experimentSchema = z.object({
  name: z.string().min(1, i18n.t('common.validation.required')).max(255, maxMsg(255))
    .describe('promptStudio.hint.experimentName'),
  baselineVersionId: z.string().min(1, i18n.t('common.validation.selectBaseline')).max(255, maxMsg(255)),
  candidateVersionIds: z.array(z.string()).min(1, i18n.t('common.validation.selectCandidate')),
  testQueries: z.string().min(1, i18n.t('common.validation.enterTestQuery')).max(50000, maxMsg(50000))
    .describe('promptStudio.hint.testQueries'),
  model: z.string().max(255, maxMsg(255)).optional(),
  judgeModel: z.string().max(255, maxMsg(255)).optional(),
  temperature: z.number().min(0).max(2).optional(),
  repetitions: z.number().int().min(1).optional(),
  evaluationConfig: z.object({
    structuralEnabled: z.boolean().optional(),
    rulesEnabled: z.boolean().optional(),
    llmJudgeEnabled: z.boolean().optional(),
    llmJudgeBudgetTokens: z.number().int().optional(),
    customRubric: z.string().max(10000, maxMsg(10000)).optional(),
  }).optional(),
})

export type ExperimentFormValues = z.infer<typeof experimentSchema>

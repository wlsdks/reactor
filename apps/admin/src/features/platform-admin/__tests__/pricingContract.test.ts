import { describe, expect, it } from 'vitest'
import { buildModelPricingRequest } from '../usePlatformAdminData'

describe('model pricing backend contract', () => {
  it('uses required per-million fields, stable id, and effective timestamp', () => {
    const request = buildModelPricingRequest({
      provider: ' OpenAI ',
      model: ' GPT-5 Mini ',
      promptPricePer1m: '1.25',
      completionPricePer1m: '2.5',
      cachedInputPricePer1m: '0.25',
      reasoningPricePer1m: '3',
      batchPromptPricePer1m: '0.75',
      batchCompletionPricePer1m: '1.5',
    }, '2026-07-11T00:00:00Z')

    expect(request).toEqual({
      id: 'pricing:openai:gpt-5 mini',
      provider: 'OpenAI',
      model: 'GPT-5 Mini',
      promptPricePer1m: 1.25,
      completionPricePer1m: 2.5,
      cachedInputPricePer1m: 0.25,
      reasoningPricePer1m: 3,
      batchPromptPricePer1m: 0.75,
      batchCompletionPricePer1m: 1.5,
      effectiveFrom: '2026-07-11T00:00:00Z',
      effectiveTo: null,
    })
    expect(request).not.toHaveProperty('promptPricePer1k')
  })
})

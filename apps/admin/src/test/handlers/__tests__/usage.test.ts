import { describe, expect, it } from 'vitest'

describe('usage mock handlers', () => {
  it('serves the complete usage dashboard contract with ISO activity timestamps', async () => {
    const [costResponse, dailyResponse, modelResponse, shortPeriodResponse, limitedCostResponse] = await Promise.all([
      fetch('http://localhost/api/admin/users/usage/cost?days=30&limit=100'),
      fetch('http://localhost/api/admin/users/usage/daily?days=30'),
      fetch('http://localhost/api/admin/users/usage/by-model?days=30'),
      fetch('http://localhost/api/admin/users/usage/daily?days=7'),
      fetch('http://localhost/api/admin/users/usage/cost?days=7&limit=3'),
    ])

    expect(costResponse.ok).toBe(true)
    expect(dailyResponse.ok).toBe(true)
    expect(modelResponse.ok).toBe(true)

    const costs = await costResponse.json() as Array<Record<string, unknown>>
    const shortPeriod = await shortPeriodResponse.json() as Array<Record<string, unknown>>
    const limitedCosts = await limitedCostResponse.json() as Array<Record<string, unknown>>
    const models = await modelResponse.json() as Array<Record<string, unknown>>

    expect(shortPeriodResponse.ok).toBe(true)
    expect(limitedCostResponse.ok).toBe(true)
    expect(shortPeriod).toHaveLength(7)
    expect(limitedCosts).toHaveLength(3)
    expect(costs[0]?.last_activity).toEqual(expect.any(String))
    expect(costs[0]?.last_activity).toMatch(/T/)
    expect(models).toEqual(expect.arrayContaining([
      expect.objectContaining({
        model: expect.any(String),
        provider: expect.any(String),
        call_count: expect.any(Number),
        prompt_tokens: expect.any(Number),
        completion_tokens: expect.any(Number),
        total_tokens: expect.any(Number),
        total_cost_usd: expect.any(String),
        last_activity: expect.any(String),
      }),
    ]))
  })
})

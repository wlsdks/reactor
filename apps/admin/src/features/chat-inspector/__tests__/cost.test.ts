import { describe, it, expect } from 'vitest'
import {
  calculateCost,
  aggregateSessionTotals,
  isBudgetExceeded,
  shouldCollapsePayload,
  formatUsd,
  DEFAULT_BUDGET,
  PAYLOAD_COLLAPSE_THRESHOLD_BYTES,
  type ModelPrice,
} from '../cost'

const PRICE: ModelPrice = {
  inputPricePerMillionTokens: 3.0,
  outputPricePerMillionTokens: 15.0,
}

describe('calculateCost', () => {
  it('returns 0 when no tokens consumed', () => {
    expect(calculateCost({ inputTokens: 0, outputTokens: 0 }, PRICE)).toBe(0)
  })

  it('returns 0 when model pricing is null', () => {
    expect(calculateCost({ inputTokens: 1000, outputTokens: 500 }, null)).toBe(0)
  })

  it('returns 0 when model pricing is undefined', () => {
    expect(calculateCost({ inputTokens: 1000, outputTokens: 500 }, undefined)).toBe(0)
  })

  it('computes cost proportionally to 1M token unit', () => {
    // 1,000,000 input tokens @ $3 = $3.00
    expect(calculateCost({ inputTokens: 1_000_000, outputTokens: 0 }, PRICE)).toBe(3.0)
  })

  it('sums input and output portions', () => {
    // 500k in * $3 + 250k out * $15 = 1.5 + 3.75 = 5.25
    const cost = calculateCost({ inputTokens: 500_000, outputTokens: 250_000 }, PRICE)
    expect(cost).toBeCloseTo(5.25, 6)
  })

  it('handles small fractional token counts', () => {
    // 1000 in * $3/M = 0.003
    expect(calculateCost({ inputTokens: 1000, outputTokens: 0 }, PRICE)).toBeCloseTo(0.003, 6)
  })

  it('clamps negative token counts to zero', () => {
    expect(calculateCost({ inputTokens: -1000, outputTokens: -1000 }, PRICE)).toBe(0)
  })

  it('treats non-finite values as zero', () => {
    expect(calculateCost({ inputTokens: NaN, outputTokens: Infinity }, PRICE)).toBe(0)
  })
})

describe('aggregateSessionTotals', () => {
  it('returns zero totals for an empty list', () => {
    expect(aggregateSessionTotals([])).toEqual({ totalTokens: 0, estimatedCostUsd: 0 })
  })

  it('sums tokens and cost across events', () => {
    const totals = aggregateSessionTotals([
      { totalTokens: 100, estimatedCostUsd: 0.001 },
      { totalTokens: 250, estimatedCostUsd: 0.004 },
    ])
    expect(totals.totalTokens).toBe(350)
    expect(totals.estimatedCostUsd).toBeCloseTo(0.005, 6)
  })

  it('ignores NaN/Infinity values', () => {
    const totals = aggregateSessionTotals([
      { totalTokens: NaN, estimatedCostUsd: Infinity },
      { totalTokens: 10, estimatedCostUsd: 0.1 },
    ])
    expect(totals.totalTokens).toBe(10)
    expect(totals.estimatedCostUsd).toBeCloseTo(0.1, 6)
  })
})

describe('isBudgetExceeded', () => {
  it('returns false when both token and cost are under caps', () => {
    expect(
      isBudgetExceeded({ totalTokens: 1000, estimatedCostUsd: 0.01 }, DEFAULT_BUDGET),
    ).toBe(false)
  })

  it('returns true when token cap is exceeded', () => {
    expect(
      isBudgetExceeded(
        { totalTokens: DEFAULT_BUDGET.maxTokens + 1, estimatedCostUsd: 0 },
        DEFAULT_BUDGET,
      ),
    ).toBe(true)
  })

  it('returns true when USD cap is exceeded', () => {
    expect(
      isBudgetExceeded(
        { totalTokens: 0, estimatedCostUsd: DEFAULT_BUDGET.maxCostUsd + 0.01 },
        DEFAULT_BUDGET,
      ),
    ).toBe(true)
  })

  it('respects a custom budget threshold', () => {
    const tight = { maxTokens: 100, maxCostUsd: 0.001 }
    expect(isBudgetExceeded({ totalTokens: 50, estimatedCostUsd: 0.0005 }, tight)).toBe(false)
    expect(isBudgetExceeded({ totalTokens: 101, estimatedCostUsd: 0 }, tight)).toBe(true)
    expect(isBudgetExceeded({ totalTokens: 0, estimatedCostUsd: 0.002 }, tight)).toBe(true)
  })

  it('uses DEFAULT_BUDGET when no budget is provided', () => {
    expect(isBudgetExceeded({ totalTokens: 0, estimatedCostUsd: 0 })).toBe(false)
    expect(
      isBudgetExceeded({ totalTokens: DEFAULT_BUDGET.maxTokens * 2, estimatedCostUsd: 0 }),
    ).toBe(true)
  })
})

describe('shouldCollapsePayload', () => {
  it('returns false for empty payloads', () => {
    expect(shouldCollapsePayload('')).toBe(false)
    expect(shouldCollapsePayload(null)).toBe(false)
    expect(shouldCollapsePayload(undefined)).toBe(false)
  })

  it('returns false for payloads smaller than the default threshold', () => {
    const small = 'x'.repeat(100)
    expect(shouldCollapsePayload(small)).toBe(false)
  })

  it('returns true for payloads larger than the default threshold (2KB)', () => {
    const large = 'x'.repeat(PAYLOAD_COLLAPSE_THRESHOLD_BYTES + 1)
    expect(shouldCollapsePayload(large)).toBe(true)
  })

  it('returns false at exactly the threshold boundary', () => {
    const exact = 'x'.repeat(PAYLOAD_COLLAPSE_THRESHOLD_BYTES)
    expect(shouldCollapsePayload(exact)).toBe(false)
  })

  it('accepts a custom threshold', () => {
    expect(shouldCollapsePayload('abcdef', 5)).toBe(true)
    expect(shouldCollapsePayload('abc', 5)).toBe(false)
  })
})

describe('formatUsd', () => {
  it('returns $0.0000 for zero / non-finite', () => {
    expect(formatUsd(0)).toBe('$0.0000')
    expect(formatUsd(NaN)).toBe('$0.0000')
    expect(formatUsd(-1)).toBe('$0.0000')
  })

  it('formats small amounts with 4 decimal places', () => {
    expect(formatUsd(0.0032)).toBe('$0.0032')
  })

  it('formats amounts >= $1 with 2 decimal places', () => {
    expect(formatUsd(1.234)).toBe('$1.23')
    expect(formatUsd(99.5)).toBe('$99.50')
  })
})

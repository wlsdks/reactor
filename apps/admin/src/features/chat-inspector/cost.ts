/**
 * Cost and budget helpers for the Chat Inspector.
 *
 * Pricing is sourced from the ModelRegistry (`/api/admin/models`) which returns
 * dollar prices per 1,000,000 tokens for input and output. This module is a
 * pure-function utility layer so it can be exercised in unit tests without any
 * React or query infrastructure.
 */

export interface ModelPrice {
  inputPricePerMillionTokens: number
  outputPricePerMillionTokens: number
}

export interface TokenBreakdown {
  inputTokens: number
  outputTokens: number
}

export interface SessionTotals {
  totalTokens: number
  estimatedCostUsd: number
}

export interface BudgetThreshold {
  /** Soft cap on total tokens consumed in the current inspector session. */
  maxTokens: number
  /** Soft cap on estimated USD cost in the current inspector session. */
  maxCostUsd: number
}

/** Default budget: 100k tokens OR $1.00 USD — whichever is hit first. */
export const DEFAULT_BUDGET: BudgetThreshold = {
  maxTokens: 100_000,
  maxCostUsd: 1.0,
}

/** Default payload collapse threshold in bytes (roughly characters for UTF-8 JSON). */
export const PAYLOAD_COLLAPSE_THRESHOLD_BYTES = 2048

/**
 * Compute the estimated USD cost of a single request/response pair.
 *
 * Returns 0 when either tokens or pricing is zero; never throws.
 */
export function calculateCost(
  tokens: TokenBreakdown,
  price: ModelPrice | null | undefined,
): number {
  if (!price) return 0
  const inputTokens = Number.isFinite(tokens.inputTokens) ? Math.max(0, tokens.inputTokens) : 0
  const outputTokens = Number.isFinite(tokens.outputTokens) ? Math.max(0, tokens.outputTokens) : 0
  const inputCost = (inputTokens / 1_000_000) * price.inputPricePerMillionTokens
  const outputCost = (outputTokens / 1_000_000) * price.outputPricePerMillionTokens
  return inputCost + outputCost
}

/** Sum an array of per-event totals into running session totals. */
export function aggregateSessionTotals(events: SessionTotals[]): SessionTotals {
  return events.reduce(
    (acc, evt) => ({
      totalTokens: acc.totalTokens + (Number.isFinite(evt.totalTokens) ? evt.totalTokens : 0),
      estimatedCostUsd:
        acc.estimatedCostUsd +
        (Number.isFinite(evt.estimatedCostUsd) ? evt.estimatedCostUsd : 0),
    }),
    { totalTokens: 0, estimatedCostUsd: 0 },
  )
}

/** True when either the token cap or the USD cap has been breached. */
export function isBudgetExceeded(
  totals: SessionTotals,
  budget: BudgetThreshold = DEFAULT_BUDGET,
): boolean {
  if (budget.maxTokens > 0 && totals.totalTokens > budget.maxTokens) return true
  if (budget.maxCostUsd > 0 && totals.estimatedCostUsd > budget.maxCostUsd) return true
  return false
}

/** Default collapse decision for a payload. Collapsed when bytes exceed the threshold. */
export function shouldCollapsePayload(
  payload: string | null | undefined,
  threshold: number = PAYLOAD_COLLAPSE_THRESHOLD_BYTES,
): boolean {
  if (!payload) return false
  // String length is a cheap proxy; UTF-8 bytes are typically >= char count.
  return payload.length > threshold
}

import { formatCurrency } from '../../shared/lib/formatters'

/**
 * Format a USD amount with 4 decimal places when small, 2 when larger.
 *
 * Wraps `formatCurrency` so the chat-inspector keeps its zero-fallback
 * (`"$0.0000"`) while delegating the magnitude-aware precision rules to the
 * shared helper.
 */
export function formatUsd(amount: number): string {
  if (!Number.isFinite(amount) || amount <= 0) return '$0.0000'
  return formatCurrency(amount)
}

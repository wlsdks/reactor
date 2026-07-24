/**
 * Monthly cost estimate based on per-million-token pricing.
 *
 *   estimate = (inputTokens  / 1_000_000) * inputPricePerMillion
 *            + (outputTokens / 1_000_000) * outputPricePerMillion
 *
 * Token volumes are expected raw token counts (not millions). Negative or
 * non-finite inputs are coerced to 0 so the UI never shows NaN.
 */
export function estimateMonthlyCost(
  inputTokens: number,
  outputTokens: number,
  inputPricePerMillion: number,
  outputPricePerMillion: number,
): number {
  const safe = (n: number) => (Number.isFinite(n) && n >= 0 ? n : 0)
  return (
    (safe(inputTokens) / 1_000_000) * safe(inputPricePerMillion) +
    (safe(outputTokens) / 1_000_000) * safe(outputPricePerMillion)
  )
}

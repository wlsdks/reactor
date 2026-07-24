/**
 * Chart tick helpers shared across recharts wrappers.
 */

/**
 * Compute a tick interval that targets ~`targetTicks` evenly spaced ticks on
 * an x-axis of length `length`. Recharts' default `preserveEnd` behaviour picks
 * ticks non-uniformly when the first/last labels would collide — forcing a
 * numeric interval yields evenly spaced ticks (e.g. every 4 hours for a
 * 24-point series with the default targetTicks of 6).
 */
export function computeTickInterval(length: number, targetTicks = 6): number {
  if (length <= targetTicks) return 0
  return Math.max(1, Math.floor(length / targetTicks) - 1)
}

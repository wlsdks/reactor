/**
 * Budget colour buckets for the CostCard progress bar:
 *   <50%  success
 *   <80%  warning
 *   ≥80%  error
 *
 * Lives in its own file so CostCard.tsx remains a "components only" module
 * (react-refresh/only-export-components rule).
 */
export function budgetSeverity(ratio: number): 'success' | 'warning' | 'error' {
  if (ratio >= 0.8) return 'error'
  if (ratio >= 0.5) return 'warning'
  return 'success'
}

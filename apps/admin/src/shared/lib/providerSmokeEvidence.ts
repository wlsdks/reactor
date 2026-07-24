export type ProviderSmokeCheckId =
  | 'provider'
  | 'model'
  | 'usage_present'
  | 'usage_source'
  | 'usage_tokens'
  | 'usage_breakdown'
  | 'required_usage_metadata'

export interface BackendProviderIntegrationEvidence {
  status?: string | null
  provider?: string | null
  model?: string | null
  requiredChecks?: string[] | null
  usageMetadata?: {
    source?: string | null
    present?: boolean | null
    inputTokens?: number | null
    outputTokens?: number | null
    totalTokens?: number | null
    totalMatchesBreakdown?: boolean | null
  } | null
}

export function listProviderSmokeMissingCheckIds(
  evidence: BackendProviderIntegrationEvidence | null | undefined,
): ProviderSmokeCheckId[] {
  const usage = evidence?.usageMetadata ?? null
  const checks: Array<{ id: ProviderSmokeCheckId; ok: boolean }> = [
    { id: 'provider', ok: Boolean(evidence?.provider) },
    { id: 'model', ok: Boolean(evidence?.model) },
    { id: 'usage_present', ok: usage?.present === true },
    { id: 'usage_source', ok: Boolean(usage?.source) },
    {
      id: 'usage_tokens',
      ok: (usage?.inputTokens ?? 0) > 0 && (usage?.outputTokens ?? 0) > 0,
    },
    { id: 'usage_breakdown', ok: usage?.totalMatchesBreakdown === true },
    {
      id: 'required_usage_metadata',
      ok: evidence?.requiredChecks?.includes('usage_metadata') === true,
    },
  ]

  return checks.filter((check) => !check.ok).map((check) => check.id)
}

export function hasProviderSmokeEvidence(
  evidence: BackendProviderIntegrationEvidence | null | undefined,
): boolean {
  return evidence?.status === 'verified'
    && listProviderSmokeMissingCheckIds(evidence).length === 0
}

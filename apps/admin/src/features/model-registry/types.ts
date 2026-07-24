export interface ModelEntry {
  name: string
  inputPricePerMillionTokens: number
  outputPricePerMillionTokens: number
  isDefault: boolean
  /**
   * Optional provider label (e.g. "openai", "anthropic").
   * Not guaranteed by the `/api/admin/models` response; the drawer shows a
   * muted placeholder when absent.
   */
  provider?: string
  /**
   * Context window size in tokens, if the backend exposes it.
   * Backends that only know maximum completion length may omit this.
   */
  contextLength?: number
  /** Maximum output tokens, if provided. */
  maxTokens?: number
  /**
   * Capability flags (e.g. "tools", "vision", "streaming", "reasoning").
   * Rendered as chips in the detail drawer; muted empty state when absent.
   */
  capabilities?: string[]
}

export interface ProviderSmokeUsageMetadata {
  source?: string | null
  present?: boolean | null
  inputTokens?: number | null
  outputTokens?: number | null
  totalTokens?: number | null
  totalMatchesBreakdown?: boolean | null
}

export interface ProviderSmokeIntegrationEvidence {
  status?: string | null
  provider?: string | null
  model?: string | null
  requiredChecks?: string[] | null
  usageMetadata?: ProviderSmokeUsageMetadata | null
}

export interface ProviderLiveSmokeResult {
  ok: boolean
  status: string
  scope: string
  provider: string
  model: string
  error?: string | null
  evidence?: {
    backendProviderIntegration?: ProviderSmokeIntegrationEvidence | null
  } | null
  checks: Record<string, { status?: string; [key: string]: unknown }>
}

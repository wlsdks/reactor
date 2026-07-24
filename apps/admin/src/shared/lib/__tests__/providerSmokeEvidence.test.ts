import { describe, expect, it } from 'vitest'
import {
  hasProviderSmokeEvidence,
  listProviderSmokeMissingCheckIds,
  type BackendProviderIntegrationEvidence,
} from '../providerSmokeEvidence'

const completeEvidence: BackendProviderIntegrationEvidence = {
  status: 'verified',
  provider: 'ollama',
  model: 'gemma4:12b',
  requiredChecks: ['required_env', 'tracing_config', 'chat_model_invoke', 'usage_metadata'],
  usageMetadata: {
    source: 'LangChain AIMessage.usage_metadata',
    present: true,
    inputTokens: 20,
    outputTokens: 63,
    totalTokens: 83,
    totalMatchesBreakdown: true,
  },
}

describe('providerSmokeEvidence', () => {
  it('accepts verified provider evidence with usage metadata', () => {
    expect(hasProviderSmokeEvidence(completeEvidence)).toBe(true)
    expect(listProviderSmokeMissingCheckIds(completeEvidence)).toEqual([])
  })

  it('rejects verified provider evidence when usage metadata is incomplete', () => {
    const evidence = {
      ...completeEvidence,
      usageMetadata: {
        ...completeEvidence.usageMetadata!,
        present: false,
        inputTokens: null,
        outputTokens: null,
        totalMatchesBreakdown: false,
      },
    }

    expect(hasProviderSmokeEvidence(evidence)).toBe(false)
    expect(listProviderSmokeMissingCheckIds(evidence)).toEqual([
      'usage_present',
      'usage_tokens',
      'usage_breakdown',
    ])
  })

  it('requires verified status for release-grade provider smoke evidence', () => {
    expect(hasProviderSmokeEvidence({ ...completeEvidence, status: 'blocked' })).toBe(false)
  })
})

import { http, HttpResponse } from 'msw'
import type { ModelEntry } from '../../features/model-registry/types'

export const mockModelsRegistry: ModelEntry[] = [
  { name: 'gpt-4o', inputPricePerMillionTokens: 2.50, outputPricePerMillionTokens: 10.00, isDefault: true },
  { name: 'gpt-4o-mini', inputPricePerMillionTokens: 0.15, outputPricePerMillionTokens: 0.60, isDefault: false },
  { name: 'claude-sonnet-4-20250514', inputPricePerMillionTokens: 3.00, outputPricePerMillionTokens: 15.00, isDefault: false },
]

export const modelRegistryHandlers = [
  http.get('/api/admin/models', () => {
    return HttpResponse.json(mockModelsRegistry)
  }),
  http.post('/api/admin/provider/smoke', () => {
    return HttpResponse.json({
      ok: true,
      status: 'passed',
      scope: 'live',
      provider: 'ollama',
      model: 'qwen3:8b',
      evidence: {
        backendProviderIntegration: {
          status: 'verified',
          provider: 'ollama',
          model: 'qwen3:8b',
          requiredChecks: ['chat_model_invoke', 'usage_metadata'],
          usageMetadata: {
            source: 'LangChain AIMessage.usage_metadata',
            present: true,
            inputTokens: 4,
            outputTokens: 2,
            totalTokens: 6,
            totalMatchesBreakdown: true,
          },
        },
      },
      checks: {
        chat_model_invoke: { status: 'passed', content_length: 4 },
        usage_metadata: { status: 'passed' },
      },
    })
  }),
]

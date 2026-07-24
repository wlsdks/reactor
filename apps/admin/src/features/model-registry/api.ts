import { api } from '../../shared/api/client'
import type { ModelEntry, ProviderLiveSmokeResult } from './types'

interface BackendModelEntry extends Omit<ModelEntry, 'inputPricePerMillionTokens' | 'outputPricePerMillionTokens'> {
  inputPricePerMillionTokens: number | string
  outputPricePerMillionTokens: number | string
}

function finiteNumber(value: number | string): number {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

export const listModels = async (): Promise<ModelEntry[]> => {
  const models = await api.get('admin/models', { searchParams: { limit: 200 } }).json<BackendModelEntry[]>()
  return models.map((model) => ({
    ...model,
    inputPricePerMillionTokens: finiteNumber(model.inputPricePerMillionTokens),
    outputPricePerMillionTokens: finiteNumber(model.outputPricePerMillionTokens),
  }))
}

export const runProviderSmoke = (): Promise<ProviderLiveSmokeResult> =>
  api.post('admin/provider/smoke').json()

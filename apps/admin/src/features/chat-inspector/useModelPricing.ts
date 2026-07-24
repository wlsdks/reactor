import { useQuery } from '@tanstack/react-query'
import { listModels } from '../model-registry/api'
import type { ModelEntry } from '../model-registry/types'
import { queryKeys } from '../../shared/lib/queryKeys'
import type { ModelPrice } from './cost'

const STALE_TIME = 5 * 60 * 1000

/**
 * Fetches the admin model catalog (with per-1M token pricing) and exposes a
 * lookup helper. The ModelRegistry page already consumes the same endpoint,
 * so TanStack Query dedupes the request.
 */
export function useModelPricing() {
  const query = useQuery({
    queryKey: queryKeys.models.list(),
    queryFn: listModels,
    staleTime: STALE_TIME,
  })

  const models: ModelEntry[] = query.data ?? []

  function getPrice(modelName: string | null | undefined): ModelPrice | null {
    if (!modelName) return null
    const entry = models.find((m) => m.name === modelName)
    if (!entry) return null
    return {
      inputPricePerMillionTokens: entry.inputPricePerMillionTokens,
      outputPricePerMillionTokens: entry.outputPricePerMillionTokens,
    }
  }

  return {
    models,
    getPrice,
    isLoading: query.isLoading,
    isError: query.isError,
  }
}

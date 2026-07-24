import { beforeEach, describe, expect, it, vi } from 'vitest'
import { queryClient } from '../../../shared/lib/queryClient'
import { errorLogger } from '../../../shared/lib/errorLogger'
import { ApiError } from '../../../shared/api/errors'

const getCapabilityManifestMock = vi.fn()

vi.mock('../api', () => ({
  getCapabilityManifest: (...args: unknown[]) => getCapabilityManifestMock(...args),
}))

import { fetchCapabilityManifestCached } from '../useCapabilities'
import { queryKeys } from '../../../shared/lib/queryKeys'

describe('fetchCapabilityManifestCached', () => {
  beforeEach(() => {
    queryClient.clear()
    getCapabilityManifestMock.mockReset()
  })

  it('deduplicates concurrent calls into a single network fetch', async () => {
    getCapabilityManifestMock.mockResolvedValue(new Set(['/api/admin/capabilities']))

    const [a, b, c] = await Promise.all([
      fetchCapabilityManifestCached(),
      fetchCapabilityManifestCached(),
      fetchCapabilityManifestCached(),
    ])

    expect(getCapabilityManifestMock).toHaveBeenCalledTimes(1)
    expect(a).toBe(b)
    expect(b).toBe(c)
    expect(a?.has('/api/admin/capabilities')).toBe(true)
  })

  it('reuses the cached value for follow-up calls within staleTime', async () => {
    getCapabilityManifestMock.mockResolvedValue(new Set(['/api/ops/dashboard']))

    const first = await fetchCapabilityManifestCached()
    const second = await fetchCapabilityManifestCached()

    expect(getCapabilityManifestMock).toHaveBeenCalledTimes(1)
    expect(first).toBe(second)
  })

  it('writes the result under the canonical ["capabilities"] queryKey', async () => {
    const manifest = new Set(['/api/tool-policy'])
    getCapabilityManifestMock.mockResolvedValue(manifest)

    await fetchCapabilityManifestCached()

    const cached = queryClient.getQueryData(queryKeys.capabilities())
    expect(cached).toBe(manifest)
  })

  it('can skip the global error logger for callers that render their own failure state', async () => {
    const captureSpy = vi.spyOn(errorLogger, 'capture').mockImplementation(() => {})
    getCapabilityManifestMock.mockRejectedValue(ApiError.fromResponse(403, null))

    await expect(fetchCapabilityManifestCached({ skipGlobalError: true })).rejects.toBeInstanceOf(ApiError)

    expect(captureSpy).not.toHaveBeenCalled()
  })
})

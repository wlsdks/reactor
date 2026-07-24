import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../../shared/api/client'
import { listModels, runProviderSmoke } from '../api'

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: vi.fn().mockReturnValue({ json: vi.fn() }),
    post: vi.fn().mockReturnValue({ json: vi.fn() }),
  },
}))

const mockedApi = vi.mocked(api)

afterEach(() => {
  vi.clearAllMocks()
})

describe('model registry api', () => {
  it('normalizes decimal string prices from the FastAPI boundary', async () => {
    mockedApi.get = vi.fn().mockReturnValue({
      json: vi.fn().mockResolvedValue([{
        name: 'gemma4:12b',
        provider: 'ollama',
        inputPricePerMillionTokens: '0',
        outputPricePerMillionTokens: '1.25',
        isDefault: true,
      }]),
    })

    await expect(listModels()).resolves.toEqual([{
      name: 'gemma4:12b',
      provider: 'ollama',
      inputPricePerMillionTokens: 0,
      outputPricePerMillionTokens: 1.25,
      isDefault: true,
    }])
  })

  it('runs the configured provider smoke endpoint without client-supplied prompt or secrets', async () => {
    const result = {
      ok: true,
      status: 'passed',
      scope: 'live',
      provider: 'ollama',
      model: 'qwen3:8b',
      checks: {},
    }
    mockedApi.post = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(result) })

    await expect(runProviderSmoke()).resolves.toEqual(result)
    expect(mockedApi.post).toHaveBeenCalledWith('admin/provider/smoke')
  })
})

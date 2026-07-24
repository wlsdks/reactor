import { describe, expect, it } from 'vitest'
import { ROUTE_REQUIREMENTS } from '../requirements'

describe('safety policy route requirements', () => {
  it('keeps the usage route gate aligned with the three report data sources', () => {
    expect(ROUTE_REQUIREMENTS['/usage']).toEqual([
      { openApiPath: '/api/admin/users/usage/cost' },
      { openApiPath: '/api/admin/users/usage/daily' },
      { openApiPath: '/api/admin/users/usage/by-model' },
    ])
  })

  it('keeps tab-specific input guard endpoints out of the workspace gate', () => {
    expect(ROUTE_REQUIREMENTS['/safety-rules']).toEqual([
      { openApiPath: '/api/output-guard/rules' },
      { openApiPath: '/api/tool-policy' },
    ])
    expect(ROUTE_REQUIREMENTS).not.toHaveProperty('/input-guard')
  })
})

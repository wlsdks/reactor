import type { DashboardResponse } from './types'
import { api } from '../../shared/api/client'

export const getDashboard = (names?: string[]): Promise<DashboardResponse> => {
  if (names && names.length > 0) {
    const searchParams = new URLSearchParams()
    names.forEach((name) => searchParams.append('names', name))
    return api.get('ops/dashboard', { searchParams }).json()
  }
  return api.get('ops/dashboard').json()
}

export const listMetricNames = (): Promise<string[]> =>
  api.get('ops/metrics/names', { searchParams: { limit: 200 } }).json()

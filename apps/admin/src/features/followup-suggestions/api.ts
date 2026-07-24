import { api } from '../../shared/api/client'
import type { FollowupStatsResponse } from './types'

// Backend 는 hours 를 1~168 범위로 clamp. 기본 24h.
export const fetchFollowupStats = (hours = 24): Promise<FollowupStatsResponse> =>
  api.get(`admin/followup-suggestions/stats`, { searchParams: { hours } }).json()

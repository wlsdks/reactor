// Follow-up suggestion CTR 통계.
// Backend: modules/admin/.../FollowupSuggestionStatsController (GET /api/admin/followup-suggestions/stats).
// Backend 응답의 FollowupStats + CategoryStats 구조를 TS 로 미러링.

export interface CategoryStats {
  category: string
  impressions: number
  clicks: number
  ctr: number
}

export interface FollowupStatsResponse {
  windowHours: number
  totalImpressions: number
  totalClicks: number
  ctr: number
  byCategory: CategoryStats[]
}

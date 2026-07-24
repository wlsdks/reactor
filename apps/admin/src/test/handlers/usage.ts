import { http, HttpResponse } from 'msw'
import { NOW, DAY } from './shared'

const DEFAULT_DAYS = 30
const SUPPORTED_DAYS = new Set([1, 7, 30, 90])

function selectedDays(request: Request): number {
  const value = Number(new URL(request.url).searchParams.get('days'))
  return SUPPORTED_DAYS.has(value) ? value : DEFAULT_DAYS
}

function selectedLimit(request: Request): number {
  const value = Number(new URL(request.url).searchParams.get('limit'))
  return Number.isInteger(value) && value > 0 ? value : 20
}

function periodValue(value: number, days: number, minimum = 0): number {
  return Math.max(minimum, Math.round(value * (days / DEFAULT_DAYS)))
}

function money(value: number): string {
  return value.toFixed(2)
}

function generateMockUsersCost() {
  const users = []

  for (let i = 0; i < 20; i++) {
    const cost = i < 4 ? 1000 + Math.random() * 600 : 30 + Math.random() * 50
    const sessions = Math.round(10 + Math.random() * 150)
    users.push({
      user_id: `user-${String(i + 1).padStart(3, '0')}`,
      session_count: sessions,
      total_tokens: Math.round(cost * 3500),
      total_cost_usd: money(Math.round(cost * 100) / 100),
      avg_latency_ms: Math.round(200 + Math.random() * 800),
      last_activity: new Date(NOW - Math.round(Math.random() * 14 * DAY)).toISOString(),
    })
  }

  users.sort((a, b) => Number(b.total_cost_usd) - Number(a.total_cost_usd))
  return users
}

function generateDailyTrend() {
  const points = []
  for (let i = 89; i >= 0; i--) {
    const date = new Date(NOW - i * DAY)
    const dateStr = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
    const base = 120 + Math.random() * 60
    points.push({
      day: dateStr,
      session_count: Math.round(40 + Math.random() * 30),
      total_tokens: Math.round(base * 3500),
      total_cost_usd: money(Math.round(base * 100) / 100),
      unique_users: Math.round(5 + Math.random() * 15),
    })
  }
  return points
}

const mockUsersCost = generateMockUsersCost()
const mockDailyTrend = generateDailyTrend()
const mockModelUsage = [
  {
    model: 'gpt-5-mini',
    provider: 'openai',
    call_count: 734,
    prompt_tokens: 1870000,
    completion_tokens: 960000,
    total_tokens: 2830000,
    total_cost_usd: '2450.32',
    last_activity: new Date(NOW - 18 * 60 * 1000).toISOString(),
  },
  {
    model: 'claude-sonnet-4-20250514',
    provider: 'anthropic',
    call_count: 261,
    prompt_tokens: 840000,
    completion_tokens: 520000,
    total_tokens: 1360000,
    total_cost_usd: '1740.85',
    last_activity: new Date(NOW - 46 * 60 * 1000).toISOString(),
  },
  {
    model: 'gemma4:12b',
    provider: 'ollama',
    call_count: 128,
    prompt_tokens: 312000,
    completion_tokens: 206000,
    total_tokens: 518000,
    total_cost_usd: '0.00',
    last_activity: new Date(NOW - 2 * 60 * 60 * 1000).toISOString(),
  },
]

function usersCostForPeriod(days: number) {
  return mockUsersCost.map((row) => ({
    ...row,
    session_count: periodValue(row.session_count, days, 1),
    total_tokens: periodValue(row.total_tokens, days, 1),
    total_cost_usd: money(Number(row.total_cost_usd) * (days / DEFAULT_DAYS)),
  }))
}

function modelUsageForPeriod(days: number) {
  return mockModelUsage.map((row) => ({
    ...row,
    call_count: periodValue(row.call_count, days, 1),
    prompt_tokens: periodValue(row.prompt_tokens, days, 1),
    completion_tokens: periodValue(row.completion_tokens, days, 1),
    total_tokens: periodValue(row.total_tokens, days, 1),
    total_cost_usd: money(Number(row.total_cost_usd) * (days / DEFAULT_DAYS)),
  }))
}

// For backward-compatible export (used by tests)
export const mockUsageDashboard = {
  totalUsers: mockUsersCost.length,
  totalCost: mockUsersCost.reduce((sum, u) => sum + Number(u.total_cost_usd), 0),
  totalTokens: mockUsersCost.reduce((sum, u) => sum + u.total_tokens, 0),
  avgCostPerUser: mockUsersCost.reduce((sum, u) => sum + Number(u.total_cost_usd), 0) / mockUsersCost.length,
  topUsers: mockUsersCost.map(u => ({
    userId: u.user_id,
    sessionCount: u.session_count,
    totalTokens: u.total_tokens,
    totalCostUsd: Number(u.total_cost_usd),
    avgLatencyMs: u.avg_latency_ms,
    lastActivity: u.last_activity,
  })),
}

export const usageHandlers = [
  http.get('/api/admin/users/usage/cost', ({ request }) => {
    const days = selectedDays(request)
    return HttpResponse.json(usersCostForPeriod(days).slice(0, selectedLimit(request)))
  }),

  http.get('/api/admin/users/usage/daily', ({ request }) => {
    return HttpResponse.json(mockDailyTrend.slice(-selectedDays(request)))
  }),

  http.get('/api/admin/users/usage/by-model', ({ request }) => {
    return HttpResponse.json(modelUsageForPeriod(selectedDays(request)))
  }),

]

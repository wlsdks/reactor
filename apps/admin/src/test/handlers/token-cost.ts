import { http, HttpResponse } from 'msw'
import { NOW, HOUR, DAY } from './shared'

const MODELS = ['claude-sonnet-4-20250514', 'claude-haiku-35-20241022', 'claude-opus-4-20250514']

function buildMockSessionCosts(sessionId: string) {
  return Array.from({ length: 4 }, (_, i) => ({
    run_id: `run-${sessionId}-${i + 1}`,
    model: MODELS[i % MODELS.length],
    provider: 'anthropic',
    step_type: 'llm_call',
    prompt_tokens: 200 + i * 100,
    completion_tokens: 300 + i * 150,
    total_tokens: 500 + i * 250,
    estimated_cost_usd: 0.002 + i * 0.001,
    time: NOW - HOUR + i * 60000,
  }))
}

export const mockSessionCosts = buildMockSessionCosts('session-1')

export const mockDailyCost = [
  { day: '2026-04-01', model: 'claude-sonnet-4-20250514', prompt_tokens: 5000, completion_tokens: 7500, total_tokens: 12500, total_cost_usd: 0.045 },
  { day: '2026-04-02', model: 'claude-haiku-35-20241022', prompt_tokens: 3200, completion_tokens: 4800, total_tokens: 8000, total_cost_usd: 0.012 },
]

export const mockTopExpensive = [
  { run_id: 'run-expensive-1', total_tokens: 25000, total_cost_usd: 0.089, model: 'claude-opus-4-20250514', time: NOW - DAY },
  { run_id: 'run-expensive-2', total_tokens: 18000, total_cost_usd: 0.045, model: 'claude-sonnet-4-20250514', time: NOW - 2 * DAY },
]

export const tokenCostHandlers = [
  http.get('/api/admin/token-cost/by-session', ({ request }) => {
    const url = new URL(request.url)
    const sessionId = url.searchParams.get('sessionId') ?? 'session-1'
    return HttpResponse.json(buildMockSessionCosts(sessionId))
  }),

  http.get('/api/admin/token-cost/daily', () => {
    return HttpResponse.json(mockDailyCost)
  }),

  http.get('/api/admin/token-cost/top-expensive', () => {
    return HttpResponse.json(mockTopExpensive)
  }),
]

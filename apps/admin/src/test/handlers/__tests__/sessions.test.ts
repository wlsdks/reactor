import { describe, expect, it } from 'vitest'

describe('session mock handlers', () => {
  it('mirrors the backend overview contract without fixture-only analytics', async () => {
    const response = await fetch('http://localhost/api/admin/sessions/overview?period=30d')

    expect(response.ok).toBe(true)
    await expect(response.json()).resolves.toEqual({
      period: '30d',
      days: 30,
      totalSessions: 150,
      statusCounts: { completed: 145, failed: 5 },
      uniqueUsers: 20,
    })
  })

  it('returns the status and timestamps rendered by the session ledger', async () => {
    const response = await fetch('http://localhost/api/admin/sessions?offset=0&limit=1')

    expect(response.ok).toBe(true)
    const body = await response.json() as { items: Array<Record<string, unknown>> }
    expect(body.items[0]).toEqual(expect.objectContaining({
      status: 'failed',
      createdAt: expect.any(Number),
      updatedAt: expect.any(Number),
    }))
  })

  it('keeps every mock user summary within valid count bounds', async () => {
    const response = await fetch('http://localhost/api/admin/users')
    const body = await response.json() as { items: Array<{ sessionCount: number; totalMessages: number }> }

    expect(body.items).toHaveLength(20)
    expect(body.items.every(({ sessionCount, totalMessages }) => sessionCount >= 0 && totalMessages >= 0)).toBe(true)
  })
})

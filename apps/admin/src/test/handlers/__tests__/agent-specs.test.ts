import { describe, expect, it } from 'vitest'
import { mockAgentSpecs } from '../agent-specs'

describe('agent spec mock handlers', () => {
  it('serves the backend list contract without exposing the resolved answer principles', async () => {
    const response = await fetch('http://localhost/api/admin/agent-specs')

    expect(response.ok).toBe(true)
    const payload = await response.json() as Array<Record<string, unknown>>
    expect(payload).toEqual(mockAgentSpecs)
    expect(payload[0]).toEqual(expect.objectContaining({
      id: expect.any(String),
      systemPromptPreview: expect.any(String),
      hasSystemPrompt: expect.any(Boolean),
      independentExecution: expect.any(Boolean),
    }))
    expect(payload[0]).not.toHaveProperty('systemPrompt')
  })

  it('serves the full answer principles only through its audited endpoint', async () => {
    const response = await fetch(
      'http://localhost/api/admin/agent-specs/agent-spec-support/system-prompt',
    )

    expect(response.ok).toBe(true)
    await expect(response.json()).resolves.toEqual({
      systemPrompt: expect.stringContaining('근거를 먼저 확인'),
    })
  })
})

import { describe, it, expect } from 'vitest'
import { mcpServerSchema } from '../schema'

describe('mcpServerSchema', () => {
  const valid = {
    name: 'my-server-1',
    transportType: 'STREAMABLE_HTTP' as const,
    configRaw: '{"url":"http://localhost:8080"}',
    tags: ['env:prod', 'type:custom'],
  }

  it('accepts valid input', () => {
    expect(mcpServerSchema.safeParse(valid).success).toBe(true)
  })

  it('rejects empty name', () => {
    expect(mcpServerSchema.safeParse({ ...valid, name: '' }).success).toBe(false)
  })

  it('rejects name with uppercase', () => {
    expect(mcpServerSchema.safeParse({ ...valid, name: 'MyServer' }).success).toBe(false)
  })

  it('rejects name starting with hyphen', () => {
    expect(mcpServerSchema.safeParse({ ...valid, name: '-server' }).success).toBe(false)
  })

  it('rejects invalid JSON config', () => {
    expect(mcpServerSchema.safeParse({ ...valid, configRaw: 'not json' }).success).toBe(false)
  })

  it('rejects JSON array config', () => {
    expect(mcpServerSchema.safeParse({ ...valid, configRaw: '[1,2]' }).success).toBe(false)
  })

  it('rejects invalid tag format', () => {
    expect(mcpServerSchema.safeParse({ ...valid, tags: ['no-colon'] }).success).toBe(false)
  })

  it('accepts empty tags', () => {
    expect(mcpServerSchema.safeParse({ ...valid, tags: [] }).success).toBe(true)
  })

  it('accepts tags array at the 50 item limit', () => {
    const tags = Array.from({ length: 50 }, (_, i) => `env:tag-${i}`)
    expect(mcpServerSchema.safeParse({ ...valid, tags }).success).toBe(true)
  })

  it('rejects tags array longer than 50 items', () => {
    const tags = Array.from({ length: 51 }, (_, i) => `env:tag-${i}`)
    expect(mcpServerSchema.safeParse({ ...valid, tags }).success).toBe(false)
  })

  it('rejects invalid transport type', () => {
    expect(mcpServerSchema.safeParse({ ...valid, transportType: 'GRPC' }).success).toBe(false)
  })
})

import { describe, expect, it } from 'vitest'
import { mockTraces } from '../../../test/handlers/traces'

describe('traces mock data', () => {
  it('generates 10 traces', () => {
    expect(mockTraces).toHaveLength(10)
  })

  it('every trace has a unique trace_id', () => {
    const ids = mockTraces.map((t) => t.trace_id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('every trace has required fields', () => {
    for (const trace of mockTraces) {
      expect(trace).toHaveProperty('trace_id')
      expect(trace).toHaveProperty('time')
      expect(trace).toHaveProperty('total_duration_ms')
      expect(trace).toHaveProperty('span_count')
      expect(trace).toHaveProperty('success')
      expect(trace).toHaveProperty('run_id')
    }
  })

  it('every trace has positive total_duration_ms', () => {
    for (const trace of mockTraces) {
      expect(trace.total_duration_ms).toBeGreaterThan(0)
    }
  })

  it('contains at least one error trace (success=false)', () => {
    expect(mockTraces.some((t) => !t.success)).toBe(true)
  })

  it('contains at least one successful trace', () => {
    expect(mockTraces.some((t) => t.success)).toBe(true)
  })

  it('different run_ids are represented', () => {
    const runIds = new Set(mockTraces.map((t) => t.run_id))
    expect(runIds.size).toBeGreaterThanOrEqual(2)
  })
})

import { describe, it, expect } from 'vitest'

import {
  createFaqChannelSchema,
  updateFaqChannelSchema,
  faqProbeSchema,
  faqDryRunSchema,
} from '../schema'

describe('createFaqChannelSchema', () => {
  it('accepts a minimal valid payload (channelId only)', () => {
    expect(createFaqChannelSchema.safeParse({ channelId: 'C123' }).success).toBe(true)
  })

  it('rejects missing channelId', () => {
    expect(createFaqChannelSchema.safeParse({}).success).toBe(false)
  })

  it('rejects empty channelId', () => {
    expect(createFaqChannelSchema.safeParse({ channelId: '' }).success).toBe(false)
  })

  it('rejects channelId longer than 64 chars', () => {
    expect(
      createFaqChannelSchema.safeParse({ channelId: 'a'.repeat(65) }).success,
    ).toBe(false)
  })

  it('accepts channelId at exactly 64 chars', () => {
    expect(
      createFaqChannelSchema.safeParse({ channelId: 'a'.repeat(64) }).success,
    ).toBe(true)
  })

  it('rejects channelName longer than 128 chars', () => {
    expect(
      createFaqChannelSchema.safeParse({
        channelId: 'C',
        channelName: 'a'.repeat(129),
      }).success,
    ).toBe(false)
  })

  it('accepts all autoReplyMode enum values', () => {
    for (const mode of ['OFF', 'AUTO', 'SUGGEST'] as const) {
      expect(
        createFaqChannelSchema.safeParse({ channelId: 'C', autoReplyMode: mode }).success,
      ).toBe(true)
    }
  })

  it('rejects unknown autoReplyMode', () => {
    expect(
      createFaqChannelSchema.safeParse({
        channelId: 'C',
        autoReplyMode: 'BOGUS',
      }).success,
    ).toBe(false)
  })

  it('rejects confidenceThreshold below 0', () => {
    expect(
      createFaqChannelSchema.safeParse({ channelId: 'C', confidenceThreshold: -0.01 }).success,
    ).toBe(false)
  })

  it('rejects confidenceThreshold above 1', () => {
    expect(
      createFaqChannelSchema.safeParse({ channelId: 'C', confidenceThreshold: 1.01 }).success,
    ).toBe(false)
  })

  it('accepts confidenceThreshold at boundaries (0 and 1)', () => {
    expect(
      createFaqChannelSchema.safeParse({ channelId: 'C', confidenceThreshold: 0 }).success,
    ).toBe(true)
    expect(
      createFaqChannelSchema.safeParse({ channelId: 'C', confidenceThreshold: 1 }).success,
    ).toBe(true)
  })

  it('rejects daysBack below 1', () => {
    expect(createFaqChannelSchema.safeParse({ channelId: 'C', daysBack: 0 }).success).toBe(
      false,
    )
  })

  it('rejects daysBack above 365', () => {
    expect(createFaqChannelSchema.safeParse({ channelId: 'C', daysBack: 366 }).success).toBe(
      false,
    )
  })

  it('rejects non-integer daysBack', () => {
    expect(createFaqChannelSchema.safeParse({ channelId: 'C', daysBack: 1.5 }).success).toBe(
      false,
    )
  })

  it('rejects reIngestIntervalHours out of range (1-720)', () => {
    expect(
      createFaqChannelSchema.safeParse({ channelId: 'C', reIngestIntervalHours: 0 }).success,
    ).toBe(false)
    expect(
      createFaqChannelSchema.safeParse({ channelId: 'C', reIngestIntervalHours: 721 }).success,
    ).toBe(false)
  })

  it('accepts reIngestIntervalHours at boundaries (1 and 720)', () => {
    expect(
      createFaqChannelSchema.safeParse({ channelId: 'C', reIngestIntervalHours: 1 }).success,
    ).toBe(true)
    expect(
      createFaqChannelSchema.safeParse({ channelId: 'C', reIngestIntervalHours: 720 }).success,
    ).toBe(true)
  })
})

describe('updateFaqChannelSchema', () => {
  it('accepts an empty payload (all fields optional)', () => {
    expect(updateFaqChannelSchema.safeParse({}).success).toBe(true)
  })

  it('omits channelId — passing it is ignored, not rejected', () => {
    // When .omit() removes a key, zod ignores extra props by default — confirm shape excludes it.
    const parsed = updateFaqChannelSchema.safeParse({ channelId: 'C' })
    expect(parsed.success).toBe(true)
    if (parsed.success) {
      expect('channelId' in parsed.data).toBe(false)
    }
  })

  it('still validates field bounds on partial update', () => {
    expect(
      updateFaqChannelSchema.safeParse({ confidenceThreshold: 1.5 }).success,
    ).toBe(false)
  })
})

describe('faqProbeSchema', () => {
  it('requires query', () => {
    expect(faqProbeSchema.safeParse({}).success).toBe(false)
  })

  it('rejects empty query', () => {
    expect(faqProbeSchema.safeParse({ query: '' }).success).toBe(false)
  })

  it('rejects query longer than 2000 chars', () => {
    expect(faqProbeSchema.safeParse({ query: 'a'.repeat(2001) }).success).toBe(false)
  })

  it('accepts query at 2000 chars', () => {
    expect(faqProbeSchema.safeParse({ query: 'a'.repeat(2000) }).success).toBe(true)
  })

  it('rejects topK below 1', () => {
    expect(faqProbeSchema.safeParse({ query: 'q', topK: 0 }).success).toBe(false)
  })

  it('rejects topK above 20', () => {
    expect(faqProbeSchema.safeParse({ query: 'q', topK: 21 }).success).toBe(false)
  })

  it('accepts topK at boundaries (1 and 20)', () => {
    expect(faqProbeSchema.safeParse({ query: 'q', topK: 1 }).success).toBe(true)
    expect(faqProbeSchema.safeParse({ query: 'q', topK: 20 }).success).toBe(true)
  })
})

describe('faqDryRunSchema', () => {
  it('requires query', () => {
    expect(faqDryRunSchema.safeParse({}).success).toBe(false)
  })

  it('rejects empty query', () => {
    expect(faqDryRunSchema.safeParse({ query: '' }).success).toBe(false)
  })

  it('rejects query longer than 2000 chars', () => {
    expect(faqDryRunSchema.safeParse({ query: 'a'.repeat(2001) }).success).toBe(false)
  })

  it('rejects userId longer than 128 chars', () => {
    expect(
      faqDryRunSchema.safeParse({ query: 'q', userId: 'u'.repeat(129) }).success,
    ).toBe(false)
  })

  it('accepts asMention boolean', () => {
    expect(faqDryRunSchema.safeParse({ query: 'q', asMention: true }).success).toBe(true)
    expect(faqDryRunSchema.safeParse({ query: 'q', asMention: false }).success).toBe(true)
  })

  it('rejects non-boolean asMention', () => {
    expect(
      faqDryRunSchema.safeParse({ query: 'q', asMention: 'yes' as unknown as boolean }).success,
    ).toBe(false)
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as faqApi from '../api'

const mockMethods = {
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockMethods.get(...args),
    post: (...args: unknown[]) => mockMethods.post(...args),
    patch: (...args: unknown[]) => mockMethods.patch(...args),
    delete: (...args: unknown[]) => mockMethods.delete(...args),
  },
}))

beforeEach(() => {
  Object.values(mockMethods).forEach((fn) => fn.mockReset())
  mockMethods.get.mockReturnValue({ json: () => Promise.resolve([]) })
  mockMethods.post.mockReturnValue({ json: () => Promise.resolve({}) })
  mockMethods.patch.mockReturnValue({ json: () => Promise.resolve({}) })
  mockMethods.delete.mockResolvedValue(undefined)
})

type MethodName = 'get' | 'post' | 'patch' | 'delete'

interface Case {
  name: string
  call: () => Promise<unknown>
  method: MethodName
  path: string
}

const cases: Case[] = [
  {
    name: 'listFaqChannels',
    call: () => faqApi.listFaqChannels(),
    method: 'get',
    path: 'admin/slack/channels/faq',
  },
  {
    name: 'getFaqChannel',
    call: () => faqApi.getFaqChannel('c1'),
    method: 'get',
    path: 'admin/slack/channels/faq/c1',
  },
  {
    name: 'createFaqChannel',
    call: () => faqApi.createFaqChannel({ channelId: 'c1' }),
    method: 'post',
    path: 'admin/slack/channels/faq',
  },
  {
    name: 'updateFaqChannel',
    call: () => faqApi.updateFaqChannel('c1', {}),
    method: 'patch',
    path: 'admin/slack/channels/faq/c1',
  },
  {
    name: 'deleteFaqChannel',
    call: () => faqApi.deleteFaqChannel('c1'),
    method: 'delete',
    path: 'admin/slack/channels/faq/c1',
  },
  {
    name: 'ingestFaqChannel',
    call: () => faqApi.ingestFaqChannel('c1'),
    method: 'post',
    path: 'admin/slack/channels/faq/c1/ingest',
  },
  {
    name: 'getFaqChannelStats',
    call: () => faqApi.getFaqChannelStats('c1'),
    method: 'get',
    path: 'admin/slack/channels/faq/c1/stats',
  },
  {
    name: 'getFaqOrgStats',
    call: () => faqApi.getFaqOrgStats(),
    method: 'get',
    path: 'admin/slack/channels/faq/stats',
  },
  {
    name: 'getFaqChannelEvents',
    call: () => faqApi.getFaqChannelEvents('c1'),
    method: 'get',
    path: 'admin/slack/channels/faq/c1/events',
  },
  {
    name: 'getFaqChannelFeedback',
    call: () => faqApi.getFaqChannelFeedback('c1'),
    method: 'get',
    path: 'admin/slack/channels/faq/c1/feedback',
  },
  {
    name: 'probeFaqChannel',
    call: () => faqApi.probeFaqChannel('c1', { query: 'q' }),
    method: 'post',
    path: 'admin/slack/channels/faq/c1/probe',
  },
  {
    name: 'dryRunFaqChannel',
    call: () => faqApi.dryRunFaqChannel('c1', { query: 'q' }),
    method: 'post',
    path: 'admin/slack/channels/faq/c1/dry-run',
  },
  {
    name: 'getFaqSchedulerHealth',
    call: () => faqApi.getFaqSchedulerHealth(),
    method: 'get',
    path: 'admin/slack/channels/faq/scheduler/health',
  },
]

describe.each(cases)('slack-faq api — $name', ({ call, method, path }) => {
  it(`calls ${method.toUpperCase()} ${path}`, async () => {
    await call()
    const fn = mockMethods[method]
    expect(fn).toHaveBeenCalledTimes(1)
    expect(fn.mock.calls[0]?.[0]).toBe(path)
  })
})

describe('slack-faq api — encoding', () => {
  it('encodes channelId path parameters', async () => {
    await faqApi.getFaqChannel('C 1!')
    expect(mockMethods.get.mock.calls[0]?.[0]).toBe('admin/slack/channels/faq/C%201!')
  })
})

describe('slack-faq api — list endpoints include limit', () => {
  it('listFaqChannels passes limit=200 in searchParams', async () => {
    await faqApi.listFaqChannels()
    const opts = mockMethods.get.mock.calls[0]?.[1] as { searchParams?: Record<string, unknown> }
    expect(opts?.searchParams).toEqual({ limit: 200 })
  })

  it('getFaqChannelEvents passes limit=200 in searchParams', async () => {
    await faqApi.getFaqChannelEvents('c1')
    const opts = mockMethods.get.mock.calls[0]?.[1] as { searchParams?: Record<string, unknown> }
    expect(opts?.searchParams).toEqual({ limit: 200 })
  })

  it('getFaqChannelFeedback passes limit=200 in searchParams', async () => {
    await faqApi.getFaqChannelFeedback('c1')
    const opts = mockMethods.get.mock.calls[0]?.[1] as { searchParams?: Record<string, unknown> }
    expect(opts?.searchParams).toEqual({ limit: 200 })
  })
})

import { http, HttpResponse } from 'msw'
import type { SlackBot } from '../../features/slack-bots/types'

const NOW = new Date('2026-07-12T08:00:00.000Z').toISOString()

export const mockSlackBots: SlackBot[] = [
  {
    id: 'bot-jarvis',
    name: 'Jarvis 운영 봇',
    botToken: null,
    appToken: null,
    signingSecret: null,
    workspace: 'Reactor 운영 워크스페이스',
    description: '운영 알림과 관리자 명령을 처리합니다.',
    isActive: true,
    createdAt: '2026-06-14T08:00:00.000Z',
    updatedAt: NOW,
  },
  {
    id: 'bot-sandbox',
    name: '시험용 봇',
    botToken: null,
    appToken: null,
    signingSecret: null,
    workspace: '개발 시험 워크스페이스',
    description: '실제 운영에 영향을 주지 않는 연동 시험용입니다.',
    isActive: false,
    createdAt: '2026-06-21T08:00:00.000Z',
    updatedAt: '2026-07-10T08:00:00.000Z',
  },
]

export const slackBotsHandlers = [
  http.get('/api/admin/slack-bots', () => HttpResponse.json(mockSlackBots)),
  http.get('/api/admin/slack-bots/:id', ({ params }) => {
    const bot = mockSlackBots.find(item => item.id === params.id)
    return bot ? HttpResponse.json(bot) : new HttpResponse(null, { status: 404 })
  }),
  http.post('/api/admin/slack-bots', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({
      id: 'bot-created',
      name: body.name,
      workspace: body.workspace,
      description: body.description ?? null,
      isActive: true,
      botToken: null,
      appToken: null,
      signingSecret: null,
      createdAt: NOW,
      updatedAt: NOW,
    }, { status: 201 })
  }),
  http.put('/api/admin/slack-bots/:id', async ({ params, request }) => {
    const current = mockSlackBots.find(item => item.id === params.id)
    if (!current) return new HttpResponse(null, { status: 404 })
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({ ...current, ...body, botToken: null, appToken: null, signingSecret: null, updatedAt: NOW })
  }),
  http.delete('/api/admin/slack-bots/:id', () => new HttpResponse(null, { status: 204 })),
]

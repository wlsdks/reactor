import type { SlackBot, CreateSlackBotRequest, UpdateSlackBotRequest } from './types'
import { api } from '../../shared/api/client'

export const listSlackBots = (): Promise<SlackBot[]> =>
  api.get('admin/slack-bots', { searchParams: { limit: 200 } }).json()

export const getSlackBot = (id: string): Promise<SlackBot> =>
  api.get(`admin/slack-bots/${id}`).json()

export const createSlackBot = (request: CreateSlackBotRequest): Promise<SlackBot> =>
  api.post('admin/slack-bots', { json: request }).json()

export const updateSlackBot = (id: string, request: UpdateSlackBotRequest): Promise<SlackBot> =>
  api.put(`admin/slack-bots/${id}`, { json: request }).json()

export const deleteSlackBot = (id: string): Promise<void> =>
  api.delete(`admin/slack-bots/${id}`).then(() => undefined)

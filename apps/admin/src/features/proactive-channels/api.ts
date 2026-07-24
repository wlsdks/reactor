import type { ProactiveChannel, AddProactiveChannelRequest } from './types'
import { api } from '../../shared/api/client'

export const listProactiveChannels = (): Promise<ProactiveChannel[]> =>
  api.get('proactive-channels', { searchParams: { limit: 200 } }).json()

export const addProactiveChannel = (request: AddProactiveChannelRequest): Promise<ProactiveChannel> =>
  api.post('proactive-channels', { json: request }).json()

export const removeProactiveChannel = (channelId: string): Promise<void> =>
  api.delete(`proactive-channels/${encodeURIComponent(channelId)}`).json()

export interface ProactiveChannel {
  channelId: string
  channelName: string | null
  addedAt: number
}

export interface AddProactiveChannelRequest {
  channelId: string
  channelName?: string
}

export interface SlackBot {
  id: string
  name: string
  botToken: string | null
  appToken: string | null
  signingSecret: string | null
  workspace: string
  description: string | null
  isActive: boolean
  createdAt: string
  updatedAt: string
}

export interface CreateSlackBotRequest {
  name: string
  botToken: string
  appToken: string
  signingSecret: string
  workspace: string
  description?: string | null
}

export interface UpdateSlackBotRequest {
  name?: string
  botToken?: string
  appToken?: string
  signingSecret?: string
  workspace?: string
  description?: string | null
  isActive?: boolean
}

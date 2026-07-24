import type { AdminSetting } from './types'
import { api } from '../../shared/api/client'

export const listSettings = (): Promise<AdminSetting[]> =>
  api.get('admin/settings').json()

export const getSetting = (key: string): Promise<AdminSetting> =>
  api.get(`admin/settings/${encodeURIComponent(key)}`).json()

export const updateSetting = (key: string, value: string): Promise<AdminSetting> =>
  api.put(`admin/settings/${encodeURIComponent(key)}`, { json: { value } }).json()

export const deleteSetting = (key: string): Promise<void> =>
  api.delete(`admin/settings/${encodeURIComponent(key)}`).then(() => undefined)

export const refreshSettingsCache = (): Promise<void> =>
  api.post('admin/settings/refresh').then(() => undefined)

// Slack 시스템 프롬프트 md 파일을 런타임에 hot-reload 한다.
// Backend: `POST /api/admin/slack/prompts/reload` (SlackPromptReloadController, reactor.slack.enabled 필요)
export const reloadSlackPrompts = (): Promise<SlackPromptReloadResponse> =>
  api.post('admin/slack/prompts/reload').json()

export interface SlackPromptReloadResponse {
  reloaded: boolean
  sectionCount: number
  sections: string[]
}

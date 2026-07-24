import { api } from '../../shared/api/client'
import type {
  FaqChannel,
  FaqChannelStats,
  FaqOrgStats,
  FaqEvent,
  FaqFeedback,
  FaqProbeRequest,
  FaqProbeResult,
  FaqDryRunRequest,
  FaqDryRunResult,
  FaqSchedulerHealth,
  CreateFaqChannelRequest,
  UpdateFaqChannelRequest,
} from './types'

// All FAQ endpoints live under `admin/slack/channels/faq*`. Paths are spelled
// out inline (no template `${BASE}` interpolation) so the verify-admin-api
// coverage script's regex can statically extract them.

export const listFaqChannels = (): Promise<FaqChannel[]> =>
  api.get('admin/slack/channels/faq', { searchParams: { limit: 200 } }).json()

export const getFaqChannel = (channelId: string): Promise<FaqChannel> =>
  api.get(`admin/slack/channels/faq/${encodeURIComponent(channelId)}`).json()

export const createFaqChannel = (req: CreateFaqChannelRequest): Promise<FaqChannel> =>
  api.post('admin/slack/channels/faq', { json: req }).json()

export const updateFaqChannel = (
  channelId: string,
  req: UpdateFaqChannelRequest,
): Promise<FaqChannel> =>
  api.patch(`admin/slack/channels/faq/${encodeURIComponent(channelId)}`, { json: req }).json()

export const deleteFaqChannel = async (channelId: string): Promise<void> => {
  await api.delete(`admin/slack/channels/faq/${encodeURIComponent(channelId)}`)
}

export const ingestFaqChannel = async (channelId: string): Promise<void> => {
  await api.post(`admin/slack/channels/faq/${encodeURIComponent(channelId)}/ingest`)
}

export const getFaqChannelStats = (channelId: string): Promise<FaqChannelStats> =>
  api.get(`admin/slack/channels/faq/${encodeURIComponent(channelId)}/stats`).json()

export const getFaqOrgStats = (): Promise<FaqOrgStats> =>
  api.get('admin/slack/channels/faq/stats').json()

export const getFaqChannelEvents = (channelId: string): Promise<FaqEvent[]> =>
  api.get(`admin/slack/channels/faq/${encodeURIComponent(channelId)}/events`, { searchParams: { limit: 200 } }).json()

export const getFaqChannelFeedback = (channelId: string): Promise<FaqFeedback[]> =>
  api.get(`admin/slack/channels/faq/${encodeURIComponent(channelId)}/feedback`, { searchParams: { limit: 200 } }).json()

export const probeFaqChannel = (
  channelId: string,
  req: FaqProbeRequest,
): Promise<FaqProbeResult> =>
  api.post(`admin/slack/channels/faq/${encodeURIComponent(channelId)}/probe`, { json: req }).json()

export const dryRunFaqChannel = (
  channelId: string,
  req: FaqDryRunRequest,
): Promise<FaqDryRunResult> =>
  api.post(`admin/slack/channels/faq/${encodeURIComponent(channelId)}/dry-run`, { json: req }).json()

export const getFaqSchedulerHealth = (): Promise<FaqSchedulerHealth> =>
  api.get('admin/slack/channels/faq/scheduler/health').json()

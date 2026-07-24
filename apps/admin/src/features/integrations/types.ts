import type {
  A2aProtocolEvidence,
  SlackGatewaySmokeEvidence,
} from '../../shared/lib/liveSmokeEvidence'

export interface HttpCallResult {
  status: number
  body: unknown
}

export interface EndpointProbeRequest {
  path: string
  method?: string
}

export interface EndpointProbeResult {
  status: number | null
  body: unknown
  durationMs: number
  error?: string
}

export interface SlackCommandRequest {
  command: string
  text: string
  userName?: string
  channelId: string
  channelName?: string
  responseUrl: string
  triggerId?: string
}

export interface SlackEventRequest {
  payload: Record<string, unknown>
  retryNum?: string
  retryReason?: string
}

export interface ErrorReportRequest {
  stackTrace: string
  serviceName: string
  repoSlug: string
  slackChannel: string
  environment?: string
  timestamp?: string
  metadata?: Record<string, string>
  apiKey?: string
}

export interface ExternalSmokeCheck {
  status?: string
  [key: string]: unknown
}

export interface ExternalSmokeResultBase {
  ok: boolean
  status: string
  scope: string
  error?: string | null
  checks: Record<string, ExternalSmokeCheck>
}

export interface SlackLiveSmokeResult extends ExternalSmokeResultBase {
  liveTarget?: {
    workspaceId?: string | null
    channelId?: string | null
    channelName?: string | null
    botUserId?: string | null
  } | null
  evidence?: {
    slackGatewaySmoke?: SlackGatewaySmokeEvidence | null
  } | null
}

export interface A2aLiveSmokeResult extends ExternalSmokeResultBase {
  base_url?: string | null
  evidence?: {
    a2aProtocol?: A2aProtocolEvidence | null
  } | null
}

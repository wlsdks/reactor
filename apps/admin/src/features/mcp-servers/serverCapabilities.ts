import { detectMcpServerKind } from './presets'
import type { McpServerDetailResponse } from './types'

export function isAtlassianServer(detail: McpServerDetailResponse): boolean {
  return detectMcpServerKind(detail) === 'atlassian'
}

export function isSwaggerServer(detail: McpServerDetailResponse): boolean {
  return detectMcpServerKind(detail) === 'swagger'
}

export function supportsOperationalReadiness(detail: McpServerDetailResponse): boolean {
  return isAtlassianServer(detail)
}

export function supportsAdminPreflight(detail: McpServerDetailResponse): boolean {
  return supportsOperationalReadiness(detail) || isSwaggerServer(detail)
}

export function supportsAccessPolicy(detail: McpServerDetailResponse): boolean {
  return supportsOperationalReadiness(detail) || isSwaggerServer(detail)
}

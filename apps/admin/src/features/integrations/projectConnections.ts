import type { McpPreflightResponse, McpServerDetailResponse, McpServerResponse } from '../mcp-servers/types'
import { detectKnownMcpServerKind, type KnownMcpServerKind } from '../mcp-servers/presets'

export type ConnectionStatus = 'PASS' | 'WARN' | 'FAIL' | 'DISCONNECTED'

const DEFAULT_REACTOR_PATHS = [
  '/api/admin/capabilities',
  '/api/ops/dashboard',
  '/api/mcp/servers',
  '/api/tool-policy',
]

const REACTOR_API_BASE = import.meta.env.VITE_API_URL || 'same-origin'
const ATLASSIAN_EXPECTED_NAME = import.meta.env.VITE_ATLASSIAN_MCP_NAME || 'atlassian'
const SWAGGER_EXPECTED_NAME = import.meta.env.VITE_SWAGGER_MCP_NAME || 'swagger'

interface ReactorConnectionSummary {
  status: ConnectionStatus
  reason: 'ready' | 'manifest_unavailable' | 'missing_paths' | 'registry_unavailable'
  missingPaths: string[]
}

interface ManagedConnectionSummary {
  status: ConnectionStatus
  reason:
    | 'ready'
    | 'warnings'
    | 'failed'
    | 'not_registered'
    | 'not_connected'
    | 'preflight_unavailable'
    | 'no_preflight_configured'
    | 'registry_unavailable'
  warningCount: number
  failCount: number
}

export interface ReactorConnectionSnapshot {
  status: ConnectionStatus
  apiBase: string
  missingPaths: string[]
}

/**
 * 토폴로지 렌더링용 MCP 서버 연결 스냅샷.
 *
 * `id` 는 registry 에서 가져온 서버 이름 (예: `atlassian-mcp-server`, `clipping-mcp-server`)
 * 또는 known preset key (`atlassian`, `swagger`). 하드코딩 대신 registry 결과를
 * 그대로 사용하여 사용자가 등록한 모든 MCP 서버가 동적으로 표시되도록 한다.
 */
export interface McpProjectConnectionSnapshot {
  id: string
  /** UI 표시용 레이블 (registry 의 server.name 또는 preset 별칭). */
  label: string
  expectedName: string
  server: McpServerResponse | null
  preflight: McpPreflightResponse | null
  error?: string
  status: ConnectionStatus
  sourceCount?: number
  publishedSourceCount?: number
}

function evaluateReactorConnection(
  requiredPaths: string[],
  capabilityManifest: Set<string> | null,
  registryError: string | null,
): ReactorConnectionSummary {
  if (registryError) {
    return {
      status: 'FAIL',
      reason: 'registry_unavailable',
      missingPaths: [],
    }
  }

  if (!capabilityManifest) {
    return {
      status: 'WARN',
      reason: 'manifest_unavailable',
      missingPaths: [],
    }
  }

  const missingPaths = requiredPaths.filter((path) => !capabilityManifest.has(path))
  if (missingPaths.length > 0) {
    return {
      status: 'WARN',
      reason: 'missing_paths',
      missingPaths,
    }
  }

  return {
    status: 'PASS',
    reason: 'ready',
    missingPaths: [],
  }
}

function pickKnownServer(
  servers: McpServerResponse[],
  kind: Exclude<KnownMcpServerKind, 'generic'>,
  preferredName?: string,
): McpServerResponse | null {
  if (preferredName) {
    const exact = servers.find((server) => server.name.toLowerCase() === preferredName.trim().toLowerCase())
    if (exact) return exact
  }

  return servers.find((server) => detectKnownMcpServerKind(server) === kind) ?? null
}

function evaluateManagedServerConnection(
  server: McpServerResponse | null,
  preflight: McpPreflightResponse | null,
  preflightError: string | null,
): ManagedConnectionSummary {
  if (preflightError && !server) {
    return {
      status: 'FAIL',
      reason: 'registry_unavailable',
      warningCount: 0,
      failCount: 0,
    }
  }

  if (!server) {
    return {
      status: 'DISCONNECTED',
      reason: 'not_registered',
      warningCount: 0,
      failCount: 0,
    }
  }

  if (server.status !== 'CONNECTED') {
    return {
      status: 'DISCONNECTED',
      reason: 'not_connected',
      warningCount: 0,
      failCount: 0,
    }
  }

  if (preflightError) {
    // admin token 미설정 = 의도된 선택 기능 미구성. 404/400 메시지 문자열로 방어.
    // 백엔드가 204 로 전환되기 전 과도기 혹은 구버전 환경 호환용.
    if (/no admin token/i.test(preflightError)) {
      return {
        status: 'PASS',
        reason: 'no_preflight_configured',
        warningCount: 0,
        failCount: 0,
      }
    }
    return {
      status: 'FAIL',
      reason: 'preflight_unavailable',
      warningCount: 0,
      failCount: 0,
    }
  }

  if (!preflight) {
    return {
      status: 'PASS',
      reason: 'no_preflight_configured',
      warningCount: 0,
      failCount: 0,
    }
  }

  if (preflight.readyForProduction) {
    return {
      status: 'PASS',
      reason: 'ready',
      warningCount: preflight.summary.warnCount,
      failCount: preflight.summary.failCount,
    }
  }

  if (preflight.ok) {
    return {
      status: 'WARN',
      reason: 'warnings',
      warningCount: preflight.summary.warnCount,
      failCount: preflight.summary.failCount,
    }
  }

  return {
    status: 'FAIL',
    reason: 'failed',
    warningCount: preflight.summary.warnCount,
    failCount: preflight.summary.failCount,
  }
}

export function summarizeReactorConnection(
  capabilityManifest: Set<string> | null,
  registryError: string | null = null,
): ReactorConnectionSnapshot {
  const summary = evaluateReactorConnection(DEFAULT_REACTOR_PATHS, capabilityManifest, registryError)
  return {
    status: summary.status,
    apiBase: REACTOR_API_BASE,
    missingPaths: summary.missingPaths,
  }
}

export function findKnownProjectServer(
  kind: Exclude<KnownMcpServerKind, 'generic'>,
  servers: McpServerResponse[],
): McpServerResponse | null {
  return pickKnownServer(servers, kind, kind === 'atlassian' ? ATLASSIAN_EXPECTED_NAME : SWAGGER_EXPECTED_NAME)
}

/**
 * 단일 MCP 서버 레지스트리 엔트리를 토폴로지 스냅샷으로 변환한다 (동적, 제네릭).
 *
 * 하드코딩된 known-kind 분기 없이 registry 엔트리 자체를 사용하므로 사용자가
 * 등록한 모든 MCP 서버가 토폴로지에 나타난다. id/label 은 server.name 그대로
 * 사용하고, 상태는 [evaluateManagedServerConnection] 이 CONNECTED / preflight
 * 기반으로 계산한다.
 */
export function summarizeMcpProjectConnection(
  server: McpServerResponse,
  preflight: McpPreflightResponse | null,
  error?: string,
  sourceSummary?: { sourceCount: number; publishedSourceCount: number },
): McpProjectConnectionSnapshot {
  const summary = evaluateManagedServerConnection(server, preflight, error ?? null)
  return {
    id: server.name,
    label: server.name,
    expectedName: server.name,
    server,
    preflight,
    error,
    status: summary.status,
    sourceCount: sourceSummary?.sourceCount,
    publishedSourceCount: sourceSummary?.publishedSourceCount,
  }
}

/**
 * Known preset 단위 스냅샷 (Atlassian/Swagger 등 preset 상세 뷰 전용).
 *
 * Dashboard/Integrations 페이지는 preset 별 configuration readiness 와
 * source count 를 함께 표시하므로 이 API 를 유지한다. 토폴로지는
 * [summarizeMcpProjectConnection] 을 사용하여 동적 렌더링한다.
 */
export function summarizeKnownProjectConnection(
  kind: Exclude<KnownMcpServerKind, 'generic'>,
  server: McpServerResponse | null,
  preflight: McpPreflightResponse | null,
  error?: string,
  sourceSummary?: { sourceCount: number; publishedSourceCount: number },
): McpProjectConnectionSnapshot {
  const summary = evaluateManagedServerConnection(server, preflight, error ?? null)
  const expected = kind === 'atlassian' ? ATLASSIAN_EXPECTED_NAME : SWAGGER_EXPECTED_NAME
  return {
    id: kind,
    label: server?.name ?? expected,
    expectedName: expected,
    server,
    preflight,
    error,
    status: summary.status,
    sourceCount: sourceSummary?.sourceCount,
    publishedSourceCount: sourceSummary?.publishedSourceCount,
  }
}

export function toolCount(detail: McpServerDetailResponse | null): number {
  return detail?.tools.length ?? 0
}

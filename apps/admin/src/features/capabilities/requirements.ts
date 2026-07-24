export interface EndpointRequirement {
  openApiPath: string
  probePath?: string
  probeMethod?: 'GET' | 'OPTIONS'
}

export const ROUTE_REQUIREMENTS: Record<string, readonly EndpointRequirement[]> = {
  '/': [{ openApiPath: '/api/ops/dashboard' }],
  // /issues is a derived view with no single backend endpoint (issueCenter
  // aggregator). We register the upstream signal sources here so the dev
  // technicalDetails disclosure exposes which controllers feed the page.
  // The route uses allowWhenUnavailable=true, so missing sources do not block
  // rendering — issueCenter handles partial data via graceful degradation.
  '/issues': [
    { openApiPath: '/api/admin/capabilities' },
    { openApiPath: '/api/mcp/servers' },
    { openApiPath: '/api/scheduler/jobs' },
    { openApiPath: '/api/approvals' },
    { openApiPath: '/api/tool-policy' },
    { openApiPath: '/api/mcp/security' },
    { openApiPath: '/api/output-guard/rules' },
    { openApiPath: '/api/admin/audits' },
  ],
  '/personas': [{ openApiPath: '/api/personas' }],
  '/reactor-universe': [{ openApiPath: '/api/admin/agent-specs', probePath: '/api/admin/agent-specs', probeMethod: 'GET' }],
  '/prompt-studio': [
    { openApiPath: '/api/prompt-templates' },
  ],
  '/mcp-servers': [{ openApiPath: '/api/mcp/servers' }],
  '/mcp-servers/:name': [{ openApiPath: '/api/mcp/servers' }],
  '/scheduler': [{ openApiPath: '/api/scheduler/jobs' }],
  '/approvals': [{ openApiPath: '/api/approvals' }],
  '/sessions': [{ openApiPath: '/api/admin/sessions' }],
  '/debug-replay': [
    { openApiPath: '/api/admin/debug/replay' },
    { openApiPath: '/api/admin/debug/replay/{id}' },
  ],
  '/traces': [{ openApiPath: '/api/admin/traces' }],
  '/feedback': [{ openApiPath: '/api/feedback' }],
  '/safety-rules': [
    { openApiPath: '/api/output-guard/rules' },
    { openApiPath: '/api/tool-policy' },
  ],
  '/documents': [
    { openApiPath: '/api/documents' },
    // Policy RAG bulk-seed lives behind the page header's "Bulk seed policy"
    // button. Probe with OPTIONS so we don't trigger an actual seed during
    // capability detection — the BE controller is gated on
    // `reactor.admin.enabled=true` and rejects non-admins, so missing this
    // endpoint should hide the button rather than block the page.
    { openApiPath: '/api/admin/rag/seed-policy', probeMethod: 'OPTIONS' },
    // '/api/rag-ingestion/candidates' 는 tab 단위 선택 기능이라 route gate 에서 제외.
    // 후보 탭은 미탑재 시 탭 내부에서 자체 안내를 표시한다.
  ],
  '/rag-cache': [
    { openApiPath: '/api/admin/platform/cache/stats' },
    { openApiPath: '/api/admin/platform/cache/invalidate' },
    { openApiPath: '/api/admin/platform/cache/invalidate-key' },
    { openApiPath: '/api/admin/platform/cache/invalidate-by-pattern' },
    { openApiPath: '/api/admin/platform/vectorstore/stats' },
    { openApiPath: '/api/admin/settings' },
    { openApiPath: '/api/admin/rag-analytics/status' },
    { openApiPath: '/api/admin/rag-analytics/by-channel' },
    { openApiPath: '/api/rag-ingestion/policy' },
    { openApiPath: '/api/rag-ingestion/candidates' },
    { openApiPath: '/api/documents/search' },
  ],
  '/audit': [{ openApiPath: '/api/admin/audits' }],
  '/metrics-ingestion': [
    { openApiPath: '/api/admin/metrics/ingest/mcp-health', probeMethod: 'OPTIONS' },
    { openApiPath: '/api/admin/metrics/ingest/tool-call', probeMethod: 'OPTIONS' },
    { openApiPath: '/api/admin/metrics/ingest/eval-result', probeMethod: 'OPTIONS' },
    { openApiPath: '/api/admin/metrics/ingest/eval-results', probeMethod: 'OPTIONS' },
    { openApiPath: '/api/admin/metrics/ingest/batch', probeMethod: 'OPTIONS' },
  ],
  '/chat-inspector': [{ openApiPath: '/api/chat' }],
  '/evals': [
    { openApiPath: '/api/ops/dashboard' },
    { openApiPath: '/api/admin/evals/runs' },
    { openApiPath: '/api/admin/evals/pass-rate' },
    { openApiPath: '/api/admin/agent-eval/cases' },
  ],
  // /integrations 는 Slack/Error-report/ProactiveChannels/Bots 탭 조합. 각 탭이
  // 독립적이므로 admin capabilities 만 필수로 요구하고 나머지는 탭 단위에서 자체
  // 안내. 기존 proactive-channels/slack-bots 누락 시 페이지 전체가 차단되던 회귀 수정.
  '/integrations': [{ openApiPath: '/api/admin/capabilities' }],
  '/performance': [
    { openApiPath: '/api/admin/metrics/latency/summary' },
    { openApiPath: '/api/admin/tools/stats' },
  ],
  // The report renders all three sources in its first view. Keep the route
  // contract aligned with the requests it actually makes rather than a
  // fixture-era "top" endpoint that no longer drives the screen.
  '/usage': [
    { openApiPath: '/api/admin/users/usage/cost' },
    { openApiPath: '/api/admin/users/usage/daily' },
    { openApiPath: '/api/admin/users/usage/by-model' },
  ],
  '/access-control': [
    { openApiPath: '/api/admin/rbac/roles' },
    { openApiPath: '/api/admin/platform/users/by-email' },
    { openApiPath: '/api/admin/platform/users/{id}/role' },
  ],
  '/models': [
    { openApiPath: '/api/admin/models' },
    { openApiPath: '/api/admin/platform/pricing' },
    { openApiPath: '/api/admin/platform/alerts/rules' },
    { openApiPath: '/api/admin/platform/alerts/rules/{id}' },
    { openApiPath: '/api/admin/platform/alerts' },
    { openApiPath: '/api/admin/platform/alerts/{id}/resolve' },
    { openApiPath: '/api/admin/platform/alerts/evaluate' },
  ],
  '/health': [
    { openApiPath: '/api/admin/platform/health' },
    { openApiPath: '/api/admin/platform/cache/invalidate' },
    { openApiPath: '/api/admin/platform/alerts/evaluate' },
  ],
  '/tenants': [
    { openApiPath: '/api/admin/platform/tenants' },
    { openApiPath: '/api/admin/platform/tenants/{id}', probeMethod: 'OPTIONS' },
    { openApiPath: '/api/admin/platform/tenants/{id}/suspend' },
    { openApiPath: '/api/admin/platform/tenants/{id}/activate' },
    { openApiPath: '/api/admin/platform/tenants/analytics' },
    { openApiPath: '/api/admin/tenant/overview' },
    { openApiPath: '/api/admin/tenant/usage' },
    { openApiPath: '/api/admin/tenant/quality' },
    { openApiPath: '/api/admin/tenant/tools' },
    { openApiPath: '/api/admin/tenant/cost' },
    { openApiPath: '/api/admin/tenant/slo' },
    { openApiPath: '/api/admin/tenant/alerts' },
    { openApiPath: '/api/admin/tenant/quota' },
    { openApiPath: '/api/admin/tenant/export/executions' },
    { openApiPath: '/api/admin/tenant/export/tools' },
  ],
  '/settings': [
    { openApiPath: '/api/admin/settings' },
    { openApiPath: '/api/admin/retention' },
  ],
}

export interface ProbeTarget {
  openApiPath: string
  path: string
  method: 'GET' | 'OPTIONS'
}

function normalizeRoutePath(routePath: string): string {
  return routePath.split(/[?#]/, 1)[0] || '/'
}

export function getRouteRequirements(routePath: string): readonly string[] {
  return (ROUTE_REQUIREMENTS[normalizeRoutePath(routePath)] ?? []).map((item) => item.openApiPath)
}

export function getAllProbeTargets(): ProbeTarget[] {
  const unique = new Map<string, ProbeTarget>()

  Object.values(ROUTE_REQUIREMENTS).forEach((requirements) => {
    requirements.forEach((requirement) => {
      const path = requirement.probePath ?? requirement.openApiPath
      const method = requirement.probeMethod ?? 'GET'
      const key = `${method}:${path}`
      if (!unique.has(key)) {
        unique.set(key, {
          openApiPath: requirement.openApiPath,
          path,
          method,
        })
      }
    })
  })

  return [...unique.values()]
}

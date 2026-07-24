interface SessionFeedKeyFilters {
  q?: string
  offset?: number
}

interface SessionUsersKeyParams {
  q?: string
  sortBy?: string
  period?: string
  offset?: number
}

interface SessionUserSessionsKeyFilters {
  q?: string
  offset?: number
}

export const queryKeys = {
  /** Canonical key for `/api/admin/capabilities` manifest. Kept as a simple
   *  top-level key so all consumers (FeatureAvailabilityProvider, dashboard
   *  topology, integrations manager, issue center) hit the same cache entry
   *  and TanStack Query dedupes concurrent fetches. */
  capabilities: () => ['capabilities'] as const,
  personas: {
    all: () => ['personas'] as const,
    list: () => ['personas', 'list'] as const,
    detail: (id: string) => ['personas', id] as const,
  },
  prompts: {
    all: () => ['prompts'] as const,
    list: () => ['prompts', 'list'] as const,
    detail: (id: string) => ['prompts', id] as const,
  },
  mcpServers: {
    all: () => ['mcp-servers'] as const,
    list: () => ['mcp-servers', 'list'] as const,
    detail: (name: string) => ['mcp-servers', name] as const,
    policy: (serverName: string) => ['mcp-servers', serverName, 'policy'] as const,
    swaggerSources: (serverName: string) => ['mcp-servers', serverName, 'swagger-sources'] as const,
    swaggerRevisions: (sourceId: string) => ['mcp-servers', 'swagger-revisions', sourceId] as const,
    preflight: (serverName: string) => ['mcp-servers', serverName, 'preflight'] as const,
  },
  scheduler: {
    all: () => ['scheduler'] as const,
    list: () => ['scheduler', 'list'] as const,
    detail: (id: string) => ['scheduler', id] as const,
    executions: (jobId: string) => ['scheduler', jobId, 'executions'] as const,
  },
  approvals: {
    all: () => ['approvals'] as const,
    list: (status?: string) => ['approvals', 'list', status] as const,
  },
  /** R538: Debug Replay — 실패 요청 캡처 조회.
   *  Detail key includes the explicit `'detail'` segment so list and detail
   *  caches share the same `['debugReplay']` root and a single
   *  `invalidateQueries({ queryKey: ['debugReplay'] })` clears both. */
  debugReplay: {
    all: () => ['debugReplay'] as const,
    list: () => ['debugReplay', 'list'] as const,
    detail: (id: string) => ['debugReplay', 'detail', id] as const,
  },
  sessions: {
    all: () => ['sessions'] as const,
    overview: (period: string) => ['sessions', 'overview', period] as const,
    feed: (filters: SessionFeedKeyFilters) => ['sessions', 'feed', filters] as const,
    detail: (id: string) => ['sessions', 'detail', id] as const,
    messages: (id: string) => ['sessions', 'messages', id] as const,
    users: (params: SessionUsersKeyParams) => ['sessions', 'users', params] as const,
    userDetail: (userId: string) => ['sessions', 'users', userId] as const,
    userSessions: (userId: string, filters: SessionUserSessionsKeyFilters) => ['sessions', 'users', userId, 'sessions', filters] as const,
    models: () => ['sessions', 'models'] as const,
  },
  feedback: {
    all: () => ['feedback'] as const,
    list: (params?: Record<string, string | number | boolean | undefined>) =>
      ['feedback', 'list', params] as const,
    detail: (id: string) => ['feedback', id] as const,
    stats: (from?: string, to?: string) => ['feedback', 'stats', from, to] as const,
    unreviewedCount: () => ['feedback', 'unreviewed-count'] as const,
  },
  proactiveChannels: {
    all: () => ['proactive-channels'] as const,
    list: () => ['proactive-channels', 'list'] as const,
  },
  tenantAdmin: {
    all: () => ['tenant-admin'] as const,
    overview: (tenantId: string, fromMs?: number, toMs?: number) => ['tenant-admin', 'overview', tenantId, fromMs, toMs] as const,
    usage: (tenantId: string, fromMs?: number, toMs?: number) => ['tenant-admin', 'usage', tenantId, fromMs, toMs] as const,
    quality: (tenantId: string, fromMs?: number, toMs?: number) => ['tenant-admin', 'quality', tenantId, fromMs, toMs] as const,
    tools: (tenantId: string, fromMs?: number, toMs?: number) => ['tenant-admin', 'tools', tenantId, fromMs, toMs] as const,
    cost: (tenantId: string, fromMs?: number, toMs?: number) => ['tenant-admin', 'cost', tenantId, fromMs, toMs] as const,
    slo: (tenantId: string) => ['tenant-admin', 'slo', tenantId] as const,
    alerts: (tenantId: string) => ['tenant-admin', 'alerts', tenantId] as const,
    quota: (tenantId: string) => ['tenant-admin', 'quota', tenantId] as const,
  },
  outputGuard: {
    all: () => ['output-guard'] as const,
    list: () => ['output-guard', 'list'] as const,
    audits: () => ['output-guard', 'audits'] as const,
  },
  toolPolicy: {
    all: () => ['tool-policy'] as const,
    list: () => ['tool-policy', 'list'] as const,
  },
  toolStats: {
    all: () => ['tool-stats'] as const,
    stats: (server?: string) => ['tool-stats', 'stats', server ?? null] as const,
    accuracy: () => ['tool-stats', 'accuracy'] as const,
  },
  documents: {
    all: () => ['documents'] as const,
    list: () => ['documents', 'list'] as const,
    candidates: (status?: string, channel?: string) => ['documents', 'candidates', status, channel] as const,
    policy: () => ['documents', 'policy'] as const,
  },
  intents: {
    all: () => ['intents'] as const,
    list: () => ['intents', 'list'] as const,
    detail: (name: string) => ['intents', name] as const,
  },
  audit: {
    all: () => ['audit'] as const,
    list: (category?: string, action?: string) => ['audit', 'list', category, action] as const,
    rollbackPreview: (id: string) => ['audit', 'rollback-preview', id] as const,
  },
  dashboard: {
    all: () => ['dashboard'] as const,
    summary: () => ['dashboard', 'summary'] as const,
    main: (names?: string[]) => ['dashboard', 'main', names] as const,
    metricNames: () => ['dashboard', 'metricNames'] as const,
    readiness: () => ['dashboard', 'readiness'] as const,
    topology: () => ['dashboard', 'topology'] as const,
  },
  doctor: {
    all: () => ['doctor'] as const,
    summary: () => ['doctor', 'summary'] as const,
    report: () => ['doctor', 'report'] as const,
  },
  mcpSecurity: {
    all: () => ['mcp-security'] as const,
    list: () => ['mcp-security', 'list'] as const,
  },
  chatInspector: {
    all: () => ['chat-inspector'] as const,
    list: () => ['chat-inspector', 'list'] as const,
  },
  promptLab: {
    all: () => ['prompt-lab'] as const,
    list: (status?: string) => ['prompt-lab', 'list', status] as const,
    detail: (id: string) => ['prompt-lab', id] as const,
    status: (id: string) => ['prompt-lab', id, 'status'] as const,
    trials: (id: string) => ['prompt-lab', id, 'trials'] as const,
    report: (id: string) => ['prompt-lab', id, 'report'] as const,
  },
  evals: {
    all: () => ['evals'] as const,
    list: (days?: number) => ['evals', 'list', days] as const,
    summary: (days?: number) => ['evals', 'summary', days] as const,
    cases: () => ['evals', 'persisted-cases'] as const,
  },
  integrations: {
    all: () => ['integrations'] as const,
    probes: () => ['integrations', 'probes'] as const,
    connections: () => ['integrations', 'connections'] as const,
  },
  issues: {
    snapshot: () => ['issues', 'snapshot'] as const,
    topology: () => ['issues', 'topology'] as const,
  },
  ragCache: {
    all: () => ['rag-cache'] as const,
    stats: () => ['rag-cache', 'stats'] as const,
    vectorStore: () => ['rag-cache', 'vector-store'] as const,
    policy: () => ['rag-cache', 'policy'] as const,
    /** Broad prefix for invalidating every cached candidate filter combination
     *  after an approve / reject / bulk action. */
    candidatesRoot: () => ['rag-cache', 'candidates'] as const,
    candidates: (filters?: { status?: string; channel?: string }) =>
      ['rag-cache', 'candidates', filters ?? {}] as const,
    analyticsStatus: () => ['rag-cache', 'analytics', 'status'] as const,
    analyticsByChannel: () => ['rag-cache', 'analytics', 'by-channel'] as const,
    runtimeSetting: (key: string) => ['rag-cache', 'setting', key] as const,
    runtimeSettings: () => ['rag-cache', 'settings'] as const,
  },
  reactorUniverse: {
    all: () => ['reactor-universe'] as const,
    list: () => ['reactor-universe', 'list'] as const,
    detail: (id: string) => ['reactor-universe', id] as const,
    systemPrompt: (id: string) => ['reactor-universe', id, 'system-prompt'] as const,
  },
  traces: {
    all: () => ['traces'] as const,
    list: (days?: number, _unused?: unknown, status?: string) =>
      ['traces', 'list', days, status] as const,
    detail: (id: string) => ['traces', id] as const,
    toolCalls: (runId?: string, days?: number) => ['traces', 'tool-calls', runId, days] as const,
    toolCallRanking: (days?: number) => ['traces', 'tool-call-ranking', days] as const,
  },
  tokenCost: {
    all: () => ['token-cost'] as const,
    session: (sessionId: string) => ['token-cost', 'session', sessionId] as const,
    daily: (days?: number) => ['token-cost', 'daily', days] as const,
    topExpensive: (days?: number, limit?: number) => ['token-cost', 'top-expensive', days, limit] as const,
  },
  inputGuard: {
    all: () => ['input-guard'] as const,
    pipeline: () => ['input-guard', 'pipeline'] as const,
    audits: (params: { limit?: number; action?: string } = {}) =>
      ['input-guard', 'audits', params] as const,
    stats: (params: { hours?: number; tenantId?: string } = {}) =>
      ['input-guard', 'stats', params] as const,
    rules: () => ['input-guard', 'rules'] as const,
    rule: (id: string) => ['input-guard', 'rule', id] as const,
    stageConfig: (stageName: string) => ['input-guard', 'stageConfig', stageName] as const,
  },
  latency: {
    all: () => ['latency'] as const,
    timeSeries: (days?: number) => ['latency', 'timeSeries', days] as const,
    summary: () => ['latency', 'summary'] as const,
  },
  usage: {
    all: () => ['usage'] as const,
    dashboard: (days?: number) => ['usage', 'dashboard', days] as const,
    daily: (days?: number) => ['usage', 'daily', days] as const,
    top: (days?: number, limit?: number) => ['usage', 'top', days, limit] as const,
    byModel: (days?: number) => ['usage', 'byModel', days] as const,
  },
  platformAdmin: {
    all: () => ['platform-admin'] as const,
    health: () => ['platform-admin', 'health'] as const,
    tenants: () => ['platform-admin', 'tenants'] as const,
    pricing: () => ['platform-admin', 'pricing'] as const,
    alertRules: () => ['platform-admin', 'alert-rules'] as const,
    activeAlerts: () => ['platform-admin', 'active-alerts'] as const,
    tenant: (id: string) => ['platform-admin', 'tenants', id] as const,
    userByEmail: (email: string | null | undefined) =>
      ['platform-admin', 'user-by-email', email] as const,
  },
  rbac: {
    all: () => ['rbac'] as const,
    list: () => ['rbac', 'list'] as const,
  },
  models: {
    all: () => ['models'] as const,
    list: () => ['models', 'list'] as const,
  },
  slackBots: {
    all: () => ['slack-bots'] as const,
    list: () => ['slack-bots', 'list'] as const,
    detail: (id: string) => ['slack-bots', id] as const,
  },
  slackActivity: {
    all: () => ['slack-activity'] as const,
    channels: (days?: number) => ['slack-activity', 'channels', days] as const,
    daily: (days?: number) => ['slack-activity', 'daily', days] as const,
  },
  slackFaq: {
    all: () => ['slack-faq'] as const,
    /** Broad prefix that invalidates both the channels list and any per-channel
     *  caches sharing the `['slack-faq', 'channels']` head. Use this for
     *  `invalidateQueries` after channel create/delete. */
    channelsRoot: () => ['slack-faq', 'channels'] as const,
    channels: () => ['slack-faq', 'channels', 'list'] as const,
    channel: (id: string) => ['slack-faq', 'channel', id] as const,
    channelStats: (id: string) => ['slack-faq', 'channel', id, 'stats'] as const,
    orgStats: () => ['slack-faq', 'org-stats'] as const,
    events: (id: string) => ['slack-faq', 'channel', id, 'events'] as const,
    feedback: (id: string) => ['slack-faq', 'channel', id, 'feedback'] as const,
    schedulerHealth: () => ['slack-faq', 'scheduler', 'health'] as const,
  },
  retention: {
    all: () => ['retention'] as const,
    policy: () => ['retention', 'policy'] as const,
  },
  ragAnalytics: {
    all: () => ['rag-analytics'] as const,
    status: () => ['rag-analytics', 'status'] as const,
    byChannel: (days?: number) => ['rag-analytics', 'by-channel', days] as const,
  },
  conversationAnalytics: {
    all: () => ['conversation-analytics'] as const,
    byChannel: (days?: number) => ['conversation-analytics', 'by-channel', days] as const,
    failurePatterns: (days?: number) => ['conversation-analytics', 'failure-patterns', days] as const,
    latencyDistribution: (days?: number) => ['conversation-analytics', 'latency-distribution', days] as const,
  },
  userMemory: {
    all: () => ['user-memory'] as const,
    detail: (userId: string) => ['user-memory', userId] as const,
  },
  adminSettings: {
    all: () => ['admin-settings'] as const,
    list: () => ['admin-settings', 'list'] as const,
    detail: (key: string) => ['admin-settings', key] as const,
  },
  followupSuggestions: {
    all: () => ['followup-suggestions'] as const,
    stats: (windowHours: number) =>
      ['followup-suggestions', 'stats', windowHours] as const,
  },
}

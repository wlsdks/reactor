import { describe, it, expect } from 'vitest'
import { queryKeys } from '../queryKeys'

describe('queryKeys.personas', () => {
  it('all returns ["personas"]', () => {
    expect(queryKeys.personas.all()).toEqual(['personas'])
  })
  it('list returns ["personas", "list"]', () => {
    expect(queryKeys.personas.list()).toEqual(['personas', 'list'])
  })
  it('detail returns ["personas", id]', () => {
    expect(queryKeys.personas.detail('abc')).toEqual(['personas', 'abc'])
  })
})

describe('queryKeys.prompts', () => {
  it('all returns ["prompts"]', () => {
    expect(queryKeys.prompts.all()).toEqual(['prompts'])
  })
  it('list returns ["prompts", "list"]', () => {
    expect(queryKeys.prompts.list()).toEqual(['prompts', 'list'])
  })
  it('detail returns ["prompts", id]', () => {
    expect(queryKeys.prompts.detail('p1')).toEqual(['prompts', 'p1'])
  })
})

describe('queryKeys.mcpServers', () => {
  it('all returns ["mcp-servers"]', () => {
    expect(queryKeys.mcpServers.all()).toEqual(['mcp-servers'])
  })
  it('list returns ["mcp-servers", "list"]', () => {
    expect(queryKeys.mcpServers.list()).toEqual(['mcp-servers', 'list'])
  })
  it('detail returns ["mcp-servers", name]', () => {
    expect(queryKeys.mcpServers.detail('my-server')).toEqual(['mcp-servers', 'my-server'])
  })
  it('policy returns ["mcp-servers", serverName, "policy"]', () => {
    expect(queryKeys.mcpServers.policy('my-server')).toEqual(['mcp-servers', 'my-server', 'policy'])
  })
  it('swaggerSources returns ["mcp-servers", serverName, "swagger-sources"]', () => {
    expect(queryKeys.mcpServers.swaggerSources('s')).toEqual(['mcp-servers', 's', 'swagger-sources'])
  })
  it('swaggerRevisions returns ["mcp-servers", "swagger-revisions", sourceId]', () => {
    expect(queryKeys.mcpServers.swaggerRevisions('sid')).toEqual(['mcp-servers', 'swagger-revisions', 'sid'])
  })
  it('preflight returns ["mcp-servers", serverName, "preflight"]', () => {
    expect(queryKeys.mcpServers.preflight('s')).toEqual(['mcp-servers', 's', 'preflight'])
  })
})

describe('queryKeys.scheduler', () => {
  it('all returns ["scheduler"]', () => {
    expect(queryKeys.scheduler.all()).toEqual(['scheduler'])
  })
  it('list returns ["scheduler", "list"]', () => {
    expect(queryKeys.scheduler.list()).toEqual(['scheduler', 'list'])
  })
  it('detail returns ["scheduler", id]', () => {
    expect(queryKeys.scheduler.detail('j1')).toEqual(['scheduler', 'j1'])
  })
  it('executions returns ["scheduler", jobId, "executions"]', () => {
    expect(queryKeys.scheduler.executions('j1')).toEqual(['scheduler', 'j1', 'executions'])
  })
})

describe('queryKeys.approvals', () => {
  it('list with status returns ["approvals", "list", status]', () => {
    expect(queryKeys.approvals.list('PENDING')).toEqual(['approvals', 'list', 'PENDING'])
  })
  it('list without status returns ["approvals", "list", undefined]', () => {
    expect(queryKeys.approvals.list()).toEqual(['approvals', 'list', undefined])
  })
})

describe('queryKeys.sessions', () => {
  it('all returns ["sessions"]', () => {
    expect(queryKeys.sessions.all()).toEqual(['sessions'])
  })
  it('overview returns ["sessions", "overview", period]', () => {
    expect(queryKeys.sessions.overview('7d')).toEqual(['sessions', 'overview', '7d'])
  })
  it('feed returns ["sessions", "feed", filters]', () => {
    const filters = { q: 'test' }
    expect(queryKeys.sessions.feed(filters)).toEqual(['sessions', 'feed', filters])
  })
  it('detail returns ["sessions", "detail", id]', () => {
    expect(queryKeys.sessions.detail('s1')).toEqual(['sessions', 'detail', 's1'])
  })
  it('users returns ["sessions", "users", params]', () => {
    const params = { q: 'user1' }
    expect(queryKeys.sessions.users(params)).toEqual(['sessions', 'users', params])
  })
  it('userSessions returns ["sessions", "users", userId, "sessions", filters]', () => {
    const filters = { channel: ['web' as const] }
    expect(queryKeys.sessions.userSessions('u1', filters)).toEqual(['sessions', 'users', 'u1', 'sessions', filters])
  })
})

describe('queryKeys.dashboard', () => {
  it('summary returns ["dashboard", "summary"]', () => {
    expect(queryKeys.dashboard.summary()).toEqual(['dashboard', 'summary'])
  })
})

describe('queryKeys.promptLab', () => {
  it('status returns ["prompt-lab", id, "status"]', () => {
    expect(queryKeys.promptLab.status('pl1')).toEqual(['prompt-lab', 'pl1', 'status'])
  })
  it('trials returns ["prompt-lab", id, "trials"]', () => {
    expect(queryKeys.promptLab.trials('pl1')).toEqual(['prompt-lab', 'pl1', 'trials'])
  })
  it('report returns ["prompt-lab", id, "report"]', () => {
    expect(queryKeys.promptLab.report('pl1')).toEqual(['prompt-lab', 'pl1', 'report'])
  })
})

describe('queryKeys.platformAdmin', () => {
  it('all returns ["platform-admin"]', () => {
    expect(queryKeys.platformAdmin.all()).toEqual(['platform-admin'])
  })
  it('health returns ["platform-admin", "health"]', () => {
    expect(queryKeys.platformAdmin.health()).toEqual(['platform-admin', 'health'])
  })
  it('tenants returns ["platform-admin", "tenants"]', () => {
    expect(queryKeys.platformAdmin.tenants()).toEqual(['platform-admin', 'tenants'])
  })
  it('pricing returns ["platform-admin", "pricing"]', () => {
    expect(queryKeys.platformAdmin.pricing()).toEqual(['platform-admin', 'pricing'])
  })
  it('alertRules returns ["platform-admin", "alert-rules"]', () => {
    expect(queryKeys.platformAdmin.alertRules()).toEqual(['platform-admin', 'alert-rules'])
  })
  it('activeAlerts returns ["platform-admin", "active-alerts"]', () => {
    expect(queryKeys.platformAdmin.activeAlerts()).toEqual(['platform-admin', 'active-alerts'])
  })
  it('tenant returns ["platform-admin", "tenants", id]', () => {
    expect(queryKeys.platformAdmin.tenant('t1')).toEqual(['platform-admin', 'tenants', 't1'])
  })
})

describe('queryKeys.integrations', () => {
  it('all returns ["integrations"]', () => {
    expect(queryKeys.integrations.all()).toEqual(['integrations'])
  })
  it('probes returns ["integrations", "probes"]', () => {
    expect(queryKeys.integrations.probes()).toEqual(['integrations', 'probes'])
  })
  it('connections returns ["integrations", "connections"]', () => {
    expect(queryKeys.integrations.connections()).toEqual(['integrations', 'connections'])
  })
})

describe('queryKeys.issues', () => {
  it('snapshot returns ["issues", "snapshot"]', () => {
    expect(queryKeys.issues.snapshot()).toEqual(['issues', 'snapshot'])
  })
  it('topology returns ["issues", "topology"]', () => {
    expect(queryKeys.issues.topology()).toEqual(['issues', 'topology'])
  })
})

describe('queryKeys.ragCache', () => {
  it('all returns ["rag-cache"]', () => {
    expect(queryKeys.ragCache.all()).toEqual(['rag-cache'])
  })
  it('stats returns ["rag-cache", "stats"]', () => {
    expect(queryKeys.ragCache.stats()).toEqual(['rag-cache', 'stats'])
  })
  it('vectorStore returns ["rag-cache", "vector-store"]', () => {
    expect(queryKeys.ragCache.vectorStore()).toEqual(['rag-cache', 'vector-store'])
  })
  it('policy returns ["rag-cache", "policy"]', () => {
    expect(queryKeys.ragCache.policy()).toEqual(['rag-cache', 'policy'])
  })
})

describe('queryKeys.feedback', () => {
  it('all returns ["feedback"]', () => {
    expect(queryKeys.feedback.all()).toEqual(['feedback'])
  })
  it('list without params returns ["feedback", "list", undefined]', () => {
    expect(queryKeys.feedback.list()).toEqual(['feedback', 'list', undefined])
  })
  it('list with params includes params', () => {
    const params = { rating: 'thumbs_up' }
    expect(queryKeys.feedback.list(params)).toEqual(['feedback', 'list', params])
  })
  it('detail returns ["feedback", id]', () => {
    expect(queryKeys.feedback.detail('fb1')).toEqual(['feedback', 'fb1'])
  })
})

describe('queryKeys.proactiveChannels', () => {
  it('all returns ["proactive-channels"]', () => {
    expect(queryKeys.proactiveChannels.all()).toEqual(['proactive-channels'])
  })
  it('list returns ["proactive-channels", "list"]', () => {
    expect(queryKeys.proactiveChannels.list()).toEqual(['proactive-channels', 'list'])
  })
})

describe('queryKeys.tenantAdmin', () => {
  it('all returns ["tenant-admin"]', () => {
    expect(queryKeys.tenantAdmin.all()).toEqual(['tenant-admin'])
  })
  it('overview returns ["tenant-admin", "overview", tenantId]', () => {
    expect(queryKeys.tenantAdmin.overview('t1', 100, 200)).toEqual(['tenant-admin', 'overview', 't1', 100, 200])
  })
  it('usage returns ["tenant-admin", "usage", tenantId, fromMs, toMs]', () => {
    expect(queryKeys.tenantAdmin.usage('t1', 100, 200)).toEqual(['tenant-admin', 'usage', 't1', 100, 200])
  })
  it('quality returns ["tenant-admin", "quality", tenantId, fromMs, toMs]', () => {
    expect(queryKeys.tenantAdmin.quality('t1', 100, 200)).toEqual(['tenant-admin', 'quality', 't1', 100, 200])
  })
  it('tools returns ["tenant-admin", "tools", tenantId, fromMs, toMs]', () => {
    expect(queryKeys.tenantAdmin.tools('t1', 100, 200)).toEqual(['tenant-admin', 'tools', 't1', 100, 200])
  })
  it('cost returns ["tenant-admin", "cost", tenantId, fromMs, toMs]', () => {
    expect(queryKeys.tenantAdmin.cost('t1', 100, 200)).toEqual(['tenant-admin', 'cost', 't1', 100, 200])
  })
  it('slo returns ["tenant-admin", "slo", tenantId]', () => {
    expect(queryKeys.tenantAdmin.slo('t1')).toEqual(['tenant-admin', 'slo', 't1'])
  })
  it('alerts returns ["tenant-admin", "alerts", tenantId]', () => {
    expect(queryKeys.tenantAdmin.alerts('t1')).toEqual(['tenant-admin', 'alerts', 't1'])
  })
  it('quota returns ["tenant-admin", "quota", tenantId]', () => {
    expect(queryKeys.tenantAdmin.quota('t1')).toEqual(['tenant-admin', 'quota', 't1'])
  })
})

describe('queryKeys.outputGuard', () => {
  it('all returns ["output-guard"]', () => {
    expect(queryKeys.outputGuard.all()).toEqual(['output-guard'])
  })
  it('list returns ["output-guard", "list"]', () => {
    expect(queryKeys.outputGuard.list()).toEqual(['output-guard', 'list'])
  })
  it('audits returns ["output-guard", "audits"]', () => {
    expect(queryKeys.outputGuard.audits()).toEqual(['output-guard', 'audits'])
  })
})

describe('queryKeys.toolPolicy', () => {
  it('all returns ["tool-policy"]', () => {
    expect(queryKeys.toolPolicy.all()).toEqual(['tool-policy'])
  })
  it('list returns ["tool-policy", "list"]', () => {
    expect(queryKeys.toolPolicy.list()).toEqual(['tool-policy', 'list'])
  })
})

describe('queryKeys.documents', () => {
  it('all returns ["documents"]', () => {
    expect(queryKeys.documents.all()).toEqual(['documents'])
  })
  it('list returns ["documents", "list"]', () => {
    expect(queryKeys.documents.list()).toEqual(['documents', 'list'])
  })
  it('candidates returns ["documents", "candidates", status, channel]', () => {
    expect(queryKeys.documents.candidates('pending', 'web')).toEqual(['documents', 'candidates', 'pending', 'web'])
  })
  it('candidates without args returns ["documents", "candidates", undefined, undefined]', () => {
    expect(queryKeys.documents.candidates()).toEqual(['documents', 'candidates', undefined, undefined])
  })
  it('policy returns ["documents", "policy"]', () => {
    expect(queryKeys.documents.policy()).toEqual(['documents', 'policy'])
  })
})

describe('queryKeys.intents', () => {
  it('all returns ["intents"]', () => {
    expect(queryKeys.intents.all()).toEqual(['intents'])
  })
  it('list returns ["intents", "list"]', () => {
    expect(queryKeys.intents.list()).toEqual(['intents', 'list'])
  })
  it('detail returns ["intents", name]', () => {
    expect(queryKeys.intents.detail('greeting')).toEqual(['intents', 'greeting'])
  })
})

describe('queryKeys.audit', () => {
  it('all returns ["audit"]', () => {
    expect(queryKeys.audit.all()).toEqual(['audit'])
  })
  it('list with category and action', () => {
    expect(queryKeys.audit.list('auth', 'login')).toEqual(['audit', 'list', 'auth', 'login'])
  })
  it('list without args', () => {
    expect(queryKeys.audit.list()).toEqual(['audit', 'list', undefined, undefined])
  })
})

describe('queryKeys.dashboard (remaining keys)', () => {
  it('all returns ["dashboard"]', () => {
    expect(queryKeys.dashboard.all()).toEqual(['dashboard'])
  })
  it('main returns ["dashboard", "main", names]', () => {
    expect(queryKeys.dashboard.main(['cpu', 'mem'])).toEqual(['dashboard', 'main', ['cpu', 'mem']])
  })
  it('main without args returns ["dashboard", "main", undefined]', () => {
    expect(queryKeys.dashboard.main()).toEqual(['dashboard', 'main', undefined])
  })
  it('metricNames returns ["dashboard", "metricNames"]', () => {
    expect(queryKeys.dashboard.metricNames()).toEqual(['dashboard', 'metricNames'])
  })
  it('readiness returns ["dashboard", "readiness"]', () => {
    expect(queryKeys.dashboard.readiness()).toEqual(['dashboard', 'readiness'])
  })
  it('topology returns ["dashboard", "topology"]', () => {
    expect(queryKeys.dashboard.topology()).toEqual(['dashboard', 'topology'])
  })
})

describe('queryKeys.mcpSecurity', () => {
  it('all returns ["mcp-security"]', () => {
    expect(queryKeys.mcpSecurity.all()).toEqual(['mcp-security'])
  })
  it('list returns ["mcp-security", "list"]', () => {
    expect(queryKeys.mcpSecurity.list()).toEqual(['mcp-security', 'list'])
  })
})

describe('queryKeys.chatInspector', () => {
  it('all returns ["chat-inspector"]', () => {
    expect(queryKeys.chatInspector.all()).toEqual(['chat-inspector'])
  })
  it('list returns ["chat-inspector", "list"]', () => {
    expect(queryKeys.chatInspector.list()).toEqual(['chat-inspector', 'list'])
  })
})

describe('queryKeys.promptLab (remaining keys)', () => {
  it('all returns ["prompt-lab"]', () => {
    expect(queryKeys.promptLab.all()).toEqual(['prompt-lab'])
  })
  it('list with status returns ["prompt-lab", "list", status]', () => {
    expect(queryKeys.promptLab.list('active')).toEqual(['prompt-lab', 'list', 'active'])
  })
  it('list without status returns ["prompt-lab", "list", undefined]', () => {
    expect(queryKeys.promptLab.list()).toEqual(['prompt-lab', 'list', undefined])
  })
  it('detail returns ["prompt-lab", id]', () => {
    expect(queryKeys.promptLab.detail('exp1')).toEqual(['prompt-lab', 'exp1'])
  })
})

describe('queryKeys.sessions (remaining keys)', () => {
  it('messages returns ["sessions", "messages", id]', () => {
    expect(queryKeys.sessions.messages('s1')).toEqual(['sessions', 'messages', 's1'])
  })
  it('userDetail returns ["sessions", "users", userId]', () => {
    expect(queryKeys.sessions.userDetail('u1')).toEqual(['sessions', 'users', 'u1'])
  })
  it('models returns ["sessions", "models"]', () => {
    expect(queryKeys.sessions.models()).toEqual(['sessions', 'models'])
  })
})

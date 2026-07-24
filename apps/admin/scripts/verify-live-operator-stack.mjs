#!/usr/bin/env node

const API_BASE = process.env.OPERATOR_STACK_API_BASE || 'http://127.0.0.1:8010'
const ADMIN_EMAIL = process.env.OPERATOR_STACK_ADMIN_EMAIL
  || process.env.PLAYWRIGHT_LIVE_ADMIN_EMAIL
  || 'admin@example.com'
const ADMIN_PASSWORD = process.env.OPERATOR_STACK_ADMIN_PASSWORD
  || process.env.PLAYWRIGHT_LIVE_ADMIN_PASSWORD
  || 'admin1234'
const EXPECTED_SWAGGER_SOURCES = csvEnv('OPERATOR_STACK_SWAGGER_SOURCES', ['petstore-public'])
const EXPECTED_JIRA_KEYS = csvEnv('OPERATOR_STACK_JIRA_KEYS')
const EXPECTED_CONFLUENCE_KEYS = csvEnv('OPERATOR_STACK_CONFLUENCE_KEYS')
const EXPECTED_BITBUCKET_REPOS = csvEnv('OPERATOR_STACK_BITBUCKET_REPOS')
const REQUIRED_CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/admin/audits',
  '/api/approvals',
  '/api/mcp/security',
  '/api/mcp/servers',
  '/api/output-guard/rules',
  '/api/scheduler/jobs',
  '/api/tool-policy',
]

function csvEnv(name, fallback = []) {
  const raw = process.env[name]
  if (!raw) return fallback
  return raw.split(',').map((item) => item.trim()).filter(Boolean)
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message)
  }
}

function isObject(value) {
  return value != null && typeof value === 'object' && !Array.isArray(value)
}

async function readJson(response) {
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('json')) {
    return response.json()
  }
  return response.text()
}

async function requestJson(pathname, options = {}) {
  const response = await fetch(new URL(pathname, API_BASE), options)
  const body = await readJson(response)
  if (!response.ok) {
    const detail = isObject(body)
      ? body.error || body.message || JSON.stringify(body)
      : String(body)
    throw new Error(`${options.method || 'GET'} ${pathname} failed: HTTP ${response.status}${detail ? ` (${detail})` : ''}`)
  }
  return body
}

async function login() {
  const body = await requestJson('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: ADMIN_EMAIL,
      password: ADMIN_PASSWORD,
    }),
  })

  assert(isObject(body), 'Login response must be an object')
  assert(typeof body.token === 'string' && body.token.length > 0, 'Login response is missing token')
  assert(isObject(body.user), 'Login response is missing user')
  assert(typeof body.user.email === 'string', 'Login user email is missing')
  assert(typeof body.user.role === 'string', 'Login user role is missing')
  assert(
    body.user.role === 'ADMIN' || body.user.role === 'ADMIN_MANAGER' || body.user.role === 'ADMIN_DEVELOPER',
    `Login user role is not admin: ${body.user.role}`,
  )

  return body.token
}

async function authedJson(token, pathname, options = {}) {
  const headers = new Headers(options.headers || {})
  headers.set('Authorization', `Bearer ${token}`)
  if (!headers.has('Content-Type') && options.body != null) {
    headers.set('Content-Type', 'application/json')
  }
  return requestJson(pathname, {
    ...options,
    headers,
  })
}

function expectListContainsAll(actual, expected, label) {
  const missing = expected.filter((item) => !actual.includes(item))
  assert(missing.length === 0, `${label} is missing expected entries: ${missing.join(', ')}`)
}

function summarizeServer(server, preflight, policy) {
  return {
    status: server.status,
    transportType: server.transportType,
    toolCount: server.toolCount,
    preflight: {
      readyForProduction: preflight.readyForProduction,
      passCount: preflight.summary?.passCount ?? 0,
      warnCount: preflight.summary?.warnCount ?? 0,
      failCount: preflight.summary?.failCount ?? 0,
      checkedAt: preflight.checkedAt ?? null,
    },
    policy: {
      policySource: policy.policySource,
      dynamicEnabled: policy.dynamicEnabled,
      allowedJiraProjectKeys: policy.allowedJiraProjectKeys ?? [],
      allowedConfluenceSpaceKeys: policy.allowedConfluenceSpaceKeys ?? [],
      allowedBitbucketRepositories: policy.allowedBitbucketRepositories ?? [],
      allowedSourceNames: policy.allowedSourceNames ?? [],
    },
  }
}

async function verifyHealth() {
  const health = await requestJson('/actuator/health')
  assert(isObject(health), 'Actuator health must be an object')
  assert(String(health.status).toUpperCase() === 'UP', `Actuator health is not UP: ${health.status}`)
  return { status: health.status }
}

async function verifyCapabilities(token) {
  const manifest = await authedJson(token, '/api/admin/capabilities')
  assert(isObject(manifest), 'Capability manifest must be an object')
  assert(Array.isArray(manifest.paths), 'Capability manifest paths must be an array')
  expectListContainsAll(manifest.paths, REQUIRED_CAPABILITY_PATHS, 'Capability manifest')
  return {
    generatedAt: manifest.generatedAt ?? null,
    pathCount: manifest.paths.length,
  }
}

async function verifyServers(token) {
  const servers = await authedJson(token, '/api/mcp/servers')
  assert(Array.isArray(servers), 'MCP registry response must be an array')

  const swagger = servers.find((server) => server?.name === 'swagger')
  const atlassian = servers.find((server) => server?.name === 'atlassian')
  assert(swagger, 'swagger server is not registered')
  assert(atlassian, 'atlassian server is not registered')

  for (const server of [swagger, atlassian]) {
    assert(server.status === 'CONNECTED', `${server.name} is not CONNECTED`)
    assert(typeof server.toolCount === 'number' && server.toolCount > 0, `${server.name} toolCount must be positive`)
  }

  const [swaggerPreflight, swaggerPolicy, atlassianPreflight, atlassianPolicy] = await Promise.all([
    authedJson(token, '/api/mcp/servers/swagger/preflight'),
    authedJson(token, '/api/mcp/servers/swagger/access-policy'),
    authedJson(token, '/api/mcp/servers/atlassian/preflight'),
    authedJson(token, '/api/mcp/servers/atlassian/access-policy'),
  ])

  for (const [name, preflight] of [['swagger', swaggerPreflight], ['atlassian', atlassianPreflight]]) {
    assert(isObject(preflight), `${name} preflight must be an object`)
    assert(preflight.ok === true, `${name} preflight is not ok`)
    assert(preflight.readyForProduction === true, `${name} preflight is not production-ready`)
    assert((preflight.summary?.warnCount ?? 0) === 0, `${name} preflight warnCount is not zero`)
    assert((preflight.summary?.failCount ?? 0) === 0, `${name} preflight failCount is not zero`)
  }

  assert(isObject(swaggerPolicy), 'swagger policy must be an object')
  assert(Array.isArray(swaggerPolicy.allowedSourceNames), 'swagger allowedSourceNames must be an array')
  expectListContainsAll(swaggerPolicy.allowedSourceNames, EXPECTED_SWAGGER_SOURCES, 'Swagger policy allowedSourceNames')

  assert(isObject(atlassianPolicy), 'atlassian policy must be an object')
  for (const [label, expected, actual] of [
    ['Jira keys', EXPECTED_JIRA_KEYS, atlassianPolicy.allowedJiraProjectKeys],
    ['Confluence keys', EXPECTED_CONFLUENCE_KEYS, atlassianPolicy.allowedConfluenceSpaceKeys],
    ['Bitbucket repositories', EXPECTED_BITBUCKET_REPOS, atlassianPolicy.allowedBitbucketRepositories],
  ]) {
    assert(Array.isArray(actual), `Atlassian ${label} must be an array`)
    if (expected.length > 0) {
      expectListContainsAll(actual, expected, `Atlassian ${label}`)
    } else {
      assert(actual.length > 0, `Atlassian ${label} must not be empty`)
    }
  }

  return {
    registryCount: servers.length,
    connectedCount: servers.filter((server) => server?.status === 'CONNECTED').length,
    swagger: summarizeServer(swagger, swaggerPreflight, swaggerPolicy),
    atlassian: summarizeServer(atlassian, atlassianPreflight, atlassianPolicy),
  }
}

async function verifyMcpSecurity(token) {
  const policy = await authedJson(token, '/api/mcp/security')
  assert(isObject(policy), 'MCP security policy must be an object')
  assert(isObject(policy.effective), 'MCP security effective policy must be an object')
  assert(Array.isArray(policy.effective.allowedServerNames), 'MCP security allowedServerNames must be an array')
  expectListContainsAll(policy.effective.allowedServerNames, ['swagger', 'atlassian'], 'MCP security allowedServerNames')
  assert(
    typeof policy.effective.maxToolOutputLength === 'number' && policy.effective.maxToolOutputLength > 0,
    'MCP security maxToolOutputLength must be positive',
  )
  return {
    allowedServerNames: policy.effective.allowedServerNames,
    maxToolOutputLength: policy.effective.maxToolOutputLength,
  }
}

async function verifyToolPolicy(token) {
  const policy = await authedJson(token, '/api/tool-policy')
  assert(isObject(policy), 'Tool policy must be an object')
  assert(typeof policy.configEnabled === 'boolean', 'Tool policy configEnabled must be boolean')
  assert(typeof policy.dynamicEnabled === 'boolean', 'Tool policy dynamicEnabled must be boolean')
  assert(isObject(policy.effective), 'Tool policy effective state must be an object')
  assert(Array.isArray(policy.effective.writeToolNames), 'Tool policy writeToolNames must be an array')
  assert(Array.isArray(policy.effective.denyWriteChannels), 'Tool policy denyWriteChannels must be an array')
  return {
    configEnabled: policy.configEnabled,
    dynamicEnabled: policy.dynamicEnabled,
    writeToolNames: policy.effective.writeToolNames.length,
    denyWriteChannels: policy.effective.denyWriteChannels.length,
  }
}

async function verifyArrayEndpoint(token, pathname, label) {
  const body = await authedJson(token, pathname)
  assert(Array.isArray(body), `${label} response must be an array`)
  return { count: body.length }
}

async function main() {
  const summary = {
    apiBase: API_BASE,
    adminEmail: ADMIN_EMAIL,
    actuator: null,
    user: null,
    capabilities: null,
    mcpRegistry: null,
    mcpSecurity: null,
    toolPolicy: null,
    schedulerJobs: null,
    approvals: null,
    auditLogs: null,
    outputGuardRules: null,
    outputGuardAudits: null,
  }

  summary.actuator = await verifyHealth()
  const token = await login()
  const me = await authedJson(token, '/api/auth/me')
  assert(isObject(me), 'Authenticated user response must be an object')
  summary.user = {
    email: me.email ?? null,
    role: me.role ?? null,
    adminScope: me.adminScope ?? null,
  }
  summary.capabilities = await verifyCapabilities(token)
  summary.mcpRegistry = await verifyServers(token)
  summary.mcpSecurity = await verifyMcpSecurity(token)
  summary.toolPolicy = await verifyToolPolicy(token)
  summary.schedulerJobs = await verifyArrayEndpoint(token, '/api/scheduler/jobs', 'Scheduler jobs')
  summary.approvals = await verifyArrayEndpoint(token, '/api/approvals', 'Approvals')
  summary.auditLogs = await verifyArrayEndpoint(token, '/api/admin/audits?limit=5', 'Audit logs')
  summary.outputGuardRules = await verifyArrayEndpoint(token, '/api/output-guard/rules', 'Output guard rules')
  summary.outputGuardAudits = await verifyArrayEndpoint(token, '/api/output-guard/rules/audits?limit=5', 'Output guard audits')

  console.log(JSON.stringify(summary, null, 2))
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error))
  process.exit(1)
})

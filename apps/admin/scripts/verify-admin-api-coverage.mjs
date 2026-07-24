#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'

const HTTP_METHODS = new Set(['get', 'post', 'put', 'delete', 'patch'])

function normalizePath(raw) {
  let value = raw.replace(/\?.*$/, '')
  const apiIndex = value.indexOf('/api/')
  const v1Index = value.indexOf('/v1/')
  const firstApiIndex = [apiIndex, v1Index].filter((index) => index >= 0).sort((a, b) => a - b)[0]
  if (firstApiIndex > 0) value = value.slice(firstApiIndex)
  value = value.replace(/\$\{[^}]+\}/g, '{var}')
  value = value.replace(/\{[^}]+\}/g, '{var}')
  value = value.replace(/\/+/g, '/')
  if (value.length > 1 && value.endsWith('/')) value = value.slice(0, -1)
  return value || '/'
}

function uniqueSorted(list) {
  return [...new Set(list)].sort()
}

function walkFiles(dir, predicate) {
  if (!fs.existsSync(dir)) return []
  const entries = fs.readdirSync(dir, { withFileTypes: true })
  return entries.flatMap((entry) => {
    const fullPath = path.join(dir, entry.name)
    if (entry.isDirectory()) return walkFiles(fullPath, predicate)
    return predicate(fullPath) ? [fullPath] : []
  })
}

function parseRouterPrefixes(source) {
  const prefixes = new Map()
  const routerRegex = /(?:^|\n)\s*(\w+)\s*=\s*APIRouter\(([^)]*)\)/g
  let match
  while ((match = routerRegex.exec(source)) !== null) {
    const [, name, args] = match
    const prefixMatch = args.match(/prefix\s*=\s*["'`]([^"'`]+)["'`]/)
    prefixes.set(name, prefixMatch ? normalizePath(prefixMatch[1]) : '')
  }
  return prefixes
}

function parseFastApiRoutes(filePath) {
  const source = fs.readFileSync(filePath, 'utf8')
  const prefixes = parseRouterPrefixes(source)
  const routes = []
  const decoratorRegex = /@(\w+)\.(get|post|put|delete|patch)\(\s*["'`]([^"'`]+)["'`]/g
  let match
  while ((match = decoratorRegex.exec(source)) !== null) {
    const [, routerName, method, routePath] = match
    if (!HTTP_METHODS.has(method)) continue
    const prefix = prefixes.get(routerName) ?? ''
    const fullPath = routePath.startsWith('/')
      ? `${prefix}${routePath}`
      : `${prefix}/${routePath}`
    routes.push(`${method.toUpperCase()} ${normalizePath(fullPath)}`)
  }
  return routes
}

function parseBackendEndpoints(backendRoot) {
  const routersDir = path.join(backendRoot, 'src/reactor/api/routers')
  const routerFiles = walkFiles(routersDir, (filePath) => filePath.endsWith('.py'))
  return uniqueSorted(
    routerFiles
      .flatMap(parseFastApiRoutes)
      .filter((endpoint) => endpoint.includes(' /api/') || endpoint.includes(' /v1/')),
  )
}

function readEndpointInventory(repoRoot) {
  const inventoryPath = process.env.REACTOR_API_INVENTORY
    ? path.resolve(process.env.REACTOR_API_INVENTORY)
    : path.join(repoRoot, 'scripts/fixtures/reactor-api-endpoints.json')
  if (!fs.existsSync(inventoryPath)) return null
  const parsed = JSON.parse(fs.readFileSync(inventoryPath, 'utf8'))
  if (!Array.isArray(parsed.endpoints)) {
    throw new Error(`Invalid Reactor API inventory: ${inventoryPath}`)
  }
  return {
    inventoryPath,
    endpoints: uniqueSorted(parsed.endpoints.map(String)),
  }
}

function parseFrontendApiCalls(repoRoot) {
  const featureFiles = walkFiles(path.join(repoRoot, 'src/features'), (filePath) => filePath.endsWith('/api.ts'))
  const sharedFiles = [path.join(repoRoot, 'src/shared/api/client.ts')]
  const endpoints = []

  for (const filePath of [...featureFiles, ...sharedFiles]) {
    if (!fs.existsSync(filePath)) continue
    const source = fs.readFileSync(filePath, 'utf8')
    const kyRegex = /\bapi\.(get|post|put|delete|patch)\(\s*[`']([^`']+)[`']/g
    let match
    while ((match = kyRegex.exec(source)) !== null) {
      const [, method, rawPath] = match
      const fullPath = rawPath.startsWith('/api/') || rawPath.startsWith('/v1/')
        ? rawPath
        : `/api/${rawPath}`
      endpoints.push(`${method.toUpperCase()} ${normalizePath(fullPath)}`)
    }

    const fetchRegex = /fetchWithAuth\(\s*([`'])(.*?)\1\s*(?:,\s*\{([\s\S]*?)\}\s*)?\)/g
    while ((match = fetchRegex.exec(source)) !== null) {
      const rawPath = match[2]
      if (!rawPath.includes('/api/')) continue
      const methodMatch = match[3]?.match(/\bmethod\s*:\s*["'`](get|post|put|delete|patch)["'`]/i)
      const method = methodMatch?.[1]?.toUpperCase() ?? 'GET'
      endpoints.push(`${method} ${normalizePath(rawPath)}`)
    }
  }

  return uniqueSorted(endpoints)
}

function parseRouteRequirements(repoRoot) {
  const requirementsPath = path.join(repoRoot, 'src/features/capabilities/requirements.ts')
  if (!fs.existsSync(requirementsPath)) return []
  const source = fs.readFileSync(requirementsPath, 'utf8')
  const endpoints = []
  const regex = /openApiPath:\s*["'`]([^"'`]+)["'`]/g
  let match
  while ((match = regex.exec(source)) !== null) {
    const routePath = normalizePath(match[1])
    endpoints.push(`GET ${routePath}`)
  }
  return uniqueSorted(endpoints)
}

function main() {
  const repoRoot = process.cwd()
  const backendRoot = process.env.REACTOR_PATH
    ? path.resolve(process.env.REACTOR_PATH)
    : path.resolve(repoRoot, '../..')
  const strict = process.env.ADMIN_API_STRICT === '1'

  const routersDir = path.join(backendRoot, 'src/reactor/api/routers')
  const inventory = fs.existsSync(routersDir) ? null : readEndpointInventory(repoRoot)
  if (!fs.existsSync(routersDir) && !inventory) {
    console.error(`Missing Reactor Python API routers directory: ${routersDir}`)
    process.exit(2)
  }

  const backendEndpoints = inventory?.endpoints ?? parseBackendEndpoints(backendRoot)
  const frontendEndpoints = parseFrontendApiCalls(repoRoot)
  const routeRequirements = parseRouteRequirements(repoRoot)
  const pendingBackendPaths = new Set()

  if (backendEndpoints.length === 0) {
    console.error('No FastAPI endpoints found in Reactor backend inventory.')
    process.exit(2)
  }

  const backendEndpointSet = new Set(backendEndpoints)
  const backendPaths = new Set(
    backendEndpoints.map((endpoint) => endpoint.replace(/^[A-Z]+ /, '')),
  )
  const frontendPathGaps = frontendEndpoints.filter((endpoint) =>
    !backendEndpointSet.has(endpoint)
      && !pendingBackendPaths.has(endpoint.replace(/^[A-Z]+ /, '')),
  )
  const pendingFrontendPaths = frontendEndpoints.filter((endpoint) =>
    pendingBackendPaths.has(endpoint.replace(/^[A-Z]+ /, ''))
      && !backendPaths.has(endpoint.replace(/^[A-Z]+ /, '')),
  )
  const requirementPathGaps = routeRequirements.filter((endpoint) => {
    const endpointPath = endpoint.replace(/^[A-Z]+ /, '')
    return !backendPaths.has(endpointPath) && !pendingBackendPaths.has(endpointPath)
  })

  const summary = {
    backendRoot: inventory ? null : backendRoot,
    backendInventory: inventory?.inventoryPath ?? null,
    backendApiEndpoints: backendEndpoints.length,
    frontendApiCalls: frontendEndpoints.length,
    routeRequirements: routeRequirements.length,
    frontendPathGaps: frontendPathGaps.length,
    pendingFrontendPaths: pendingFrontendPaths.length,
    requirementPathGaps: requirementPathGaps.length,
    mode: strict ? 'strict' : 'inventory',
  }

  console.log(JSON.stringify(summary, null, 2))

  if (frontendPathGaps.length > 0) {
    console.error('\nFrontend API method/path pairs not present in Reactor FastAPI inventory:')
    frontendPathGaps.slice(0, 80).forEach((endpoint) => console.error(`- ${endpoint}`))
    if (frontendPathGaps.length > 80) {
      console.error(`... and ${frontendPathGaps.length - 80} more`)
    }
  }

  if (requirementPathGaps.length > 0) {
    console.error('\nRoute requirements not present in Reactor FastAPI inventory:')
    requirementPathGaps.slice(0, 80).forEach((endpoint) => console.error(`- ${endpoint}`))
    if (requirementPathGaps.length > 80) {
      console.error(`... and ${requirementPathGaps.length - 80} more`)
    }
  }

  if (strict && (frontendPathGaps.length > 0 || requirementPathGaps.length > 0)) {
    process.exit(1)
  }
}

main()

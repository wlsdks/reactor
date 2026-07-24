/**
 * Facade for API functions used across multiple features.
 *
 * Dashboard and Integrations both need MCP-server, capability, and
 * project-connection helpers. Re-exporting them here prevents direct
 * cross-feature imports and keeps each feature module isolated.
 */

// ── MCP server APIs ─────────────────────────────────────────────────────────
export { listMcpServers, getMcpPreflight, listSwaggerSpecSources } from '../../features/mcp-servers/api'

// ── Capability manifest ─────────────────────────────────────────────────────
export { getCapabilityManifest } from '../../features/capabilities/api'

// ── Project connection helpers / types ───────────────────────────────────────
export {
  findKnownProjectServer,
  summarizeReactorConnection,
  summarizeKnownProjectConnection,
  summarizeMcpProjectConnection,
  type ReactorConnectionSnapshot,
  type McpProjectConnectionSnapshot,
} from '../../features/integrations/projectConnections'

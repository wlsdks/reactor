import type { McpServerDetailResponse } from '../types'
import { localizeMcpRuntimeStatus, localizeMcpTransport } from '../mcpDisplay'

// ── Component ───────────────────────────────────────────────────────────────

interface McpServerOverviewSectionProps {
  server: McpServerDetailResponse
  t: (key: string) => string
}

export function McpServerOverviewSection({ server, t }: McpServerOverviewSectionProps) {
  return (
    <div className="mcp-detail-card">
      <h4 className="mcp-detail-card-title">{t('mcpServers.detail.overview')}</h4>
      <div className="mcp-detail-kv-grid">
        <div className="mcp-detail-kv-item">
          <span className="mcp-detail-kv-label">{t('mcpServers.detail.transport')}</span>
          <span className="mcp-detail-kv-value">
            {localizeMcpTransport(server.transportType, t)}
          </span>
        </div>
        <div className="mcp-detail-kv-item">
          <span className="mcp-detail-kv-label">{t('mcpServers.detail.backendState')}</span>
          <span className="mcp-detail-kv-value">{localizeMcpRuntimeStatus(server.backendStatus, t)}</span>
        </div>
        <div className="mcp-detail-kv-item">
          <span className="mcp-detail-kv-label">{t('mcpServers.detail.protocolVersion')}</span>
          <span className="mcp-detail-kv-value mono">{server.protocolVersion ?? '-'}</span>
        </div>
      </div>
      <details className="mcp-technical-details">
        <summary>{t('mcpServers.detail.technicalDetails')}</summary>
        <dl>
          <div><dt>{t('mcpServers.detail.serverId')}</dt><dd>{server.id}</dd></div>
          <div><dt>{t('mcpServers.detail.tenantId')}</dt><dd>{server.tenantId ?? '-'}</dd></div>
          <div><dt>{t('mcpServers.detail.toolSnapshot')}</dt><dd>{server.toolSnapshotHash ?? '-'}</dd></div>
        </dl>
      </details>
    </div>
  )
}

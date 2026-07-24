import {
  ToggleSwitch,
  LoadingSpinner,
} from '../../../shared/ui'
import type { McpServerDetailResponse } from '../types'
import {
  displayMcpServerDescription,
  displayMcpServerName,
  localizeMcpConnectionStatus,
} from '../mcpDisplay'

// ── Component ───────────────────────────────────────────────────────────────

interface McpServerHeaderProps {
  server: McpServerDetailResponse
  name: string
  serverTags: string[]
  isAllowed: boolean
  isConnected: boolean
  hasSecurityPolicy: boolean
  toggleAllowedMutation: {
    mutate: (vars: { serverName: string; allowed: boolean }) => void
    isPending: boolean
  }
  toggleInFlightRef: { current: boolean }
  connectMutation: { mutate: (name: string) => void; isPending: boolean }
  disconnectMutation: { mutate: (name: string) => void; isPending: boolean }
  onEdit: () => void
  onDelete: () => void
  t: (key: string) => string
}

export function McpServerHeader({
  server,
  name,
  serverTags,
  isAllowed,
  isConnected,
  hasSecurityPolicy,
  toggleAllowedMutation,
  toggleInFlightRef,
  connectMutation,
  disconnectMutation,
  onEdit,
  onDelete,
  t,
}: McpServerHeaderProps) {
  return (
    <div className="mcp-detail-header">
      <div className="mcp-detail-header-left">
        <div className="mcp-detail-header-title">
          <h1>{displayMcpServerName(server.name)}</h1>
          <span className={`mcp-detail-state mcp-detail-state--${server.status.toLowerCase()}`}>
            <span aria-hidden="true" />
            {localizeMcpConnectionStatus(server.status, t)}
          </span>
          <span onClick={(e) => e.stopPropagation()}>
            <ToggleSwitch
              checked={isAllowed}
              onChange={(checked) => {
                if (toggleInFlightRef.current) return
                toggleAllowedMutation.mutate({ serverName: name, allowed: checked })
              }}
              disabled={toggleAllowedMutation.isPending || !hasSecurityPolicy}
              label={isAllowed ? t('mcpServers.detail.allowed') : t('mcpServers.detail.denied')}
            />
          </span>
        </div>
        {server.description && (
          <p className="mcp-detail-desc">{displayMcpServerDescription(server.name, server.description)}</p>
        )}
        {serverTags.length > 0 && (
          <p className="mcp-detail-tags">{serverTags.join(', ')}</p>
        )}
      </div>

      <div className="mcp-detail-header-actions">
        {isConnected ? (
          <button
            className="btn btn-secondary"
            disabled={disconnectMutation.isPending}
            onClick={() => disconnectMutation.mutate(name)}
          >
            {disconnectMutation.isPending ? <LoadingSpinner size="sm" /> : t('mcpServers.disconnect')}
          </button>
        ) : (
          <button
            className="btn btn-primary"
            disabled={connectMutation.isPending}
            onClick={() => connectMutation.mutate(name)}
          >
            {connectMutation.isPending ? <LoadingSpinner size="sm" /> : t('mcpServers.connect')}
          </button>
        )}
        <button
          className="btn btn-secondary"
          onClick={onEdit}
        >
          {t('mcpServers.detail.edit')}
        </button>
        <button
          className="btn btn-danger"
          onClick={onDelete}
        >
          {t('mcpServers.detail.delete')}
        </button>
      </div>
    </div>
  )
}

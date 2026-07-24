import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { ArrowLeft } from 'lucide-react'
import {
  ConfirmDialog,
  DetailSkeleton,
  LoadingSpinner,
  WorkspaceUnavailable,
} from '../../../shared/ui'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import type { McpServerDetailResponse, McpAccessPolicy, McpPreflightResponse } from '../types'
import { useMcpServerDetail } from '../useMcpServerDetail'
import { McpServerHeader } from './McpServerHeader'
import { McpServerOverviewSection } from './McpServerOverviewSection'
import { McpServerToolsList } from './McpServerToolsList'
import { McpServerSwaggerSection } from './McpServerSwaggerSection'
import { RegisterServerModal } from './RegisterServerModal'
import './McpServerDetailView.css'

// ── Sensitive key detection ─────────────────────────────────────────────────

const SENSITIVE_KEY_PATTERN = /token|secret|key|password/i

function maskConfigValue(
  config: Record<string, unknown>,
  showSensitive: boolean,
): Record<string, unknown> {
  const masked: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(config)) {
    if (!showSensitive && SENSITIVE_KEY_PATTERN.test(key) && typeof value === 'string') {
      masked[key] = '••••••••'
    } else {
      masked[key] = value
    }
  }
  return masked
}

const CONFIG_LABELS: Record<string, string> = {
  adminUrl: '관리 주소',
  adminToken: '관리 인증 정보',
  adminHmacRequired: '요청 서명 사용',
  adminHmacSecret: '요청 서명 인증 정보',
  adminTimeoutMs: '관리 요청 제한 시간',
  adminConnectTimeoutMs: '관리 연결 제한 시간',
  args: '실행 옵션',
}

function humanizeConfigKey(key: string): string {
  return CONFIG_LABELS[key]
    ?? key.replace(/_/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/^./, (letter) => letter.toUpperCase())
}

function displayConfigValue(value: unknown): string {
  if (typeof value === 'boolean') return value ? '사용' : '사용 안 함'
  if (Array.isArray(value)) return value.length > 0 ? value.map(String).join(', ') : '-'
  if (value == null || value === '') return '-'
  if (typeof value === 'object') return Object.entries(value as Record<string, unknown>)
    .map(([key, item]) => `${humanizeConfigKey(key)}: ${displayConfigValue(item)}`)
    .join(', ')
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'bigint') return String(value)
  return '-'
}

function optionalText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function connectionTarget(server: McpServerDetailResponse): string | null {
  return server.url
    ?? server.command
    ?? optionalText(server.config.url)
    ?? optionalText(server.config.command)
}

function describeConnectionTarget(target: string | null, t: TFunction): string {
  if (!target) return t('mcpServers.detail.connectionTargetUnknown')
  if (!/^https?:\/\//i.test(target)) return t('mcpServers.detail.connectionTargetLocalProcess')

  try {
    const { hostname } = new URL(target)
    return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1'
      ? t('mcpServers.detail.connectionTargetLocal')
      : t('mcpServers.detail.connectionTargetExternal')
  } catch {
    return t('mcpServers.detail.connectionTargetUnknown')
  }
}

// ── Component ───────────────────────────────────────────────────────────────

export function McpServerDetailView() {
  const { t } = useTranslation()
  const [editModalOpen, setEditModalOpen] = useState(false)

  const {
    name,
    server,
    serverLoading,
    serverError,
    serverFetching,
    refetchServer,
    securityPolicy,
    isAllowed,
    accessPolicy,
    hasAccessPolicy,
    preflightData,
    preflightFetching,
    refetchPreflight,
    hasPreflight,
    swaggerSources,
    hasSwagger,
    serverTags,
    connectMutation,
    disconnectMutation,
    startUndoableDelete,
    toggleAllowedMutation,
    toggleInFlightRef,
    isConnected,
    showSensitive,
    setShowSensitive,
    toolFilter,
    setToolFilter,
    filteredTools,
    showDeleteConfirm,
    setShowDeleteConfirm,
    navigate,
  } = useMcpServerDetail()

  // ── Render: Loading / Error states ────────────────────────────────────

  if (serverLoading) {
    return (
      <div className="page">
        <button className="mcp-detail-back" onClick={() => void navigate('/mcp-servers')}>
          <ArrowLeft size={16} aria-hidden="true" /> {t('mcpServers.detail.backToList')}
        </button>
        <DetailSkeleton />
      </div>
    )
  }

  if (serverError || !server) {
    return (
      <div className="page">
        <button className="mcp-detail-back" onClick={() => void navigate('/mcp-servers')}>
          <ArrowLeft size={16} aria-hidden="true" /> {t('mcpServers.detail.backToList')}
        </button>
        <WorkspaceUnavailable
          title={t('mcpServers.detail.loadErrorTitle')}
          description={t('mcpServers.detail.loadErrorDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.loading')}
          onRetry={() => void refetchServer()}
          isRetrying={serverFetching}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{
            title: t('mcpServers.list.recoveryTitle'),
            steps: [t('mcpServers.list.recoveryConnection')],
            technicalLabel: t('common.technicalDetails'),
            technicalDetail: serverError ? getErrorMessage(serverError) : null,
          }}
        />
      </div>
    )
  }

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div className="page">
      {/* Back link */}
      <button className="mcp-detail-back" onClick={() => void navigate('/mcp-servers')}>
        <ArrowLeft size={16} aria-hidden="true" /> {t('mcpServers.detail.backToList')}
      </button>

      {/* Header */}
      <McpServerHeader
        server={server}
        name={name}
        serverTags={serverTags}
        isAllowed={isAllowed}
        isConnected={isConnected}
        hasSecurityPolicy={!!securityPolicy}
        toggleAllowedMutation={toggleAllowedMutation}
        toggleInFlightRef={toggleInFlightRef}
        connectMutation={connectMutation}
        disconnectMutation={disconnectMutation}
        onEdit={() => setEditModalOpen(true)}
        onDelete={() => setShowDeleteConfirm(true)}
        t={t}
      />

      {server.lastConnectionError && (
        <section className="mcp-runtime-notice" role="note" aria-labelledby="mcp-runtime-notice-title">
          <h2 id="mcp-runtime-notice-title">{t('mcpServers.detail.lastConnectionError')}</h2>
          <p>{t('mcpServers.detail.lastConnectionErrorDescription')}</p>
          <details className="mcp-runtime-notice__technical">
            <summary>{t('common.technicalDetails')}</summary>
            <code>{server.lastConnectionError}</code>
          </details>
        </section>
      )}

      {/* Two-column layout */}
      <div className="mcp-detail-columns">
        {/* Left column */}
        <div className="mcp-detail-col">
          <McpServerOverviewSection server={server} t={t} />
          <ConfigurationCard
            server={server}
            showSensitive={showSensitive}
            onToggleSensitive={() => setShowSensitive(!showSensitive)}
            t={t}
          />
          {hasAccessPolicy && accessPolicy && (
            <AccessPolicyCard policy={accessPolicy} t={t} />
          )}
        </div>

        {/* Right column */}
        <div className="mcp-detail-col">
          {server.tools.length > 0 ? (
            <McpServerToolsList
              tools={filteredTools}
              totalCount={server.tools.length}
              filter={toolFilter}
              onFilterChange={setToolFilter}
              t={t}
            />
          ) : null}
          {hasSwagger && (
            <McpServerSwaggerSection sources={swaggerSources} t={t} />
          )}
          {hasPreflight && (
            <PreflightCard
              data={preflightData ?? undefined}
              isFetching={preflightFetching}
              onRunCheck={() => void refetchPreflight()}
              t={t}
            />
          )}
        </div>
      </div>

      {/* Delete confirm dialog */}
      {showDeleteConfirm && (
        <ConfirmDialog
          title={t('mcpServers.deleteTitle')}
          message={t('mcpServers.confirm.delete')}
          danger
          onConfirm={() => {
            setShowDeleteConfirm(false)
            startUndoableDelete()
          }}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      )}

      {/* Edit modal — reuses the register modal in edit mode.
       * Only mount when open so the editServer prop identity is created
       * lazily and the modal's wizard step state initializes correctly. */}
      {editModalOpen && (
        <RegisterServerModal
          open={editModalOpen}
          onClose={() => setEditModalOpen(false)}
          editServer={{
            name: server.name,
            transportType: server.transportType,
            config: server.config,
          }}
        />
      )}
    </div>
  )
}

// ── Sub-components (kept inline) ──────────────────────────────────────────

interface ConfigurationCardProps {
  server: McpServerDetailResponse
  showSensitive: boolean
  onToggleSensitive: () => void
  t: TFunction
}

function ConfigurationCard({ server, showSensitive, onToggleSensitive, t }: ConfigurationCardProps) {
  const masked = maskConfigValue(server.config, showSensitive)
  const hasSensitive = Object.keys(server.config).some((key) => SENSITIVE_KEY_PATTERN.test(key))
  const target = connectionTarget(server)
  const additionalConfig = Object.entries(masked)
    .filter(([key]) => !['url', 'command', 'authType', 'timeoutMs'].includes(key))

  return (
    <div className="mcp-detail-card">
      <h4 className="mcp-detail-card-title">{t('mcpServers.detail.configuration')}</h4>
      <dl className="mcp-config-list">
        <div><dt>{t('mcpServers.detail.target')}</dt><dd>{describeConnectionTarget(target, t)}</dd></div>
        <div><dt>{t('mcpServers.detail.authentication')}</dt><dd>{(server.authType ?? optionalText(server.config.authType) ?? 'none') === 'none' ? t('mcpServers.detail.noAuthentication') : (server.authType ?? optionalText(server.config.authType))}</dd></div>
        <div><dt>{t('mcpServers.detail.timeout')}</dt><dd>{t('mcpServers.detail.timeoutSeconds', { count: (server.timeoutMs ?? 15_000) / 1000 })}</dd></div>
      </dl>
      {(target || additionalConfig.length > 0) ? (
        <details className="mcp-technical-details">
          <summary>{t('mcpServers.detail.configurationTechnical')}</summary>
          {hasSensitive ? (
            <button className="mcp-config-mask-btn" onClick={onToggleSensitive}>
              {showSensitive ? t('mcpServers.detail.hideConfig') : t('mcpServers.detail.showConfig')}
            </button>
          ) : null}
          <dl>
            {target && <div><dt>{t('mcpServers.detail.connectionAddress')}</dt><dd>{target}</dd></div>}
            {additionalConfig.map(([key, value]) => (
              <div key={key}><dt>{humanizeConfigKey(key)}</dt><dd>{displayConfigValue(value)}</dd></div>
            ))}
          </dl>
        </details>
      ) : null}
    </div>
  )
}

interface AccessPolicyCardProps {
  policy: McpAccessPolicy
  t: TFunction
}

function AccessPolicyCard({ policy, t }: AccessPolicyCardProps) {
  return (
    <div className="mcp-detail-card">
      <h4 className="mcp-detail-card-title">{t('mcpServers.detail.accessPolicy')}</h4>
      <div className="mcp-policy-summary">
        <div className="mcp-policy-row">
          <span className="mcp-policy-label">{t('mcpServers.allowedJiraProjectKeys')}</span>
          <span className="mcp-policy-value">{policy.allowedJiraProjectKeys.length}</span>
        </div>
        <div className="mcp-policy-row">
          <span className="mcp-policy-label">{t('mcpServers.allowedConfluenceSpaceKeys')}</span>
          <span className="mcp-policy-value">{policy.allowedConfluenceSpaceKeys.length}</span>
        </div>
        <div className="mcp-policy-row">
          <span className="mcp-policy-label">{t('mcpServers.allowedBitbucketRepositories')}</span>
          <span className="mcp-policy-value">{policy.allowedBitbucketRepositories.length}</span>
        </div>
        <div className="mcp-policy-row">
          <span className="mcp-policy-label">{t('mcpServers.allowPreviewReads')}</span>
          <span className="mcp-policy-value">
            {policy.allowPreviewReads
              ? t('mcpServers.detail.enabled')
              : t('mcpServers.detail.disabled')}
          </span>
        </div>
        <div className="mcp-policy-row">
          <span className="mcp-policy-label">{t('mcpServers.allowPreviewWrites')}</span>
          <span className="mcp-policy-value">
            {policy.allowPreviewWrites
              ? t('mcpServers.detail.enabled')
              : t('mcpServers.detail.disabled')}
          </span>
        </div>
      </div>
    </div>
  )
}

interface PreflightCardProps {
  data: McpPreflightResponse | undefined
  isFetching: boolean
  onRunCheck: () => void
  t: TFunction
}

function PreflightCard({ data, isFetching, onRunCheck, t }: PreflightCardProps) {
  return (
    <div className="mcp-detail-card">
      <div className="mcp-detail-card-heading">
        <h4 className="mcp-detail-card-title">{t('mcpServers.detail.preflightCheck')}</h4>
      </div>
      <button
        className="btn btn-secondary"
        disabled={isFetching}
        onClick={onRunCheck}
      >
        {isFetching ? <LoadingSpinner size="sm" /> : t('mcpServers.detail.runCheck')}
      </button>
      {data && (
        <div className="mcp-preflight-results">
          {data.checks.map((check, i) => {
            const statusClass = check.status === 'PASS'
              ? 'pass'
              : check.status === 'FAIL'
                ? 'fail'
                : 'warn'
            return (
              <div key={`${check.name}-${i}`} className="mcp-preflight-item">
                <span className={`mcp-preflight-status ${statusClass}`}>{t(`mcpServers.detail.checkStatus.${statusClass}`)}</span>
                <span className="mcp-preflight-name">{check.name}</span>
                <span className="mcp-preflight-message">{check.message}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

import type { SwaggerSpecSource } from '../types'

interface McpServerSwaggerSectionProps {
  sources: SwaggerSpecSource[] | undefined
  t: (key: string) => string
}

export function McpServerSwaggerSection({ sources, t }: McpServerSwaggerSectionProps) {
  return (
    <div className="mcp-detail-card">
      <h4 className="mcp-detail-card-title">{t('mcpServers.detail.swaggerSources')}</h4>
      {!sources || sources.length === 0 ? (
        <p className="mcp-swagger-placeholder">{t('mcpServers.swaggerSourcesEmpty')}</p>
      ) : (
        <div className="mcp-swagger-list">
          {sources.map((source) => (
            <div key={source.id} className="mcp-swagger-item">
              <div>
                <span className="mcp-swagger-item-name">{source.name}</span>
                <span className="mcp-swagger-item-state">
                  {source.enabled ? t('mcpServers.detail.enabled') : t('mcpServers.detail.disabled')}
                </span>
              </div>
              <span className="mcp-swagger-item-url">{source.url}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

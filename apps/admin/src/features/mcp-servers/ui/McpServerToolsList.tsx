interface McpServerToolsListProps {
  tools: string[]
  totalCount: number
  filter: string
  onFilterChange: (value: string) => void
  t: (key: string) => string
}

const TOOL_WORDS: Record<string, string> = {
  search: '검색',
  list: '목록',
  repos: '저장소',
  repositories: '저장소',
  work: '업무',
  context: '맥락',
  get: '조회',
  create: '생성',
  update: '수정',
  delete: '삭제',
}

function humanizeToolName(tool: string): string {
  return tool
    .split(/[._-]+/)
    .filter(Boolean)
    .map((word) => TOOL_WORDS[word.toLowerCase()] ?? (/^[a-z]+$/i.test(word) ? word.replace(/^./, (letter) => letter.toUpperCase()) : word))
    .join(' ')
}

export function McpServerToolsList({
  tools,
  totalCount,
  filter,
  onFilterChange,
  t,
}: McpServerToolsListProps) {
  return (
    <div className="mcp-detail-card">
      <h4 className="mcp-detail-card-title">
        {t('mcpServers.detail.tools')} ({totalCount})
      </h4>
      <input
        type="text"
        className="mcp-tools-filter"
        placeholder={t('mcpServers.detail.filterTools')}
        value={filter}
        onChange={(e) => onFilterChange(e.target.value)}
        aria-label={t('mcpServers.detail.filterTools')}
      />
      <div className="mcp-tools-list">
        {tools.map((tool) => (
          <div key={tool} className="mcp-tool-item">
            <span className="mcp-tool-name">{humanizeToolName(tool)}</span>
          </div>
        ))}
        {tools.length === 0 && totalCount > 0 && (
          <span style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>
            {t('mcpServers.detail.filterTools')}
          </span>
        )}
      </div>
    </div>
  )
}

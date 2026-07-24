const TOOL_LABELS: Record<string, string> = {
  web_search: '웹 검색',
  jira_create_issue: 'Jira 이슈 만들기',
  jira_issue_transition: 'Jira 이슈 상태 변경',
  jira_write: 'Jira 쓰기',
  jira_comment: 'Jira 댓글 작성',
  confluence_write: 'Confluence 문서 작성',
  confluence_update_page: 'Confluence 문서 수정',
  slack_post: 'Slack 메시지 보내기',
  'Slack:post_message': 'Slack 메시지 보내기',
  send_email: '이메일 보내기',
}

const WORD_LABELS: Record<string, string> = {
  confluence: 'Confluence',
  create: '만들기',
  email: '이메일',
  issue: '이슈',
  jira: 'Jira',
  message: '메시지',
  page: '문서',
  post: '보내기',
  search: '검색',
  slack: 'Slack',
  update: '수정',
  web: '웹',
  write: '작성',
}

/** Human label for a model-facing tool while preserving the raw ID elsewhere. */
export function humanizeToolName(toolName: string): string {
  const trimmed = toolName.trim()
  if (!trimmed) return '이름을 확인할 수 없는 작업'
  const known = TOOL_LABELS[trimmed]
  if (known) return known

  const words = trimmed
    .split(/[:_-]+/)
    .filter(Boolean)
  const labels = words.map((word) => WORD_LABELS[word.toLowerCase()])

  return labels.length > 0 && labels.every(Boolean)
    ? labels.join(' ')
    : '확인할 수 없는 외부 도구'
}

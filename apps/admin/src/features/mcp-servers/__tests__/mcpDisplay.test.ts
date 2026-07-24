import { describe, expect, it } from 'vitest'
import { displayMcpServerDescription, displayMcpServerName } from '../mcpDisplay'

describe('displayMcpServerName', () => {
  it('turns known backend identifiers into operator-facing connection names', () => {
    expect(displayMcpServerName('atlassian')).toBe('Atlassian')
    expect(displayMcpServerName('swagger')).toBe('API 문서 도구')
    expect(displayMcpServerName('internal-docs')).toBe('내부 문서 도구')
  })

  it('keeps custom connection names readable without exposing snake case', () => {
    expect(displayMcpServerName('research_api')).toBe('Research API')
  })
})

describe('displayMcpServerDescription', () => {
  it('replaces built-in technical descriptions with an operator-facing explanation', () => {
    expect(displayMcpServerDescription('atlassian', 'Atlassian MCP server for Jira')).toBe(
      'Jira, Confluence, Bitbucket 업무 도구를 연결합니다.',
    )
    expect(displayMcpServerDescription('swagger', 'Swagger MCP server')).toBe(
      'API 문서를 연결해 필요한 정보를 찾고 확인합니다.',
    )
  })

  it('keeps a custom description supplied by an operator', () => {
    expect(displayMcpServerDescription('atlassian', '고객 지원팀 전용 연결')).toBe(
      '고객 지원팀 전용 연결',
    )
  })
})

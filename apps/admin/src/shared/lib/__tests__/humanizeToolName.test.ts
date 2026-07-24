import { describe, expect, it } from 'vitest'
import { humanizeToolName } from '../humanizeToolName'

describe('humanizeToolName', () => {
  it('localizes known operator-facing tool IDs', () => {
    expect(humanizeToolName('web_search')).toBe('웹 검색')
    expect(humanizeToolName('jira_create_issue')).toBe('Jira 이슈 만들기')
    expect(humanizeToolName('Slack:post_message')).toBe('Slack 메시지 보내기')
  })

  it('uses a safe Korean fallback for unknown tool IDs', () => {
    expect(humanizeToolName('custom_write_action')).toBe('확인할 수 없는 외부 도구')
  })
})

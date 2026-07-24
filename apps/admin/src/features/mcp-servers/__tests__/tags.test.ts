import { describe, it, expect, beforeEach } from 'vitest'
import { useTagStore } from '../tags'

describe('useTagStore', () => {
  beforeEach(() => {
    localStorage.clear()
    useTagStore.setState({ tags: {} })
  })

  it('setTags stores tags for a server and persists to localStorage', () => {
    useTagStore.getState().setTags('atlassian-prod', ['env:prod', 'type:atlassian'])
    expect(useTagStore.getState().tags['atlassian-prod']).toEqual(['env:prod', 'type:atlassian'])
    const stored = JSON.parse(localStorage.getItem('mcp-server-tags') ?? '{}')
    expect(stored['atlassian-prod']).toEqual(['env:prod', 'type:atlassian'])
  })

  it('removeTags deletes tags for a server', () => {
    useTagStore.getState().setTags('server-a', ['env:dev'])
    useTagStore.getState().removeTags('server-a')
    expect(useTagStore.getState().tags['server-a']).toBeUndefined()
  })

  it('getAllUniqueTags aggregates all unique tags across servers', () => {
    useTagStore.getState().setTags('a', ['env:prod', 'team:fe'])
    useTagStore.getState().setTags('b', ['env:prod', 'team:be'])
    expect(useTagStore.getState().getAllUniqueTags()).toEqual(
      expect.arrayContaining(['env:prod', 'team:fe', 'team:be'])
    )
  })

  it('getTagColor returns correct color for known keys', () => {
    const { getTagColor } = useTagStore.getState()
    expect(getTagColor('env:prod')).toBe('#8CB8FF')
    expect(getTagColor('team:fe')).toBe('#5EBA8D')
    expect(getTagColor('type:atlassian')).toBe('#D6A451')
    expect(getTagColor('custom:foo')).toBe('#94A3B8')
  })

  it('initializes from localStorage on creation', () => {
    localStorage.setItem('mcp-server-tags', JSON.stringify({ 'x': ['env:staging'] }))
    useTagStore.setState({ tags: JSON.parse(localStorage.getItem('mcp-server-tags') ?? '{}') })
    expect(useTagStore.getState().tags['x']).toEqual(['env:staging'])
  })
})

import { describe, it, expect, beforeEach } from 'vitest'
import { useSavedViewsStore, SAVED_VIEWS_STORAGE_KEY } from '../savedViews.store'

function reset() {
  // Clear persisted bucket and in-memory state between tests so behaviour
  // does not leak across cases.
  localStorage.removeItem(SAVED_VIEWS_STORAGE_KEY)
  useSavedViewsStore.setState({ views: [] })
}

describe('savedViews.store', () => {
  beforeEach(() => {
    reset()
  })

  it('starts with an empty views array', () => {
    expect(useSavedViewsStore.getState().views).toEqual([])
    expect(useSavedViewsStore.getState().list('audit')).toEqual([])
  })

  it('adds a view scoped to the requested scope and returns it', () => {
    const view = useSavedViewsStore.getState().add('audit', 'High risk', { audit_p: '2', audit_s: 'category' })
    expect(view.id).toBeTruthy()
    expect(view.scope).toBe('audit')
    expect(view.name).toBe('High risk')
    expect(view.params).toEqual({ audit_p: '2', audit_s: 'category' })
    expect(view.createdAt).toMatch(/^\d{4}-\d{2}-\d{2}T/)
    expect(useSavedViewsStore.getState().views).toHaveLength(1)
  })

  it('list() filters by scope and ignores other scopes', () => {
    const { add } = useSavedViewsStore.getState()
    add('audit', 'A', { audit_p: '1' })
    add('feedback', 'B', { feedback_p: '3' })
    add('audit', 'C', { audit_s: 'category' })

    expect(useSavedViewsStore.getState().list('audit').map((v) => v.name)).toEqual(['A', 'C'])
    expect(useSavedViewsStore.getState().list('feedback').map((v) => v.name)).toEqual(['B'])
    expect(useSavedViewsStore.getState().list('does-not-exist')).toEqual([])
  })

  it('remove() drops the matching view by id without touching others', () => {
    const { add, remove } = useSavedViewsStore.getState()
    const a = add('audit', 'A', {})
    const b = add('audit', 'B', {})
    remove(a.id)
    expect(useSavedViewsStore.getState().views.map((v) => v.id)).toEqual([b.id])
  })

  it('remove() is a no-op when the id is unknown', () => {
    useSavedViewsStore.getState().add('audit', 'A', {})
    useSavedViewsStore.getState().remove('does-not-exist')
    expect(useSavedViewsStore.getState().views).toHaveLength(1)
  })

  it('rename() updates the name and trims whitespace', () => {
    const view = useSavedViewsStore.getState().add('audit', 'A', {})
    useSavedViewsStore.getState().rename(view.id, '  Renamed  ')
    const updated = useSavedViewsStore.getState().views.find((v) => v.id === view.id)
    expect(updated?.name).toBe('Renamed')
  })

  it('rename() ignores empty names so the row never becomes blank', () => {
    const view = useSavedViewsStore.getState().add('audit', 'A', {})
    useSavedViewsStore.getState().rename(view.id, '   ')
    const updated = useSavedViewsStore.getState().views.find((v) => v.id === view.id)
    expect(updated?.name).toBe('A')
  })

  it('add() defensively copies params so external mutation cannot leak in', () => {
    const params = { audit_p: '1' }
    const view = useSavedViewsStore.getState().add('audit', 'A', params)
    params.audit_p = '99'
    expect(view.params).toEqual({ audit_p: '1' })
    expect(useSavedViewsStore.getState().views[0].params).toEqual({ audit_p: '1' })
  })

  it('persists views to localStorage under reactor-admin-saved-views', () => {
    useSavedViewsStore.getState().add('audit', 'High risk', { audit_p: '2' })
    const raw = localStorage.getItem(SAVED_VIEWS_STORAGE_KEY)
    expect(raw).toBeTruthy()
    const parsed = JSON.parse(raw as string)
    // zustand/persist wraps data under { state, version }
    expect(parsed.state.views).toHaveLength(1)
    expect(parsed.state.views[0].name).toBe('High risk')
    expect(parsed.state.views[0].params).toEqual({ audit_p: '2' })
  })

  it('rehydrates persisted views on demand', () => {
    // Seed storage as if a prior session had saved a view, then ask the store
    // to rehydrate so we can read it back.
    localStorage.setItem(
      SAVED_VIEWS_STORAGE_KEY,
      JSON.stringify({
        state: {
          views: [
            { id: 'fixture-1', scope: 'audit', name: 'Pre-loaded', params: { audit_s: 'action' }, createdAt: '2026-04-20T00:00:00.000Z' },
          ],
        },
        version: 1,
      }),
    )
    // Rehydrate — persist exposes this on the store API.
    void useSavedViewsStore.persist.rehydrate()
    expect(useSavedViewsStore.getState().views).toHaveLength(1)
    expect(useSavedViewsStore.getState().list('audit')[0]).toMatchObject({
      id: 'fixture-1',
      name: 'Pre-loaded',
    })
  })
})

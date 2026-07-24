import { describe, it, expect, beforeEach } from 'vitest'
import { useSidebarStore } from '../sidebar.store'

const STORAGE_KEY = 'reactor-admin-sidebar-collapsed'
const LEGACY_KEY = 'reactor-sidebar-collapsed'

describe('sidebar.store', () => {
  beforeEach(() => {
    useSidebarStore.setState({ collapsed: true })
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem(LEGACY_KEY)
  })

  it('defaults to collapsed', () => {
    expect(useSidebarStore.getState().collapsed).toBe(true)
  })

  it('toggles collapsed state', () => {
    useSidebarStore.getState().toggle()
    expect(useSidebarStore.getState().collapsed).toBe(false)
    useSidebarStore.getState().toggle()
    expect(useSidebarStore.getState().collapsed).toBe(true)
  })

  it('persists state to localStorage under reactor-admin-sidebar-collapsed', () => {
    useSidebarStore.getState().toggle()
    expect(localStorage.getItem(STORAGE_KEY)).toBe('false')
  })

  it('exposes open() to explicitly set collapsed=false', () => {
    useSidebarStore.getState().open()
    expect(useSidebarStore.getState().collapsed).toBe(false)
    expect(localStorage.getItem(STORAGE_KEY)).toBe('false')
  })

  it('close() explicitly sets collapsed=true', () => {
    useSidebarStore.setState({ collapsed: false })
    useSidebarStore.getState().close()
    expect(useSidebarStore.getState().collapsed).toBe(true)
    expect(localStorage.getItem(STORAGE_KEY)).toBe('true')
  })
})

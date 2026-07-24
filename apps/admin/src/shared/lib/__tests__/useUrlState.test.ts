import { describe, it, expect } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { createElement, type ReactNode } from 'react'
import { useUrlState } from '../useUrlState'

/**
 * Render a hook inside a memory router so `useSearchParams` resolves. We
 * surface the live router via `getLocation()` so assertions can look at the
 * URL after each setter call.
 */
function renderWithRouter<T>(
  hookFn: () => T,
  initialEntry = '/',
): {
  result: { current: T }
  getSearch: () => string
  rerender: () => void
} {
  let captured: T | undefined

  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: createElement(() => {
          captured = hookFn()
          return null
        }),
      },
    ],
    { initialEntries: [initialEntry] },
  )

  function Wrapper({ children }: { children?: ReactNode }) {
    return createElement(RouterProvider, { router }, children)
  }

  const view = renderHook(() => null, { wrapper: Wrapper })

  return {
    result: {
      get current() {
        return captured as T
      },
    },
    getSearch: () => router.state.location.search,
    rerender: () => view.rerender(),
  }
}

describe('useUrlState', () => {
  it('returns defaults when no params are present', () => {
    const { result } = renderWithRouter(() =>
      useUrlState({ page: 1, sort: 'name', dir: 'asc' as string }),
    )
    expect(result.current[0]).toEqual({ page: 1, sort: 'name', dir: 'asc' })
  })

  it('reads existing string params as strings', () => {
    const { result } = renderWithRouter(
      () => useUrlState({ q: '' as string }),
      '/?q=hello',
    )
    expect(result.current[0].q).toBe('hello')
  })

  it('coerces numeric defaults from string URL values', () => {
    const { result } = renderWithRouter(
      () => useUrlState({ page: 1 }),
      '/?page=7',
    )
    expect(result.current[0].page).toBe(7)
    expect(typeof result.current[0].page).toBe('number')
  })

  it('falls back to default when numeric param fails to parse', () => {
    const { result } = renderWithRouter(
      () => useUrlState({ page: 1 }),
      '/?page=abc',
    )
    expect(result.current[0].page).toBe(1)
  })

  it('writes updates to the URL via setSearchParams', () => {
    const { result, getSearch, rerender } = renderWithRouter(() =>
      useUrlState({ page: 1, q: '' as string }),
    )
    act(() => {
      result.current[1]({ page: 3 })
    })
    rerender()
    expect(getSearch()).toContain('page=3')
    expect(result.current[0].page).toBe(3)
  })

  it('removes the param when the new value matches its default', () => {
    const { result, getSearch, rerender } = renderWithRouter(
      () => useUrlState({ page: 1 }),
      '/?page=3',
    )
    expect(getSearch()).toBe('?page=3')
    act(() => {
      result.current[1]({ page: 1 })
    })
    rerender()
    expect(getSearch()).toBe('')
  })

  it('removes the param when set to undefined', () => {
    const { result, getSearch, rerender } = renderWithRouter(
      () => useUrlState({ q: '' as string }),
      '/?q=foo',
    )
    expect(getSearch()).toBe('?q=foo')
    act(() => {
      result.current[1]({ q: undefined })
    })
    rerender()
    expect(getSearch()).toBe('')
  })

  it('namespaces param keys when prefix is provided', () => {
    const { result, getSearch, rerender } = renderWithRouter(() =>
      useUrlState({ p: 1 }, { prefix: 'audit' }),
    )
    act(() => {
      result.current[1]({ p: 2 })
    })
    rerender()
    expect(getSearch()).toContain('audit_p=2')
  })

  it('reads namespaced params on initial render', () => {
    const { result } = renderWithRouter(
      () => useUrlState({ p: 1 }, { prefix: 'audit' }),
      '/?audit_p=4',
    )
    expect(result.current[0].p).toBe(4)
  })

  it('only patches provided keys, leaving siblings untouched', () => {
    const { result, getSearch, rerender } = renderWithRouter(
      () => useUrlState({ p: 1, s: '' as string }),
      '/?p=2&s=name',
    )
    act(() => {
      result.current[1]({ p: 3 })
    })
    rerender()
    const search = getSearch()
    expect(search).toContain('p=3')
    expect(search).toContain('s=name')
  })
})

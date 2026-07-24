import '@testing-library/jest-dom'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from './server'
import { queryClient } from '../shared/lib/queryClient'

// Start MSW server before all tests
beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))

// Reset handlers after each test
afterEach(() => {
  server.resetHandlers()
  // Shared singleton queryClient is used by dedupe helpers (e.g.
  // fetchCapabilityManifestCached). Clear it between tests so cached results
  // do not leak across unrelated test cases.
  queryClient.clear()
})

// Close server after all tests
afterAll(() => server.close())

// Mock ResizeObserver (jsdom doesn't implement it, needed by recharts)
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
Object.defineProperty(globalThis, 'ResizeObserver', {
  value: ResizeObserverMock,
  writable: true,
  configurable: true,
})

// Mock window.matchMedia (jsdom doesn't implement it)
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
})

// Mock navigator.language
// Pinned to ko-KR for parity with the production product locale. Tests that
// previously relied on the browser default falling back to en-US should
// either use a deterministic shared formatter (formatLocaleNumber, etc.)
// or assert on locale-independent substrings.
Object.defineProperty(navigator, 'language', {
  value: 'ko-KR',
  configurable: true,
})

// Node 25+ exposes a broken native localStorage that shadows jsdom's Storage.
// Provide a spec-compliant in-memory Storage so all tests work reliably.
function createStorage(): Storage {
  let store: Record<string, string> = {}
  return {
    getItem(key: string) { return key in store ? store[key] : null },
    setItem(key: string, value: string) { store[key] = String(value) },
    removeItem(key: string) { delete store[key] },
    clear() { store = {} },
    key(index: number) { return Object.keys(store)[index] ?? null },
    get length() { return Object.keys(store).length },
  }
}

Object.defineProperty(globalThis, 'localStorage', {
  value: createStorage(),
  writable: true,
  configurable: true,
})

Object.defineProperty(globalThis, 'sessionStorage', {
  value: createStorage(),
  writable: true,
  configurable: true,
})

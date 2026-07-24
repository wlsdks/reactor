import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useAuth } from '../auth'
import { fetchCapabilityManifestCached } from './useCapabilities'
import { getRouteRequirements } from './requirements'

type AvailabilityMode = 'none' | 'manifest'
const CAPABILITY_CACHE_KEY = 'reactor-admin-feature-availability-v3'
const CAPABILITY_CACHE_TTL_MS = 60 * 1000

interface CapabilityCachePayload {
  mode: 'manifest'
  endpoints: string[]
  durable?: boolean
  timestamp: number
}

interface FeatureAvailabilityContextValue {
  isLoading: boolean
  mode: AvailabilityMode
  isDurable?: boolean
  isRouteAvailable: (routePath: string) => boolean
}

const FeatureAvailabilityContext = createContext<FeatureAvailabilityContextValue | null>(null)

function readCapabilityCache(): CapabilityCachePayload | null {
  try {
    const raw = sessionStorage.getItem(CAPABILITY_CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as CapabilityCachePayload
    if (!parsed || !Array.isArray(parsed.endpoints)) return null
    if (!parsed.timestamp || Date.now() - parsed.timestamp > CAPABILITY_CACHE_TTL_MS) return null
    if (parsed.mode !== 'manifest') return null
    return parsed
  } catch {
    return null
  }
}

function writeCapabilityCache(mode: 'manifest', endpoints: Set<string>, durable: boolean): void {
  try {
    const payload: CapabilityCachePayload = {
      mode,
      endpoints: [...endpoints],
      durable,
      timestamp: Date.now(),
    }
    sessionStorage.setItem(CAPABILITY_CACHE_KEY, JSON.stringify(payload))
  } catch {
    // sessionStorage unavailable
  }
}

export function FeatureAvailabilityProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading: isAuthLoading } = useAuth()
  const [isLoading, setIsLoading] = useState(true)
  const [mode, setMode] = useState<AvailabilityMode>('none')
  const [availableEndpoints, setAvailableEndpoints] = useState<Set<string> | null>(null)
  const [isDurable, setIsDurable] = useState<boolean | undefined>()

  useEffect(() => {
    let cancelled = false

    async function detect() {
      if (isAuthLoading) {
        setIsLoading(true)
        return
      }

      const isLoginRoute = window.location.pathname === '/login'
      if (isLoginRoute) {
        setIsLoading(false)
        setMode('none')
        setAvailableEndpoints(null)
        setIsDurable(undefined)
        return
      }

      if (!isAuthenticated) {
        try {
          sessionStorage.removeItem(CAPABILITY_CACHE_KEY)
        } catch {
          // sessionStorage unavailable
        }
        setIsLoading(false)
        setMode('none')
        setAvailableEndpoints(null)
        setIsDurable(undefined)
        return
      }

      setIsLoading(true)
      const cached = readCapabilityCache()
      if (cached) {
        setMode(cached.mode)
        setAvailableEndpoints(new Set(cached.endpoints))
        setIsDurable(cached.durable !== false)
        setIsLoading(false)
        return
      }

      const manifestPaths = await fetchCapabilityManifestCached()
      if (cancelled) return
      if (manifestPaths) {
        setMode('manifest')
        setAvailableEndpoints(manifestPaths)
        setIsDurable(manifestPaths.durable)
        writeCapabilityCache('manifest', manifestPaths, manifestPaths.durable)
      } else {
        setMode('none')
        setAvailableEndpoints(null)
        setIsDurable(undefined)
      }

      setIsLoading(false)
    }

    void detect()
    return () => {
      cancelled = true
    }
  }, [isAuthenticated, isAuthLoading])

  const isRouteAvailable = (routePath: string): boolean => {
    if (!availableEndpoints || mode === 'none') return true
    const required = getRouteRequirements(routePath)
    return required.every((endpoint) => availableEndpoints.has(endpoint))
  }

  const value: FeatureAvailabilityContextValue = { isLoading, mode, isDurable, isRouteAvailable }

  return (
    <FeatureAvailabilityContext.Provider value={value}>
      {children}
    </FeatureAvailabilityContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useFeatureAvailability(): FeatureAvailabilityContextValue {
  const context = useContext(FeatureAvailabilityContext)
  if (!context) {
    throw new Error('useFeatureAvailability must be used within FeatureAvailabilityProvider')
  }
  return context
}

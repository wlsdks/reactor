import type { CSSProperties } from 'react'
import { useEffect } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { buildPreservedDestination, resolveRedirectDestination } from './redirectMappings'

const SR_ONLY_STYLE: CSSProperties = {
  position: 'absolute',
  width: '1px',
  height: '1px',
  padding: 0,
  margin: '-1px',
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  whiteSpace: 'nowrap',
  border: 0,
}

/**
 * Replacement for the legacy `/platform-admin` route. Reads the `?tab=` query
 * parameter, resolves the new destination from a hardcoded allowlist, and
 * announces the move to assistive technology before navigating.
 */
export function PlatformAdminRedirect() {
  const [searchParams] = useSearchParams()
  const tab = searchParams.get('tab')

  const { destination, destinationLabel } = resolveRedirectDestination(tab)

  const finalDestination = buildPreservedDestination(destination, searchParams)

  useEffect(() => {
    const previous = document.title
    document.title = `Redirecting to ${destinationLabel}`
    return () => {
      document.title = previous
    }
  }, [destinationLabel])

  return (
    <>
      <div role="status" aria-live="polite" style={SR_ONLY_STYLE}>
        {`Page moved to ${destinationLabel}`}
      </div>
      <Navigate to={finalDestination} replace />
    </>
  )
}

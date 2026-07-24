import type { ReactNode } from 'react'
import { ErrorBoundary } from './ErrorBoundary'

interface Props {
  children: ReactNode
  /** Section name used for error logging */
  name: string
}

/**
 * Compact error boundary for feature sections.
 * Shows a small inline error message instead of crashing the entire route.
 */
export function SectionErrorBoundary({ children, name }: Props) {
  return (
    <ErrorBoundary level="section" context={name}>
      {children}
    </ErrorBoundary>
  )
}

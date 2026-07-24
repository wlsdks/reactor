import { Suspense, type ReactNode } from 'react'
import { LoadingSpinner } from './LoadingSpinner'

export function PageSuspense({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<div className="loading-fullscreen"><LoadingSpinner size="lg" /></div>}>
      {children}
    </Suspense>
  )
}

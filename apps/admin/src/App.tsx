import { RouterProvider } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { ToastContainer, LiveAnnouncerProvider } from './shared/ui'
import { AuthProvider } from './features/auth'
import { FeatureAvailabilityProvider } from './features/capabilities'
import { RoleVisibilityProvider } from './features/workspace'
import { ErrorBoundary } from './shared/ui'
import { queryClient } from './shared/lib/queryClient'
import { router } from './router'

export default function App() {
  return (
    <ErrorBoundary level="app">
      <QueryClientProvider client={queryClient}>
        <LiveAnnouncerProvider>
          <AuthProvider>
            <RoleVisibilityProvider>
              <FeatureAvailabilityProvider>
                <RouterProvider router={router} />
              </FeatureAvailabilityProvider>
            </RoleVisibilityProvider>
          </AuthProvider>
          <ToastContainer />
        </LiveAnnouncerProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}

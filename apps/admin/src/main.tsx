import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { initSentry } from './shared/lib/sentry'
import { errorLogger } from './shared/lib/errorLogger'
import './shared/i18n/config'
import './index.css'
import './styles/product-tokens.css'
import './shared/ui/shared-components.css'
import App from './App'

initSentry()

window.addEventListener('unhandledrejection', (event) => {
  const reason: unknown = event.reason
  const error = reason instanceof Error ? reason : new Error(String(reason))
  errorLogger.capture(error)
})

window.onerror = (
  message: string | Event,
  source?: string,
  lineno?: number,
  colno?: number,
  error?: Error,
) => {
  const captured = error ?? new Error(String(message))
  errorLogger.capture(captured, {
    action: 'window.onerror',
    component: typeof source === 'string' ? `${source}:${lineno ?? 0}:${colno ?? 0}` : undefined,
  })
}

async function enableMocking() {
  if (import.meta.env.DEV && import.meta.env.VITE_MOCK === 'true') {
    const { worker } = await import('./test/browser')
    return worker.start({ onUnhandledRequest: 'bypass' })
  }
}

enableMocking()
  .catch(() => {
    // MSW service worker failed to start (e.g., blocked by Playwright).
    // Continue without mocking — the app renders fine without it.
  })
  .then(() => {
    createRoot(document.getElementById('root')!).render(
      <StrictMode>
        <App />
      </StrictMode>,
    )
  })

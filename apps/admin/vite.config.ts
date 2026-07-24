import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget = env.VITE_PROXY_TARGET || 'http://localhost:8000'
  const iamTarget = env.VITE_IAM_PROXY_TARGET || 'http://localhost:18082'
  const iamEnabled = env.VITE_IAM_ENABLED === 'true' || Boolean(env.VITE_IAM_URL)
  const authTarget = iamEnabled ? iamTarget : proxyTarget

  return {
  plugins: [
    react({
      babel: {
        plugins: ['babel-plugin-react-compiler'],
      },
    }),
  ],
  build: {
    sourcemap: 'hidden',
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.endsWith('/src/shared/i18n/ko.json')) return 'app-locale-ko'

          if (!id.includes('node_modules')) return undefined

          // React core runtime
          if (
            id.includes('/react-dom/') ||
            /\/node_modules\/react\//.test(id) ||
            id.includes('/scheduler/')
          ) {
            return 'vendor-react'
          }

          // Router (react-router-dom v7 is substantial)
          if (
            id.includes('/react-router-dom/') ||
            id.includes('/react-router/')
          ) {
            return 'vendor-router'
          }

          // TanStack Query
          if (id.includes('/@tanstack/')) return 'vendor-query'

          // Forms
          if (id.includes('/react-hook-form/') || id.includes('/@hookform/')) {
            return 'vendor-form'
          }

          // i18n
          if (id.includes('/i18next/') || id.includes('/react-i18next/')) {
            return 'vendor-i18n'
          }

          // HTTP client
          if (id.includes('/ky/')) return 'vendor-ky'

          // Runtime schemas are shared by most lazy feature routes. Keep Zod
          // outside the application entry chunk so route-level code splitting
          // does not duplicate or eagerly absorb the schema runtime.
          if (/\/node_modules\/(?:\.pnpm\/[^/]+\/node_modules\/)?zod\//.test(id)) {
            return 'vendor-schema'
          }

          // Icons
          if (id.includes('/lucide-react/')) return 'vendor-icons'

          // State management
          if (id.includes('/zustand/')) return 'vendor-state'

          // Virtualisation (react-window)
          if (id.includes('/react-window/')) return 'vendor-virtual'

          // Error monitoring
          if (id.includes('/@sentry/')) return 'vendor-sentry'

          // Shared d3 runtime. Recharts and React Flow both depend on d3
          // packages, so keep them in one shared chunk instead of splitting
          // d3 modules across vendor-charts and vendor-flow.
          if (id.includes('/d3-')) {
            return 'vendor-d3'
          }

          // Topology graph (React Flow / xyflow).
          // Loaded only when the Issues page renders SystemTopology (lazy),
          // keeping the React Flow runtime separate from recharts.
          if (id.includes('@xyflow/')) {
            return 'vendor-flow'
          }

          // Charts (recharts; d3 helpers are isolated above)
          if (id.includes('recharts')) {
            return 'vendor-charts'
          }

          return undefined
        },
      },
    },
  },
  server: {
    port: 3001,
    proxy: {
      // IAM owns these endpoints only when the local environment explicitly
      // enables IAM. Otherwise the direct reactor login fallback must not
      // be routed to an unavailable IAM service.
      '/api/auth/login': { target: authTarget, changeOrigin: true },
      '/api/auth/register': { target: authTarget, changeOrigin: true },
      '/api/auth/refresh': { target: authTarget, changeOrigin: true },
      '/api/auth/public-key': { target: authTarget, changeOrigin: true },
      // Everything else (including /api/auth/exchange, /api/auth/logout) → reactor
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/v3/api-docs': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
  }
})

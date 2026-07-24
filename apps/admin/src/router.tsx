import { lazy } from 'react'
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { PlatformAdminRedirect } from './features/workspace'
import { FeatureRoute } from './features/capabilities'
import { AdminLayout } from './widgets/layout'
import { PageSuspense } from './shared/ui'
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'

const DashboardPage = lazy(() => import('./pages/DashboardPage').then(m => ({ default: m.DashboardPage })))
const ReleaseOperationsPage = lazy(() => import('./pages/ReleaseOperationsPage').then(m => ({ default: m.ReleaseOperationsPage })))
const PersonasPage = lazy(() => import('./pages/PersonasPage').then(m => ({ default: m.PersonasPage })))
const McpServersPage = lazy(() => import('./pages/McpServersPage').then(m => ({ default: m.McpServersPage })))
const McpServerDetailPage = lazy(() => import('./pages/McpServerDetailPage'))
const SchedulerPage = lazy(() => import('./pages/SchedulerPage').then(m => ({ default: m.SchedulerPage })))
const ApprovalsPage = lazy(() => import('./pages/ApprovalsPage').then(m => ({ default: m.ApprovalsPage })))
const DebugReplayPage = lazy(() => import('./pages/DebugReplayPage').then(m => ({ default: m.DebugReplayPage })))
const SessionsPage = lazy(() => import('./pages/SessionsPage').then(m => ({ default: m.SessionsPage })))
const SessionsFeedPage = lazy(() => import('./pages/SessionsFeedPage').then(m => ({ default: m.SessionsFeedPage })))
const SessionUsersPage = lazy(() => import('./pages/SessionUsersPage').then(m => ({ default: m.SessionUsersPage })))
const SessionUserDetailPage = lazy(() => import('./pages/SessionUserDetailPage').then(m => ({ default: m.SessionUserDetailPage })))
const SessionDetailPage = lazy(() => import('./pages/SessionDetailPage').then(m => ({ default: m.SessionDetailPage })))
const FeedbackPage = lazy(() => import('./pages/FeedbackPage').then(m => ({ default: m.FeedbackPage })))
const SafetyRulesPage = lazy(() => import('./pages/SafetyRulesPage').then(m => ({ default: m.SafetyRulesPage })))
const DocumentsPage = lazy(() => import('./pages/DocumentsPage').then(m => ({ default: m.DocumentsPage })))
const AuditLogPage = lazy(() => import('./pages/AuditLogPage').then(m => ({ default: m.AuditLogPage })))
const MetricsIngestionPage = lazy(() => import('./pages/MetricsIngestionPage').then(m => ({ default: m.MetricsIngestionPage })))
const ChatInspectorPage = lazy(() => import('./pages/ChatInspectorPage').then(m => ({ default: m.ChatInspectorPage })))
const IntegrationsPage = lazy(() => import('./pages/IntegrationsPage').then(m => ({ default: m.IntegrationsPage })))
const IssuesPage = lazy(() => import('./pages/IssuesPage').then(m => ({ default: m.IssuesPage })))
const PromptStudioPage = lazy(() => import('./pages/PromptStudioPage').then(m => ({ default: m.PromptStudioPage })))
const RagCachePage = lazy(() => import('./pages/RagCachePage').then(m => ({ default: m.RagCachePage })))
const EvalsPage = lazy(() => import('./pages/EvalsPage').then(m => ({ default: m.EvalsPage })))
const TracesPage = lazy(() => import('./pages/TracesPage').then(m => ({ default: m.TracesPage })))
const ReactorUniversePage = lazy(() => import('./pages/ReactorUniversePage').then(m => ({ default: m.ReactorUniversePage })))
const PerformancePage = lazy(() => import('./pages/PerformancePage').then(m => ({ default: m.PerformancePage })))
const UsagePage = lazy(() => import('./pages/UsagePage').then(m => ({ default: m.UsagePage })))
const ModelRegistryPage = lazy(() => import('./pages/ModelRegistryPage').then(m => ({ default: m.ModelRegistryPage })))
const HealthPage = lazy(() => import('./pages/HealthPage').then(m => ({ default: m.HealthPage })))
const TenantsPage = lazy(() => import('./pages/TenantsPage').then(m => ({ default: m.TenantsPage })))
const SettingsPage = lazy(() => import('./pages/SettingsPage').then(m => ({ default: m.SettingsPage })))
const AccessControlPage = lazy(() => import('./pages/AccessControlPage').then(m => ({ default: m.AccessControlPage })))

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    element: <AdminLayout />,
    children: [
      {
        index: true,
        element: (
          <FeatureRoute routePath="/" titleKey="nav.dashboard">
            <PageSuspense><DashboardPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'release',
        element: (
          <FeatureRoute routePath="/release" titleKey="nav.releaseOperations" allowWhenUnavailable>
            <PageSuspense><ReleaseOperationsPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'issues',
        element: (
          <FeatureRoute routePath="/issues" titleKey="nav.issues" allowWhenUnavailable>
            <PageSuspense><IssuesPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'personas',
        element: (
          <FeatureRoute routePath="/personas" titleKey="nav.personas">
            <PageSuspense><PersonasPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'prompt-studio',
        element: (
          <FeatureRoute routePath="/prompt-studio" titleKey="nav.promptStudio">
            <PageSuspense><PromptStudioPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'prompts',
        element: <Navigate to="/prompt-studio" replace />,
      },
      {
        path: 'mcp-servers',
        element: (
          <FeatureRoute routePath="/mcp-servers" titleKey="nav.mcpServers">
            <PageSuspense><McpServersPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'mcp-servers/:name',
        element: (
          <FeatureRoute routePath="/mcp-servers/:name" titleKey="nav.mcpServers">
            <PageSuspense><McpServerDetailPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'mcp-security',
        element: <Navigate to="/mcp-servers" replace />,
      },
      {
        path: 'reactor-universe',
        element: (
          <FeatureRoute routePath="/reactor-universe" titleKey="nav.reactorUniverse" allowWhenUnavailable>
            <PageSuspense><ReactorUniversePage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'scheduler',
        element: (
          <FeatureRoute routePath="/scheduler" titleKey="nav.scheduler" allowWhenUnavailable>
            <PageSuspense><SchedulerPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'approvals',
        element: (
          <FeatureRoute routePath="/approvals" titleKey="nav.approvals" allowWhenUnavailable>
            <PageSuspense><ApprovalsPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'debug-replay',
        element: (
          <FeatureRoute routePath="/debug-replay" titleKey="nav.debugReplay" allowWhenUnavailable>
            <PageSuspense><DebugReplayPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'sessions',
        children: [
          {
            index: true,
            element: (
              <FeatureRoute routePath="/sessions" titleKey="nav.sessions">
                <PageSuspense><SessionsPage /></PageSuspense>
              </FeatureRoute>
            ),
          },
          {
            path: 'feed',
            element: (
              <FeatureRoute routePath="/sessions" titleKey="nav.sessions">
                <PageSuspense><SessionsFeedPage /></PageSuspense>
              </FeatureRoute>
            ),
          },
          {
            path: 'users',
            element: (
              <FeatureRoute routePath="/sessions" titleKey="nav.sessions">
                <PageSuspense><SessionUsersPage /></PageSuspense>
              </FeatureRoute>
            ),
          },
          {
            path: 'users/:userId',
            element: (
              <FeatureRoute routePath="/sessions" titleKey="nav.sessions">
                <PageSuspense><SessionUserDetailPage /></PageSuspense>
              </FeatureRoute>
            ),
          },
          {
            path: ':sessionId',
            element: (
              <FeatureRoute routePath="/sessions" titleKey="nav.sessions">
                <PageSuspense><SessionDetailPage /></PageSuspense>
              </FeatureRoute>
            ),
          },
        ],
      },
      {
        path: 'traces',
        element: (
          <FeatureRoute routePath="/traces" titleKey="nav.traces">
            <PageSuspense><TracesPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'feedback',
        element: (
          <FeatureRoute routePath="/feedback" titleKey="nav.feedback">
            <PageSuspense><FeedbackPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'safety-rules',
        element: (
          <FeatureRoute routePath="/safety-rules" titleKey="nav.safetyRules">
            <PageSuspense><SafetyRulesPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'input-guard',
        element: <Navigate to="/safety-rules?tab=input-guard" replace />,
      },
      {
        path: 'output-guard',
        element: <Navigate to="/safety-rules?tab=output-guard" replace />,
      },
      {
        path: 'tool-policy',
        element: <Navigate to="/safety-rules?tab=tool-policy" replace />,
      },
      {
        path: 'documents',
        element: (
          <FeatureRoute routePath="/documents" titleKey="nav.documents">
            <PageSuspense><DocumentsPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'rag-cache',
        element: (
          <FeatureRoute routePath="/rag-cache" titleKey="nav.ragCache" allowWhenUnavailable>
            <PageSuspense><RagCachePage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'intents',
        element: <Navigate to="/prompt-studio" replace />,
      },
      {
        path: 'audit',
        element: (
          <FeatureRoute routePath="/audit" titleKey="nav.audit">
            <PageSuspense><AuditLogPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'prompt-lab',
        element: <Navigate to="/prompt-studio" replace />,
      },
      {
        path: 'evals',
        element: (
          <FeatureRoute routePath="/evals" titleKey="nav.evals">
            <PageSuspense><EvalsPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'performance',
        element: (
          <FeatureRoute routePath="/performance" titleKey="nav.performance">
            <PageSuspense><PerformancePage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'usage',
        element: (
          <FeatureRoute routePath="/usage" titleKey="nav.usage">
            <PageSuspense><UsagePage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'platform-admin',
        element: <PlatformAdminRedirect />,
      },
      {
        path: 'rbac',
        element: <Navigate to="/access-control" replace />,
      },
      {
        path: 'models',
        element: (
          <FeatureRoute routePath="/models" titleKey="nav.models" allowWhenUnavailable>
            <PageSuspense><ModelRegistryPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'health',
        element: (
          <FeatureRoute routePath="/health" titleKey="healthPage.title" allowWhenUnavailable>
            <PageSuspense><HealthPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'tenants',
        element: (
          <FeatureRoute routePath="/tenants" titleKey="tenantsPage.title" allowWhenUnavailable>
            <PageSuspense><TenantsPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'retention',
        element: <Navigate to="/settings?tab=retention" replace />,
      },
      {
        path: 'settings',
        element: (
          <FeatureRoute routePath="/settings" titleKey="settingsPage.title" allowWhenUnavailable>
            <PageSuspense><SettingsPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'access-control',
        element: (
          <FeatureRoute routePath="/access-control" titleKey="nav.accessControl" allowWhenUnavailable>
            <PageSuspense><AccessControlPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'tenant-admin',
        element: <Navigate to="/tenants?tab=tenant" replace />,
      },
      {
        path: 'metrics-ingestion',
        element: (
          <FeatureRoute routePath="/metrics-ingestion" titleKey="nav.metricsIngestion">
            <PageSuspense><MetricsIngestionPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'chat-inspector',
        element: (
          <FeatureRoute routePath="/chat-inspector" titleKey="nav.chatInspector">
            <PageSuspense><ChatInspectorPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'integrations',
        element: (
          <FeatureRoute routePath="/integrations" titleKey="nav.integrations">
            <PageSuspense><IntegrationsPage /></PageSuspense>
          </FeatureRoute>
        ),
      },
      {
        path: 'proactive-channels',
        element: <Navigate to="/integrations?tab=channels" replace />,
      },
      {
        path: '*',
        element: <NotFoundPage />,
      },
    ],
  },
])

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { readdirSync, statSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const sourceRoot = join(process.cwd(), 'src')

describe('product design token contract', () => {
  it('defines the semantic workspace, surface, control, data, and overlay roles', () => {
    const css = readFileSync(join(sourceRoot, 'styles/product-tokens.css'), 'utf8')

    for (const token of [
      '--workspace-gutter',
      '--workspace-section-gap',
      '--surface-panel-padding',
      '--type-page-title-size',
      '--control-height-default',
      '--icon-size-default',
      '--conversation-list-compact-height',
      '--data-row-height',
      '--data-row-height-comfortable',
      '--overlay-panel-width',
      '--dialog-width',
      '--surface-note',
      '--surface-feedback',
      '--workspace-mobile-edge',
      '--brand-mark-foreground',
      '--navigation-item-active-surface',
      '--navigation-item-active-foreground',
      '--navigation-item-active-icon',
    ]) {
      expect(css).toContain(token)
    }
  })

  it('keeps brand and selected-navigation color roles out of unused animated gauge chrome', () => {
    const layoutCss = readFileSync(
      join(sourceRoot, 'widgets/layout/layout.css'),
      'utf8',
    )
    const sharedUiIndex = readFileSync(join(sourceRoot, 'shared/ui/index.ts'), 'utf8')
    const sharedLibIndex = readFileSync(join(sourceRoot, 'shared/lib/index.ts'), 'utf8')
    const globalCss = readFileSync(join(sourceRoot, 'index.css'), 'utf8')

    expect(layoutCss).toContain('color: var(--brand-mark-foreground)')
    expect(layoutCss).toContain('color: var(--navigation-item-active-foreground)')
    expect(layoutCss).toContain('background: var(--navigation-item-active-surface)')
    expect(layoutCss).toContain('color: var(--navigation-item-active-icon)')
    expect(layoutCss).not.toContain('dotPulse')
    expect(layoutCss).not.toContain('bounce-down')
    expect(globalCss).toMatch(/\.login-logo\s*{[^}]*color:\s*var\(--brand-mark-foreground\)/)
    expect(sharedUiIndex).not.toContain('ReactorGauge')
    expect(sharedLibIndex).not.toContain('useCountUp')
  })

  it('forbids decorative vertical status rails across product styles', () => {
    const cssFiles: string[] = []
    const visit = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name)
        if (statSync(path).isDirectory()) visit(path)
        else if (path.endsWith('.css')) cssFiles.push(path)
      }
    }
    visit(sourceRoot)

    for (const file of cssFiles) {
      const css = readFileSync(file, 'utf8')
      expect(css, file).not.toMatch(/border-left:\s*[2-4]px\s+solid/)
      expect(css, file).not.toMatch(/border-left-color\s*:/)
    }
  })

  it('keeps service relationships list-first and free from decorative topology motion', () => {
    const status = readFileSync(
      join(sourceRoot, 'features/issues/ui/SystemTopology.status.ts'),
      'utf8',
    )
    const topology = readFileSync(
      join(sourceRoot, 'features/issues/ui/SystemTopology.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/dashboard/ui/dashboard.css'),
      'utf8',
    )

    expect(status).toContain("return raw === 'graph' ? 'graph' : 'list'")
    expect(topology).not.toContain('useForceSimulation')
    expect(topology).not.toContain('useTopologyAnimationVars')
    expect(topology).toContain('nodesDraggable={false}')
    expect(css).not.toContain('topo-rf-center__orbit')
    expect(css).not.toContain('topo-rf-edge__flow')
    expect(css).not.toContain('topo-rf-node__pulse')
    expect(css).not.toContain('radial-gradient(circle at 50% 50%, var(--accent-subtle)')
  })

  it('loads product tokens before shared UI component styles', () => {
    const main = readFileSync(join(sourceRoot, 'main.tsx'), 'utf8')
    const tokenImport = main.indexOf("import './styles/product-tokens.css'")
    const componentImport = main.indexOf("import './shared/ui/shared-components.css'")

    expect(tokenImport).toBeGreaterThan(-1)
    expect(componentImport).toBeGreaterThan(tokenImport)
  })

  it('keeps one visible workspace heading on session routes', () => {
    for (const page of [
      'SessionsPage.tsx',
      'SessionsFeedPage.tsx',
      'SessionUsersPage.tsx',
    ]) {
      const source = readFileSync(join(sourceRoot, 'pages', page), 'utf8')
      expect(source).toContain('<SessionsWorkspaceHeader')
      expect(source).not.toContain('<h1 className="sr-only">')
    }
  })

  it('does not shrink the root type scale or bypass workspace gutters at desktop-narrow widths', () => {
    const globalCss = readFileSync(join(sourceRoot, 'index.css'), 'utf8')

    expect(globalCss).not.toContain('html { font-size: 14px; }')
    expect(globalCss).not.toContain('.app-content { padding: var(--content-pad); }')
    expect(globalCss).toContain('.app-content { padding: var(--workspace-gutter); }')
  })

  it('scopes collapsed release disclosure rules to details elements', () => {
    const css = readFileSync(
      join(sourceRoot, 'features/dashboard/ui/dashboard.css'),
      'utf8',
    )

    expect(css).toContain('details.release-cockpit__recommendation:not([open])')
    expect(css).not.toMatch(/(?<!details)\.release-cockpit__recommendation:not\(\[open\]\)/)
  })

  it('keeps feedback technical evidence hidden until its disclosure opens', () => {
    const css = readFileSync(
      join(sourceRoot, 'features/feedback/ui/feedback.css'),
      'utf8',
    )

    expect(css).toContain('.fb-promotion-panel__boundary-chain:not([open]) > :not(summary)')
    expect(css).toContain('.fb-promotion-panel__handoff-queue:not([open]) > :not(summary)')
    expect(css).toContain('.fb-release-action:not([open]) > :not(summary)')
  })

  it('keeps evaluation evidence inside closed disclosures by default', () => {
    const css = readFileSync(
      join(sourceRoot, 'features/evals/ui/EvalDashboardManager.css'),
      'utf8',
    )

    expect(css).toContain('.eval-langsmith-panel__evidence-disclosure:not([open]) > :not(summary)')
    expect(css).toContain('.eval-langsmith-panel__handoff:not([open]) > :not(summary)')
    expect(css).toContain('.eval-langsmith-panel__command-disclosure:not([open]) > :not(summary)')
    expect(css).toContain('.eval-langsmith-panel__live-result:not([open]) > :not(summary)')
  })

  it('keeps feedback and evaluation workflows as open divided lists, not a step-card grid', () => {
    const feedbackCss = readFileSync(
      join(sourceRoot, 'features/feedback/ui/feedback.css'),
      'utf8',
    )
    const evalCss = readFileSync(
      join(sourceRoot, 'features/evals/ui/EvalDashboardManager.css'),
      'utf8',
    )

    expect(feedbackCss).toMatch(/\.fb-promotion-panel__workflow\s*{\s*display: grid;\s*grid-template-columns: 1fr;/)
    expect(evalCss).toMatch(/\.eval-langsmith-panel__workflow\s*{\s*display: grid;\s*grid-template-columns: 1fr;/)
    expect(feedbackCss).not.toMatch(/\.fb-promotion-panel__workflow\s*{[^}]*repeat\(3/)
    expect(evalCss).not.toMatch(/\.eval-langsmith-panel__workflow\s*{[^}]*repeat\(3/)
  })

  it('keeps organization facts open and removes decorative tenant dividers', () => {
    const tenantCss = readFileSync(
      join(sourceRoot, 'features/tenant-admin/ui/TenantAdminManager.css'),
      'utf8',
    )
    const platformTenantCss = readFileSync(
      join(sourceRoot, 'features/platform-admin/ui/PlatformTenantsTab.css'),
      'utf8',
    )

    expect(tenantCss).toMatch(/\.tenant-metrics\s*{\s*display: flex;\s*flex-wrap: wrap;/)
    expect(tenantCss).not.toMatch(/\.tenant-metrics\s*{[^}]*repeat\(6/)
    expect(platformTenantCss).toMatch(/\.tenant-detail dl\s*{\s*display: flex;/)
    expect(platformTenantCss).not.toContain('.tenant-detail dl > div + div { border-left')
  })

  it('keeps unavailable-route diagnostics out of the ordinary operator view', () => {
    const source = readFileSync(
      join(sourceRoot, 'features/capabilities/FeatureRoute.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'shared/ui/shared-components.css'),
      'utf8',
    )

    expect(source).toContain('feature-route-unavailable__notice')
    expect(source).not.toContain('detail-panel detail-panel-empty')
    expect(source).not.toContain('<pre className="code-block"')
    expect(css).toContain('.feature-route-unavailable__technical:not([open]) > :not(summary)')
  })

  it('keeps document candidate review table-first and technical evidence closed', () => {
    const css = readFileSync(
      join(sourceRoot, 'features/documents/ui/document-ingestion.css'),
      'utf8',
    )
    const source = readFileSync(
      join(sourceRoot, 'features/documents/ui/DocumentsManager.tsx'),
      'utf8',
    )

    expect(css).toContain('.document-ingestion-review__technical:not([open]) > :not(summary)')
    expect(css).not.toContain('border-radius: var(--surface-panel-radius)')
    expect(source).not.toContain('ReleaseWorkflowBacklink')
  })

  it('keeps document-search operations open and technical evidence closed', () => {
    const css = readFileSync(
      join(sourceRoot, 'features/rag-cache/ui/rag-cache-insight.css'),
      'utf8',
    )
    const manager = readFileSync(
      join(sourceRoot, 'features/rag-cache/ui/RagCacheManager.tsx'),
      'utf8',
    )
    const search = readFileSync(
      join(sourceRoot, 'features/rag-cache/ui/RagQuickSearch.tsx'),
      'utf8',
    )

    expect(css).toContain('.rag-technical-details:not([open]) > :not(summary)')
    expect(css).not.toContain('.rag-lifecycle-strip')
    expect(manager).toContain("type TabKey = 'cache' | 'candidates' | 'rag' | 'policy' | 'analytics'")
    expect(manager).not.toContain('dashboardApi')
    expect(search).not.toContain('RELEASE_RAG_ANSWER_CONTRACT_PATH')
    expect(search).not.toContain('ReleaseWorkflowBacklink')
  })

  it('keeps answer-review evidence out of the candidate decision surface', () => {
    const css = readFileSync(
      join(sourceRoot, 'features/rag-cache/ui/rag-cache-insight.css'),
      'utf8',
    )
    const drawer = readFileSync(
      join(sourceRoot, 'features/rag-cache/ui/RagCandidateDetailDrawer.tsx'),
      'utf8',
    )

    expect(drawer).toContain('candidate-review-drawer__technical')
    expect(drawer).not.toContain('ReleaseWorkflowBacklink')
    expect(drawer).not.toContain('StatusBadge')
    expect(drawer).not.toContain('RELEASE_WORKFLOW_PATHS_BY_ID')
    expect(css).toContain('.candidate-review-drawer__checks')
    expect(css).not.toContain('.rag-candidate-action__state')
    expect(css).not.toContain('.rag-candidate-action__runbook')
  })

  it('keeps approval decisions in the selected detail and raw evidence closed', () => {
    const source = readFileSync(
      join(sourceRoot, 'features/approvals/ui/ApprovalsManager.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/approvals/ui/approvals.css'),
      'utf8',
    )

    expect(source).toContain('approval-detail__technical')
    expect(source).not.toContain('StatusBadge')
    expect(source).not.toContain('row-actions--paired')
    expect(source).toContain('formatApprovalAge')
    expect(css).toContain('.approvals-readiness__checks')
    expect(css).toContain('.approval-status--pending')
  })

  it('keeps integration setup evidence out of the connection overview', () => {
    const manager = readFileSync(
      join(sourceRoot, 'features/integrations/ui/IntegrationsManager.tsx'),
      'utf8',
    )
    const probes = readFileSync(
      join(sourceRoot, 'features/integrations/ui/ControlPlaneProbesPanel.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/integrations/ui/IntegrationsManager.css'),
      'utf8',
    )
    const operations = readFileSync(
      join(sourceRoot, 'features/integrations/ui/ExternalSmokeOperations.tsx'),
      'utf8',
    )

    expect(manager).not.toContain('ReleaseWorkflowBacklink')
    expect(probes).toContain("view === 'evidence' && (")
    expect(probes).not.toContain("hidden={view !== 'evidence'}")
    expect(probes).not.toContain('RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID')
    expect(probes).not.toContain('release-smoke-command__step')
    expect(probes).toContain('integration-evidence-detail')
    expect(probes).not.toContain('release-smoke-evidence')
    expect(css).toContain('.integration-evidence-detail__summary:focus-visible')
    expect(operations).not.toContain('StatusBadge')
    expect(operations).toContain('smoke-operation-status')
  })

  it('keeps manual integration tests as one readable operator surface', () => {
    const slack = readFileSync(
      join(sourceRoot, 'features/integrations/ui/IntegrationsSlackTab.tsx'),
      'utf8',
    )
    const errorReport = readFileSync(
      join(sourceRoot, 'features/integrations/ui/IntegrationsErrorReportTab.tsx'),
      'utf8',
    )
    const result = readFileSync(
      join(sourceRoot, 'features/integrations/ui/IntegrationTestResult.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/integrations/ui/IntegrationsManager.css'),
      'utf8',
    )

    expect(slack).toContain('integration-tool-workspace')
    expect(errorReport).toContain('integration-tool-workspace')
    expect(slack).not.toContain('split-layout')
    expect(errorReport).not.toContain('split-layout')
    expect(result).toContain('integration-tool-result__technical')
    expect(css).toContain('.integration-tool-result__technical:not([open]) > :not(summary)')
    expect(css).toContain('@media (max-width: 900px)')
    expect(css).toContain('.integration-tool-form .form-row')
  })

  it('keeps integration evidence as feature-owned operator rows, not a release workflow grid', () => {
    const source = readFileSync(
      join(sourceRoot, 'features/integrations/ui/ControlPlaneProbesPanel.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/integrations/ui/IntegrationsManager.css'),
      'utf8',
    )

    expect(source).not.toContain('ProductCapabilityBoundaryFlowList')
    expect(source).not.toContain('release-smoke-workflow')
    expect(source).not.toContain('release-smoke-action-queue')
    expect(css).toContain('.release-smoke-gate__header')
    expect(css).toContain('.release-evidence-status')
    expect(css).toContain('@media (max-width: 640px)')
    expect(css).not.toMatch(/\.release-smoke-gates\s*{[^}]*grid-template-columns/)
  })

  it('keeps AI model response tests as an open operator flow with technical evidence closed', () => {
    const source = readFileSync(
      join(sourceRoot, 'features/model-registry/ui/ModelRegistryManager.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/model-registry/ui/model-registry.css'),
      'utf8',
    )

    expect(source).not.toContain('StatusBadge')
    expect(source).not.toContain('ReleaseReportLink')
    expect(source).not.toContain('RELEASE_WORKFLOW_PATHS_BY_ID')
    expect(source).toContain('modelsPage.loadErrorTitle')
    expect(source).toContain('model-provider-smoke__unavailable')
    expect(css).toMatch(/\.model-registry-summary\s*{\s*display: flex;/)
    expect(css).not.toMatch(/\.model-provider-smoke__live-result dl\s*{[^}]*repeat\(4/)
    expect(css).toContain('details.model-provider-smoke__evidence:not([open]) > :not(summary)')
  })

  it('keeps response-test payloads and stream records out of the primary answer view', () => {
    const response = readFileSync(
      join(sourceRoot, 'features/chat-inspector/ui/ResponseDetailPanel.tsx'),
      'utf8',
    )
    const stream = readFileSync(
      join(sourceRoot, 'features/chat-inspector/ui/StreamOutputPanel.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/chat-inspector/ui/ChatInspectorManager.css'),
      'utf8',
    )

    expect(response).toContain('chat-inspector-response__content')
    expect(response).not.toContain('<pre className="code-block">{displayText(result.content)}</pre>')
    expect(response).toContain('chat-inspector-response__technical-details')
    expect(stream).toContain('chat-inspector-stream-output__events')
    expect(stream).not.toContain('detail-panel detail-panel--compact')
    expect(css).toContain('.chat-inspector-response__technical-details')
    expect(css).toContain('.chat-inspector-response__technical-summary')
    expect(css).toContain('.chat-inspector-response__technical-details:not([open]) > :not(summary)')
  })

  it('keeps scheduled-job operations in the selected detail and raw execution data closed', () => {
    const jobsTable = readFileSync(
      join(sourceRoot, 'features/scheduler/ui/SchedulerJobsTable.tsx'),
      'utf8',
    )
    const jobDetail = readFileSync(
      join(sourceRoot, 'features/scheduler/ui/SchedulerJobDetail.tsx'),
      'utf8',
    )
    const executionDetail = readFileSync(
      join(sourceRoot, 'features/scheduler/ui/SchedulerExecutionDetail.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/scheduler/ui/SchedulerManager.css'),
      'utf8',
    )

    expect(jobsTable).not.toContain('className="row-actions"')
    expect(jobDetail).toContain('scheduler-job-detail__technical')
    expect(jobDetail).toContain("variant=\"danger\"")
    expect(executionDetail).toContain('scheduler-execution-detail__technical')
    expect(css).toContain('.scheduler-technical-details:not([open]) > :not(summary)')
    expect(css).toMatch(/\.scheduler-detail-facts\s*{\s*display: flex;\s*flex-wrap: wrap;/)
  })

  it('keeps prompt comparison results as open facts instead of metric tiles', () => {
    const source = readFileSync(
      join(sourceRoot, 'features/prompt-studio/ui/ExperimentResults.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/prompt-studio/ui/prompt-studio.css'),
      'utf8',
    )

    expect(source).toContain('<dl className="comparison-facts">')
    expect(source).not.toContain('className="metric-grid"')
    expect(css).toMatch(/\.comparison-facts\s*{\s*display: flex;\s*flex-wrap: wrap;/)
    expect(css).not.toContain('.comparison-row .metric-grid')
  })

  it('keeps response-quality comparisons table-first and their raw records closed', () => {
    const manager = readFileSync(
      join(sourceRoot, 'features/prompt-lab/ui/PromptLabManager.tsx'),
      'utf8',
    )
    const detail = readFileSync(
      join(sourceRoot, 'features/prompt-lab/ui/ExperimentDetail.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/prompt-lab/ui/prompt-lab.css'),
      'utf8',
    )

    expect(manager).not.toContain('ReleaseWorkflowBacklink')
    expect(manager).not.toContain('StatusBadge')
    expect(detail).not.toContain('StatusBadge')
    expect(detail).toContain('prompt-experiment-detail__technical')
    expect(css).toContain('.prompt-lab-technical-details:not([open]) > :not(summary)')
    expect(css).not.toMatch(/\.prompt-experiment-comparison__row\s*{[^}]*repeat\(3,\s*1fr\)/)
  })

  it('keeps answer-role actions and technical identifiers in the selected detail', () => {
    const manager = readFileSync(
      join(sourceRoot, 'features/personas/ui/PersonaManager.tsx'),
      'utf8',
    )
    const info = readFileSync(
      join(sourceRoot, 'features/personas/ui/PersonaInfoTab.tsx'),
      'utf8',
    )
    const playground = readFileSync(
      join(sourceRoot, 'features/personas/ui/PersonaPlayground.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/personas/ui/personas.css'),
      'utf8',
    )

    expect(manager).not.toContain('rowActions={personaRowActions}')
    expect(manager).toContain('persona-detail--unavailable')
    expect(info).toContain('persona-technical-details')
    expect(info).not.toContain('form-code-block')
    expect(playground).not.toContain("'🤖'")
    expect(playground).not.toContain("'👤'")
    expect(css).toContain('.persona-technical-details:not([open]) > :not(summary)')
  })

  it('keeps failed-request recovery focused on a selected detail and closes raw diagnostics', () => {
    const source = readFileSync(
      join(sourceRoot, 'features/debug-replay/ui/DebugReplayManager.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/debug-replay/ui/debug-replay.css'),
      'utf8',
    )

    expect(source).toContain('debug-replay-detail__unavailable')
    expect(source).toContain('debugReplay.failureReason')
    expect(source).not.toContain('debug-replay-section__step')
    expect(source).not.toContain('debug-replay-review')
    expect(css).toContain('.debug-replay-technical:not([open]) > :not(summary)')
    expect(css).not.toContain('border-left:')
  })

  it('keeps manual diagnostic submission readable and its raw failure closed', () => {
    const source = readFileSync(
      join(sourceRoot, 'features/metric-ingestion/ui/MetricIngestionManager.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/metric-ingestion/ui/MetricIngestionManager.css'),
      'utf8',
    )

    expect(source).toContain('metricsIngestionPage.submitUnavailable')
    expect(source).toContain('metric-ingestion-workspace__technical-error')
    expect(source).not.toContain('metric-ingestion-workspace__step')
    expect(source).not.toContain('LoadingSpinner')
    expect(css).toContain('.metric-ingestion-workspace__technical:not([open]) > :not(summary)')
    expect(css).toContain('.metric-ingestion-workspace__payload textarea:focus-visible')
  })

  it('keeps external tool connection actions in the selected detail', () => {
    const list = readFileSync(
      join(sourceRoot, 'features/mcp-servers/ui/McpServersListView.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/mcp-servers/ui/McpServersListView.css'),
      'utf8',
    )

    expect(list).not.toContain('mcp-row-actions')
    expect(list).not.toContain('ToggleSwitch')
    expect(list).toContain('mcp-allowance-state')
    expect(css).not.toContain('.mcp-row-actions')
    expect(css).toContain('.mcp-allowance-state[data-allowed')
  })

  it('keeps external tool error text and detailed configuration closed by default', () => {
    const detail = readFileSync(
      join(sourceRoot, 'features/mcp-servers/ui/McpServerDetailView.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/mcp-servers/ui/McpServerDetailView.css'),
      'utf8',
    )

    expect(detail).toContain('mcp-runtime-notice__technical')
    expect(detail).toContain('mcpServers.detail.configurationTechnical')
    expect(detail).not.toContain('mcp-runtime-error')
    expect(css).toContain('.mcp-runtime-notice__technical:not([open]) > :not(summary)')
    expect(css).toContain('.mcp-technical-details:not([open]) > :not(summary)')
  })

  it('keeps response instruction actions in selected detail and technical values closed', () => {
    const source = readFileSync(
      join(sourceRoot, 'features/prompts/ui/PromptsManager.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/prompts/ui/prompts.css'),
      'utf8',
    )

    expect(source).toContain('prompt-detail__technical')
    expect(source).toContain('WorkspaceUnavailable')
    expect(source).not.toContain('ReleaseWorkflowBacklink')
    expect(source).not.toContain('StatusBadge')
    expect(css).toContain('.prompt-detail__technical:not([open]) > :not(summary)')
    expect(css).not.toContain('border-left:')
  })

  it('keeps AI role changes in selected detail and answer principles readable', () => {
    const manager = readFileSync(
      join(sourceRoot, 'features/reactor-universe/ui/ReactorUniverseManager.tsx'),
      'utf8',
    )
    const promptViewer = readFileSync(
      join(sourceRoot, 'features/reactor-universe/ui/SystemPromptSection.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/reactor-universe/ui/ReactorUniverseManager.css'),
      'utf8',
    )

    expect(manager).toContain('agent-detail__technical')
    expect(manager).toContain('aria-pressed={selected}')
    expect(manager).not.toContain('agent-row__actions')
    expect(promptViewer).not.toContain('<pre')
    expect(css).toContain('.agent-detail__technical:not([open]) > :not(summary)')
    expect(css).not.toContain('border-left:')
  })

  it('keeps notification channel failures fail-closed without a local error card', () => {
    const source = readFileSync(
      join(sourceRoot, 'features/proactive-channels/ui/ProactiveChannelsManager.tsx'),
      'utf8',
    )
    const css = readFileSync(
      join(sourceRoot, 'features/proactive-channels/ui/proactive-channels.css'),
      'utf8',
    )

    expect(source).toContain('WorkspaceUnavailable')
    expect(source).toContain('OperationButton')
    expect(source).not.toContain('channel-load-error')
    expect(css).not.toContain('.channel-load-error')
    expect(css).not.toContain('border-left:')
  })

  it('keeps the Today page headed and prioritizes actionable work before release summary', () => {
    const source = readFileSync(
      join(sourceRoot, 'features/dashboard/ui/DashboardView.tsx'),
      'utf8',
    )

    expect(source).toContain("title={t('dashboard.todayTitle')}")
    expect(source.indexOf('<DashboardActionCards')).toBeLessThan(
      source.indexOf('<ReleaseOperationsSummary'),
    )
  })
})

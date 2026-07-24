import { ShieldAlert, ShieldCheck, Wrench } from 'lucide-react'
import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { InputGuardManager } from '../features/input-guard'
import { OutputGuardManager } from '../features/output-guard'
import { ToolPolicyManager } from '../features/tool-policy'
import { PageHeader, SectionErrorBoundary, Tabs } from '../shared/ui'
import './safety-rules.css'

type SafetyTab = 'input-guard' | 'output-guard' | 'tool-policy'

function SafetyWorkspacePanel({ description, children }: { description: string; children: ReactNode }) {
  return (
    <div className="safety-workspace__panel">
      <p className="safety-workspace__panel-description">{description}</p>
      {children}
    </div>
  )
}

function parseTab(params: URLSearchParams): SafetyTab {
  const raw = params.get('tab')
  if (raw === 'input-guard') return 'input-guard'
  if (raw === 'output-guard') return 'output-guard'
  if (raw === 'tool-policy') return 'tool-policy'
  return 'input-guard'
}

export function SafetyRulesPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = parseTab(searchParams)
  const tabs = [
    {
      value: 'input-guard',
      label: (
        <span className="safety-workspace__tab-label">
          <ShieldAlert size={15} aria-hidden="true" />
          {t('safetyRules.tabInputGuard')}
        </span>
      ),
      panel: (
        <SafetyWorkspacePanel description={t('nav.help.inputGuard')}>
          <InputGuardManager embedded />
        </SafetyWorkspacePanel>
      ),
    },
    {
      value: 'output-guard',
      label: (
        <span className="safety-workspace__tab-label">
          <ShieldCheck size={15} aria-hidden="true" />
          {t('safetyRules.tabOutputGuard')}
        </span>
      ),
      panel: (
        <SafetyWorkspacePanel description={t('nav.help.outputGuard')}>
          <OutputGuardManager embedded />
        </SafetyWorkspacePanel>
      ),
    },
    {
      value: 'tool-policy',
      label: (
        <span className="safety-workspace__tab-label">
          <Wrench size={15} aria-hidden="true" />
          {t('safetyRules.tabToolPolicy')}
        </span>
      ),
      panel: (
        <SafetyWorkspacePanel description={t('nav.help.toolPolicy')}>
          <ToolPolicyManager embedded />
        </SafetyWorkspacePanel>
      ),
    },
  ]

  return (
    <SectionErrorBoundary name="safety-rules">
      <div className="page safety-workspace">
        <PageHeader
          title={t('safetyRules.title')}
          description={t('safetyRules.description')}
        />
        <Tabs
          tabs={tabs}
          value={activeTab}
          onChange={(next) => {
            const params = new URLSearchParams(searchParams)
            params.set('tab', next)
            setSearchParams(params, { replace: true })
          }}
          ariaLabel={t('safetyRules.tabsLabel')}
        />
      </div>
    </SectionErrorBoundary>
  )
}

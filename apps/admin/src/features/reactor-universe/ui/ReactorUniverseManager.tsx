import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ChevronRight, Plus, X } from 'lucide-react'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { useToastStore } from '../../../shared/store/toast.store'
import { ConfirmDialog, OperationButton, PageHeader, TableSkeleton, WorkspaceUnavailable } from '../../../shared/ui'
import * as agentApi from '../api'
import type { AgentSpec } from '../types'
import { AgentSpecModal } from './AgentSpecModal'
import { SystemPromptSection } from './SystemPromptSection'
import './ReactorUniverseManager.css'

function modeLabel(mode: string, t: (key: string, options?: Record<string, unknown>) => string) {
  const knownModes = new Set(['REACT', 'STANDARD', 'PLAN_EXECUTE'])
  return knownModes.has(mode)
    ? t(`reactorUniverse.modes.${mode}`)
    : t('reactorUniverse.modes.unknown')
}

export function ReactorUniverseManager() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingAgent, setEditingAgent] = useState<AgentSpec | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AgentSpec | null>(null)

  const { data: agents = [], isLoading, isFetching, error: listError, refetch } = useQuery({
    queryKey: queryKeys.reactorUniverse.list(),
    queryFn: agentApi.listAgentSpecs,
  })
  const selectedAgent = agents.find((agent) => agent.id === selectedId) ?? null

  const deleteMutation = useMutation({
    mutationFn: agentApi.deleteAgentSpec,
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.reactorUniverse.all() })
      if (id === selectedId) setSelectedId(null)
      setDeleteTarget(null)
      addToast({ type: 'success', message: t('reactorUniverse.deleted') })
    },
    onError: () => {
      setDeleteTarget(null)
      addToast({ type: 'error', message: t('reactorUniverse.operationUnavailable') })
    },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      agentApi.updateAgentSpec(id, { enabled }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.reactorUniverse.all() })
    },
    onError: () => {
      addToast({ type: 'error', message: t('reactorUniverse.operationUnavailable') })
    },
  })

  function handleEdit(agent: AgentSpec) {
    setEditingAgent(agent)
    setModalOpen(true)
  }

  function handleCreate() {
    setEditingAgent(null)
    setModalOpen(true)
  }

  return (
    <div className="page-content reactor-universe-workspace">
      <PageHeader
        title={t('reactorUniverse.title')}
        description={t('reactorUniverse.description')}
        actions={
          !isLoading && !listError && agents.length > 0 ? (
            <OperationButton onClick={handleCreate}>
              <Plus aria-hidden="true" />
              {t('reactorUniverse.createAgent')}
            </OperationButton>
          ) : undefined
        }
      />

      {isLoading ? (
        <TableSkeleton rows={4} columns={3} />
      ) : listError ? (
        <WorkspaceUnavailable
          title={t('reactorUniverse.unavailableTitle')}
          description={t('reactorUniverse.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={refetch}
          isRetrying={isFetching}
          secondaryAction={{ label: t('reactorUniverse.openHealth'), to: '/health' }}
          guide={{
            title: t('reactorUniverse.recoveryGuideTitle'),
            steps: [
              t('reactorUniverse.recoveryCheckAccount'),
              t('reactorUniverse.recoveryCheckStatus'),
              t('reactorUniverse.recoveryRetry'),
            ],
            technicalLabel: t('reactorUniverse.technicalError'),
            technicalDetail: getErrorMessage(listError),
          }}
        />
      ) : agents.length === 0 ? (
        <section className="reactor-universe-empty" aria-label={t('reactorUniverse.emptyTitle')}>
          <p className="reactor-universe-empty__eyebrow">{t('reactorUniverse.emptyEyebrow')}</p>
          <h2>{t('reactorUniverse.emptyTitle')}</h2>
          <p className="reactor-universe-empty__description">{t('reactorUniverse.emptyDescription')}</p>
          <OperationButton onClick={handleCreate}>
            <Plus aria-hidden="true" />
            {t('reactorUniverse.createFirst')}
          </OperationButton>
          <details className="reactor-universe-empty__guide">
            <summary>
              <ChevronRight aria-hidden="true" size={15} />
              <span>{t('reactorUniverse.guide.disclosure')}</span>
            </summary>
            <HowItWorksGuide />
          </details>
        </section>
      ) : (
        <div className={`reactor-universe-workspace__body${selectedAgent ? ' reactor-universe-workspace__body--detail' : ''}`}>
          <section className="agent-directory" aria-label={t('reactorUniverse.directoryLabel')}>
            <header className="agent-directory__header" aria-hidden="true">
              <span>{t('reactorUniverse.columns.agent')}</span>
              <span>{t('reactorUniverse.columns.routing')}</span>
              <span>{t('reactorUniverse.columns.runtime')}</span>
            </header>
            {agents.map((agent) => (
              <AgentRow
                key={agent.id}
                agent={agent}
                selected={agent.id === selectedId}
                onSelect={() => setSelectedId(agent.id)}
              />
            ))}
          </section>

          {selectedAgent ? (
            <aside className="agent-detail" aria-labelledby="agent-detail-title">
              <header className="agent-detail__header">
                <div>
                  <div className="agent-detail__title-line">
                    <span
                      className={`status-dot ${selectedAgent.enabled ? 'status-dot--active' : 'status-dot--inactive'}`}
                      aria-label={selectedAgent.enabled ? t('reactorUniverse.status.enabled') : t('reactorUniverse.status.disabled')}
                      title={selectedAgent.enabled ? t('reactorUniverse.status.enabled') : t('reactorUniverse.status.disabled')}
                    />
                    <h2 id="agent-detail-title">{selectedAgent.name}</h2>
                  </div>
                  <p>{selectedAgent.description || t('reactorUniverse.noDescription')}</p>
                </div>
                <button className="agent-detail__close" type="button" onClick={() => setSelectedId(null)} aria-label={t('common.close')}>
                  <X aria-hidden="true" />
                </button>
              </header>

              <dl className="agent-detail__facts">
                <div>
                  <dt>{t('reactorUniverse.statusLabel')}</dt>
                  <dd>{selectedAgent.enabled ? t('reactorUniverse.status.enabled') : t('reactorUniverse.status.disabled')}</dd>
                </div>
                <div>
                  <dt>{t('reactorUniverse.answerMode')}</dt>
                  <dd>{modeLabel(selectedAgent.mode, t)}</dd>
                </div>
                <div>
                  <dt>{t('reactorUniverse.questionCriteria')}</dt>
                  <dd>{selectedAgent.keywords.join(', ') || t('reactorUniverse.noKeywords')}</dd>
                </div>
                <div>
                  <dt>{t('reactorUniverse.connectedFeatures')}</dt>
                  <dd>{t('reactorUniverse.toolCount', { count: selectedAgent.toolNames.length })}</dd>
                </div>
              </dl>

              <div className="agent-detail__actions">
                <OperationButton variant="secondary" onClick={() => handleEdit(selectedAgent)}>{t('common.edit')}</OperationButton>
                <OperationButton
                  variant="secondary"
                  onClick={() => toggleMutation.mutate({ id: selectedAgent.id, enabled: !selectedAgent.enabled })}
                  isOperating={toggleMutation.isPending}
                >
                  {selectedAgent.enabled ? t('reactorUniverse.stopUsing') : t('reactorUniverse.startUsing')}
                </OperationButton>
                <OperationButton variant="danger" onClick={() => setDeleteTarget(selectedAgent)}>{t('common.delete')}</OperationButton>
              </div>

              <section className="agent-detail__principles" aria-label={t('reactorUniverse.systemPrompt.toggle')}>
                <SystemPromptSection specId={selectedAgent.id} />
              </section>

              <details className="agent-detail__technical">
                <summary>{t('reactorUniverse.technicalDetails')}</summary>
                <dl>
                  <div>
                    <dt>{t('reactorUniverse.agentIdentifier')}</dt>
                    <dd><code>{selectedAgent.id}</code></dd>
                  </div>
                </dl>
              </details>
            </aside>
          ) : null}
        </div>
      )}

      {modalOpen ? (
        <AgentSpecModal
          agent={editingAgent}
          onClose={() => setModalOpen(false)}
        />
      ) : null}

      {deleteTarget ? (
        <ConfirmDialog
          title={t('reactorUniverse.deleteTitle')}
          message={t('reactorUniverse.deleteConfirm', { name: deleteTarget.name })}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
          danger
        />
      ) : null}
    </div>
  )
}

function AgentRow({
  agent,
  selected,
  onSelect,
}: {
  agent: AgentSpec
  selected: boolean
  onSelect: () => void
}) {
  const { t } = useTranslation()
  const stateLabel = agent.enabled ? t('reactorUniverse.status.enabled') : t('reactorUniverse.status.disabled')

  return (
    <button
      className={`agent-row ${!agent.enabled ? 'agent-row--disabled' : ''}`}
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
    >
      <span className="agent-row__identity">
        <span className="agent-row__title-line">
          <span
            className={`status-dot ${agent.enabled ? 'status-dot--active' : 'status-dot--inactive'}`}
            aria-label={stateLabel}
            title={stateLabel}
          />
          <strong>{agent.name}</strong>
          <span className="agent-row__status">{stateLabel}</span>
        </span>
        <span>{agent.description || t('reactorUniverse.noDescription')}</span>
      </span>

      <span className="agent-row__routing">
        <span>{agent.keywords.slice(0, 4).join(', ') || t('reactorUniverse.noKeywords')}</span>
        {agent.keywords.length > 4 ? (
          <small>{t('reactorUniverse.moreKeywords', { count: agent.keywords.length - 4 })}</small>
        ) : null}
      </span>

      <span className="agent-row__runtime">
        <strong>{modeLabel(agent.mode, t)}</strong>
        <span>{t('reactorUniverse.toolCount', { count: agent.toolNames.length })}</span>
      </span>
    </button>
  )
}

function HowItWorksGuide() {
  const { t } = useTranslation()
  const steps = [
    {
      title: t('reactorUniverse.guide.step1Title'),
      body: t('reactorUniverse.guide.step1Body'),
    },
    {
      title: t('reactorUniverse.guide.step2Title'),
      body: t('reactorUniverse.guide.step2Body'),
    },
    {
      title: t('reactorUniverse.guide.step3Title'),
      body: t('reactorUniverse.guide.step3Body'),
    },
  ]

  return (
    <div className="reactor-universe-guide">
      <ol className="reactor-universe-guide__steps">
        {steps.map((step) => (
          <li key={step.title} className="reactor-universe-guide__step">
            <p className="reactor-universe-guide__step-title">{step.title}</p>
            <p className="reactor-universe-guide__step-body">{step.body}</p>
          </li>
        ))}
      </ol>
      <p className="reactor-universe-guide__example-title">{t('reactorUniverse.guide.exampleTitle')}</p>
      <div className="reactor-universe-guide__example">
        <strong>{t('reactorUniverse.guide.exampleName')}</strong>
        <span>{t('reactorUniverse.guide.exampleBody')}</span>
      </div>
    </div>
  )
}

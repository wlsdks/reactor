import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { render, screen } from '../../../test/utils'
import { RELEASE_LANGSMITH_SYNC_PATH } from '../../releaseWorkflow'
import { ProductCapabilityBoundaryFlowList } from '../ProductCapabilityBoundaryFlowList'

describe('ProductCapabilityBoundaryFlowList', () => {
  it('renders release workflow steps from product capability evidence', () => {
    render(
      <MemoryRouter>
        <ProductCapabilityBoundaryFlowList
          evidence={['langsmith_eval_sync']}
          missingEvidence={['rag_ingestion_lifecycle']}
          ariaLabel="제품 경계 흐름"
          fallbackEvidenceLabel="근거 누락"
          statusIconOnly
        />
      </MemoryRouter>,
    )

    expect(screen.getByRole('list', { name: '제품 경계 흐름' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /dashboard\.release\.productBoundaryFlow\.langsmith/ })).toHaveAttribute(
      'href',
      RELEASE_LANGSMITH_SYNC_PATH,
    )
    expect(screen.getByText('확인 자료 1개 연결됨')).toBeInTheDocument()
    expect(screen.getByText('확인 자료 1개 더 필요')).toBeInTheDocument()
    expect(screen.queryByText('langsmith_eval_sync')).not.toBeInTheDocument()
    expect(screen.queryByText('rag_ingestion_lifecycle')).not.toBeInTheDocument()
  })

  it('uses a fallback when a missing boundary item has no report evidence', () => {
    render(
      <MemoryRouter>
        <ProductCapabilityBoundaryFlowList
          evidence={[]}
          missingEvidence={[]}
          ariaLabel="제품 경계 흐름"
          fallbackEvidenceLabel="경계 evidence 없음"
        />
      </MemoryRouter>,
    )

    expect(screen.getAllByText('경계 evidence 없음').length).toBeGreaterThan(0)
  })
})

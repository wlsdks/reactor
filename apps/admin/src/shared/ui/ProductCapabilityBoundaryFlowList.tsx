import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  listProductCapabilityBoundaryFlowItems,
  type ProductCapabilityBoundaryFlowItem,
} from '../lib/productCapabilityBoundaryFlow'
import { StatusBadge } from './StatusBadge'

export interface ProductCapabilityBoundaryFlowListProps {
  evidence: string[] | null | undefined
  missingEvidence: string[] | null | undefined
  ariaLabel: string
  as?: 'ol' | 'ul'
  className?: string
  itemClassName?: string | ((item: ProductCapabilityBoundaryFlowItem) => string)
  linkClassName?: string
  stepClassName?: string
  copyClassName?: string
  labelClassName?: string
  evidenceClassName?: string
  fallbackEvidenceLabel?: string
  statusIconOnly?: boolean
  statusPosition?: 'before-copy' | 'after-copy'
}

function productBoundaryFlowLabel(item: ProductCapabilityBoundaryFlowItem, t: (key: string) => string): string {
  switch (item.id) {
    case 'ingest':
      return t('dashboard.release.productBoundaryFlow.ingest')
    case 'cited_answer':
      return t('dashboard.release.productBoundaryFlow.citedAnswer')
    case 'feedback':
      return t('dashboard.release.productBoundaryFlow.feedback')
    case 'langsmith':
      return t('dashboard.release.productBoundaryFlow.langsmith')
    case 'slack':
      return t('dashboard.release.productBoundaryFlow.slack')
    case 'a2a':
      return t('dashboard.release.productBoundaryFlow.a2a')
    case 'provider':
      return t('dashboard.release.productBoundaryFlow.provider')
    case 'readiness':
      return t('dashboard.release.productBoundaryFlow.readiness')
  }
}

export function ProductCapabilityBoundaryFlowList({
  evidence,
  missingEvidence,
  ariaLabel,
  as: ListTag = 'ol',
  className,
  itemClassName,
  linkClassName,
  stepClassName,
  copyClassName,
  labelClassName,
  evidenceClassName,
  fallbackEvidenceLabel,
  statusIconOnly = false,
  statusPosition = 'before-copy',
}: ProductCapabilityBoundaryFlowListProps) {
  const { t } = useTranslation()
  const items = listProductCapabilityBoundaryFlowItems({ evidence, missingEvidence })

  return (
    <ListTag className={className} aria-label={ariaLabel}>
      {items.map((item) => {
        const statusLabel = item.status === 'passed'
          ? t('dashboard.release.productBoundaryFlow.passed')
          : t('dashboard.release.productBoundaryFlow.missing')
        const evidenceCount = item.status === 'passed'
          ? item.matchedEvidence.length
          : item.missingEvidence.length
        const evidenceLabel = evidenceCount > 0
          ? item.status === 'passed'
            ? t('common.releaseEvidenceConnected', {
                count: evidenceCount,
                defaultValue: `확인 자료 ${evidenceCount}개 연결됨`,
              })
            : t('common.releaseEvidenceNeeded', {
                count: evidenceCount,
                defaultValue: `확인 자료 ${evidenceCount}개 더 필요`,
              })
          : fallbackEvidenceLabel ?? statusLabel
        const resolvedItemClassName = typeof itemClassName === 'function'
          ? itemClassName(item)
          : itemClassName
        const copy = (
          <>
            <span className={labelClassName}>{productBoundaryFlowLabel(item, t)}</span>
            <span className={evidenceClassName}>
              {evidenceLabel}
            </span>
          </>
        )
        const statusBadge = (
          <StatusBadge
            status={item.status === 'passed' ? 'PASS' : 'WARN'}
            label={statusLabel}
            iconOnly={statusIconOnly}
          />
        )

        return (
          <li key={item.id} className={resolvedItemClassName}>
            <Link to={item.path} className={linkClassName}>
              <span className={stepClassName}>{item.stepNumber}</span>
              {statusPosition === 'before-copy' && statusBadge}
              {copyClassName ? <span className={copyClassName}>{copy}</span> : copy}
              {statusPosition === 'after-copy' && statusBadge}
            </Link>
          </li>
        )
      })}
    </ListTag>
  )
}

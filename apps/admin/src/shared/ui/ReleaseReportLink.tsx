import type { CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { releaseReportPath, releaseReportStepNumber } from '../releaseWorkflow'

const nestedReportLabelKeys: Record<string, string> = {
  feedback_promotion: 'common.releaseReports.feedback_promotion.reviewed_feedback',
}

export interface ReleaseReportLinkProps {
  report: string
  includeStep?: boolean
  stepClassName?: string
  stepStyle?: CSSProperties
}

export interface ReleaseReportListProps {
  reports: string[] | null | undefined
  includeStep?: boolean
  stepClassName?: string
  stepStyle?: CSSProperties
}

export interface ReleaseReportMapProps {
  reports: Record<string, string> | null | undefined
  includeStep?: boolean
  stepClassName?: string
  stepStyle?: CSSProperties
}

export function ReleaseReportLink({
  report,
  includeStep = false,
  stepClassName = 'data-mono',
  stepStyle,
}: ReleaseReportLinkProps) {
  const { i18n, t } = useTranslation()
  const path = releaseReportPath(report)
  const stepNumber = includeStep ? releaseReportStepNumber(report) : null
  const translationKey = nestedReportLabelKeys[report]
    ?? `common.releaseReports.${report}`
  const label = i18n.exists(translationKey)
    ? t(translationKey)
    : t('common.releaseReportFallback', { defaultValue: '연결된 점검 자료' })
  const linkLabel = t('common.openReleaseReport', {
    report: label,
    defaultValue: `${label} 화면 열기`,
  })
  const content = (
    <>
      {stepNumber !== null && (
        <span className={stepClassName} style={stepStyle}>
          {stepNumber}
        </span>
      )}
      <span className="release-report-link__label">{label}</span>
    </>
  )
  if (!path) return <span>{content}</span>
  return <Link className="release-report-link" to={path} aria-label={linkLabel}>{content}</Link>
}

export function ReleaseReportList({
  reports,
  includeStep = false,
  stepClassName,
  stepStyle,
}: ReleaseReportListProps) {
  const filtered = reports?.filter(Boolean) ?? []
  if (filtered.length === 0) return null

  return filtered.map((report, index) => (
    <span key={`${report}-${index}`}>
      {index > 0 && ', '}
      <ReleaseReportLink
        report={report}
        includeStep={includeStep}
        stepClassName={stepClassName}
        stepStyle={stepStyle}
      />
    </span>
  ))
}

export function ReleaseReportMap({
  reports,
  includeStep = false,
  stepClassName,
  stepStyle,
}: ReleaseReportMapProps) {
  const entries = Object.entries(reports ?? {})
  if (entries.length === 0) return null

  return entries.map(([report, file], index) => (
    <span key={`${report}-${file}`}>
      {index > 0 && ', '}
      <ReleaseReportLink
        report={report}
        includeStep={includeStep}
        stepClassName={stepClassName}
        stepStyle={stepStyle}
      />
      : {file}
    </span>
  ))
}

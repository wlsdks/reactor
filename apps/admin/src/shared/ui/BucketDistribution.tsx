import { CHART_WARM_SEQUENCE } from './ChartConfig'

interface Bucket {
  label: string
  count: number
}

interface BucketDistributionProps {
  buckets: Bucket[]
  title?: string
}

// Bucket gradient runs fast → slow via the shared CHART_WARM_SEQUENCE
// (amber → yellow → orange → rose → deep red). See ChartConfig for rationale.
function getBarColor(index: number, total: number): string {
  if (total <= 1) return CHART_WARM_SEQUENCE[0]
  const colorIndex = Math.round(
    (index / (total - 1)) * (CHART_WARM_SEQUENCE.length - 1),
  )
  return CHART_WARM_SEQUENCE[colorIndex]
}

export function BucketDistribution({ buckets, title }: BucketDistributionProps) {
  const maxCount = Math.max(...buckets.map((b) => b.count), 1)
  const totalCount = buckets.reduce((sum, b) => sum + b.count, 0)

  return (
    <div className="bucket-distribution">
      {title && (
        <h4 className="bucket-distribution__title">{title}</h4>
      )}
      <div className="bucket-distribution__list">
        {buckets.map((bucket, i) => {
          const pct = totalCount > 0 ? ((bucket.count / totalCount) * 100).toFixed(1) : '0.0'
          const widthPct = (bucket.count / maxCount) * 100

          return (
            <div key={bucket.label} className="bucket-distribution__item">
              <div className="bucket-distribution__header">
                <span className="bucket-distribution__label">{bucket.label}</span>
                <span className="bucket-distribution__value data-mono">
                  {bucket.count} <span className="bucket-distribution__pct">({pct}%)</span>
                </span>
              </div>
              <div className="bucket-distribution__bar-track">
                <div
                  className="bucket-distribution__bar"
                  style={{
                    width: `${widthPct}%`,
                    background: getBarColor(i, buckets.length),
                  }}
                  title={`${bucket.label}: ${bucket.count} (${pct}%)`}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

import { Link } from 'react-router-dom'

interface WorkspaceUnavailableProps {
  title: string
  description: string
  retryLabel: string
  retryingLabel: string
  onRetry: () => void | Promise<unknown>
  isRetrying?: boolean
  secondaryAction?: {
    label: string
    to: string
  }
  guide?: {
    title: string
    steps?: string[]
    technicalLabel?: string
    technicalDetail?: string | null
  }
}

export function WorkspaceUnavailable({
  title,
  description,
  retryLabel,
  retryingLabel,
  onRetry,
  isRetrying = false,
  secondaryAction,
  guide,
}: WorkspaceUnavailableProps) {
  return (
    <section className="workspace-unavailable" role="alert">
      <h2>{title}</h2>
      <p>{description}</p>
      <div className="workspace-unavailable__actions">
        <button className="btn btn-primary" type="button" onClick={() => void onRetry()} disabled={isRetrying}>
          {isRetrying ? retryingLabel : retryLabel}
        </button>
        {secondaryAction ? (
          <Link className="btn btn-secondary" to={secondaryAction.to}>{secondaryAction.label}</Link>
        ) : null}
      </div>
      {guide ? (
        <details className="workspace-unavailable__guide">
          <summary>{guide.title}</summary>
          {guide.steps && guide.steps.length > 0 ? (
            <ol>{guide.steps.map((step) => <li key={step}>{step}</li>)}</ol>
          ) : null}
          {guide.technicalDetail ? (
            <div className="workspace-unavailable__technical">
              {guide.technicalLabel ? <strong>{guide.technicalLabel}</strong> : null}
              <code>{guide.technicalDetail}</code>
            </div>
          ) : null}
        </details>
      ) : null}
    </section>
  )
}

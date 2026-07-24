import { ChevronRight } from 'lucide-react'
import { useId, useState } from 'react'
import type { ReactNode, SyntheticEvent } from 'react'
import './CollapsibleSection.css'

interface CollapsibleSectionProps {
  title: ReactNode
  defaultOpen?: boolean
  badge?: string | number
  /** Stable id assigned to the body region; used by the toggle's aria-controls.
   *  Defaults to a useId-generated id so consumers don't have to wire one. */
  bodyId?: string
  /** Fired with the next open state every time the toggle is clicked. */
  onToggle?: (open: boolean) => void
  children: ReactNode
}

export function CollapsibleSection({
  title,
  defaultOpen = false,
  badge,
  bodyId,
  onToggle,
  children,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  const autoId = useId()
  const resolvedBodyId = bodyId ?? `cs-body-${autoId}`

  function handleToggle(event: SyntheticEvent<HTMLDetailsElement>) {
    const next = event.currentTarget.open
    setOpen(next)
    onToggle?.(next)
  }

  return (
    <details className="collapsible-section" open={open} onToggle={handleToggle}>
      <summary className="collapsible-header">
        <ChevronRight className="collapsible-chevron" aria-hidden="true" />
        <span className="collapsible-title">{title}</span>
        {badge != null && <span className="collapsible-badge">{badge}</span>}
      </summary>
      <div id={resolvedBodyId} className="collapsible-body">
        {children}
      </div>
    </details>
  )
}

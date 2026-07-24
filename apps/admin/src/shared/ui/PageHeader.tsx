import type { ReactNode } from 'react'
import { useDocumentTitle } from '../lib/useDocumentTitle'

/**
 * PageHeader — shared primitive for top-of-page chrome on list/CRUD pages.
 *
 * Bakes in:
 * - `<h1>` semantic + `.page-title` gold style (WCAG 2.4.6 / 1.3.1)
 * - Optional breadcrumb slot rendered above the title row
 * - Optional description slot (string or ReactNode for multi-paragraph cases)
 * - Optional right-side actions slot
 * - `aria-label` defaulting to the page title
 * - Per BX audit P1-2: also drives `document.title` via {@link useDocumentTitle}
 *   so the browser tab reads `<title> · Reactor Admin` for every page that
 *   uses this primitive — no per-page wiring required.
 *
 * Per BX audit P0-4: do NOT use on Dashboard, Login, or *Detail pages — those
 * are sui generis. This primitive is for list / CRUD pages where the structure
 * genuinely repeats.
 *
 * Layout:
 *   <header class="page-header"> (flex column when breadcrumb present, otherwise reuses existing row layout)
 *     [breadcrumb row]
 *     <div class="page-header-row">  // only when breadcrumb present
 *       <div class="page-header-main">
 *         <h1 class="page-title">title</h1>
 *         <div class="page-header-description">description</div>
 *       </div>
 *       <div class="page-header-actions">actions</div>
 *     </div>
 *   </header>
 *
 * When no breadcrumb is provided, the header keeps the legacy flat layout to
 * preserve existing `.page-header { display: flex; justify-content: space-between }` styling.
 */
export interface PageHeaderProps {
  /** Page title — always rendered as <h1> with .page-title gold style. */
  title: string
  /**
   * Optional sub-text under the title. Accepts ReactNode so callers can pass
   * either a plain string or richer markup (e.g. multiple `<p>` tags) without
   * breaking the primitive.
   */
  description?: ReactNode
  /** Optional breadcrumb element rendered above the title row. */
  breadcrumb?: ReactNode
  /** Right-side actions slot (buttons, filters, etc). */
  actions?: ReactNode
  /** Optional aria-label override; defaults to `title`. */
  ariaLabel?: string
  /** Heading rank for embedded workspaces. Top-level pages keep the h1 default. */
  headingLevel?: 1 | 2
  /** Embedded section headers must not replace the owning page document title. */
  updateDocumentTitle?: boolean
}

export function PageHeader({
  title,
  description,
  breadcrumb,
  actions,
  ariaLabel,
  headingLevel = 1,
  updateDocumentTitle = true,
}: PageHeaderProps) {
  useDocumentTitle(title, updateDocumentTitle)
  const Heading = headingLevel === 2 ? 'h2' : 'h1'

  const main = (
    <div className="page-header-main">
      <Heading className="page-title">{title}</Heading>
      {description && <div className="page-header-description">{description}</div>}
    </div>
  )

  const actionsEl = actions ? <div className="page-header-actions">{actions}</div> : null

  if (breadcrumb) {
    return (
      <header
        className="page-header page-header--with-breadcrumb"
        aria-label={ariaLabel ?? title}
      >
        <div className="page-header-breadcrumb">{breadcrumb}</div>
        <div className="page-header-row">
          {main}
          {actionsEl}
        </div>
      </header>
    )
  }

  return (
    <header className="page-header" aria-label={ariaLabel ?? title}>
      {main}
      {actionsEl}
    </header>
  )
}

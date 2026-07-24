import type { CSSProperties, ReactNode } from 'react'

/**
 * Semantic intent for a Tag. Selects the color scheme via the matching
 * `.tag--<variant>` CSS rule in `src/index.css` / `src/shared/ui/shared-components.css`.
 *
 * - `neutral` (default): bare base `.tag` — muted text + elevated bg
 * - `success` / `error` / `warning` / `info`: semantic colors
 * - `knowledge` / `operational` / `hybrid` / `unknown`: answer-mode taxonomy
 * - `pill`: MCP-style rounder pill (elevated bg + primary text), commonly
 *           paired with a dynamic `borderLeft` color via `style`.
 */
export type TagVariant =
  | 'neutral'
  | 'success'
  | 'error'
  | 'warning'
  | 'info'
  | 'knowledge'
  | 'operational'
  | 'hybrid'
  | 'unknown'
  | 'pill'

export interface TagProps {
  variant?: TagVariant
  /** When true, applies the `tag--mono` modifier (mono font + smaller). */
  mono?: boolean
  /**
   * Inline style passthrough — used by MCP server tag lists to set a per-tag
   * `borderLeft` color. Prefer a variant when an intent applies; reach for
   * `style` only for dynamic per-instance colors.
   */
  style?: CSSProperties
  /** Stable key when rendered inside a list — re-exposed for ergonomic use. */
  'data-testid'?: string
  children: ReactNode
}

export function Tag({
  variant = 'neutral',
  mono = false,
  style,
  children,
  'data-testid': testId,
}: TagProps) {
  const cls = [
    'tag',
    variant !== 'neutral' && `tag--${variant}`,
    mono && 'tag--mono',
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <span className={cls} style={style} data-testid={testId}>
      {children}
    </span>
  )
}

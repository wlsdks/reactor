interface OverlayCloseButtonProps {
  onClick: () => void
  /** Accessible label. Pass a translated string. */
  label: string
}

/**
 * Standard close button for Modal / Drawer / ConfirmDialog overlays.
 * Renders a 16x16 SVG ✕ inside a 32x32 hit target pinned to the overlay's
 * top-right corner. Styling lives in `.overlay-close-btn` (shared-components.css)
 * and follows DESIGN.md (border ring, weight 510, no shadow on dark surfaces).
 */
export function OverlayCloseButton({ onClick, label }: OverlayCloseButtonProps) {
  return (
    <button
      type="button"
      className="overlay-close-btn"
      onClick={onClick}
      aria-label={label}
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        focusable="false"
      >
        <line x1="3.5" y1="3.5" x2="12.5" y2="12.5" />
        <line x1="12.5" y1="3.5" x2="3.5" y2="12.5" />
      </svg>
    </button>
  )
}

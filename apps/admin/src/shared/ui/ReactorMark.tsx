interface ReactorMarkProps {
  className?: string
  label?: string
}

/** A circular containment vessel with three control rods and a curved reactor core. */
export function ReactorMark({ className = '', label }: ReactorMarkProps) {
  return (
    <svg
      className={`reactor-mark ${className}`.trim()}
      viewBox="0 0 48 48"
      fill="none"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <circle cx="24" cy="24" r="19" stroke="currentColor" strokeWidth="2.75" />
      <path d="M16.75 15.5v11" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
      <path d="M24 11.75v13.5" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
      <path d="M31.25 15.5v11" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
      <path d="M13.75 27.5c.8 6.7 4.35 10.1 10.25 11.5 5.9-1.4 9.45-4.8 10.25-11.5" stroke="currentColor" strokeWidth="2.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

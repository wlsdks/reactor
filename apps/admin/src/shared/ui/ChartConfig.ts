/**
 * Shared recharts configuration: colorblind-safe categorical palette,
 * sequential scale, axis/grid presets, and helpers for stroke / marker
 * differentiation beyond color (Wong / Tol-inspired, dark-canvas tuned).
 *
 * Recharts SVG attributes (stroke, fill) cannot consume CSS custom
 * properties directly, so the palette mirrors `--chart-*` tokens from
 * `src/index.css` as literal hex values. Keep both in sync.
 *
 * See DESIGN.md §11 for the colorblind-safe rationale.
 */

// Categorical palette — primary ordering tuned for deuteranopia / protanopia
// distinction on the cool graphite canvas (#101419). Colors that risk visual
// collision (red ↔ green, blue ↔ violet) are placed at non-adjacent indices.
export const CHART_PALETTE = [
  '#8CB8FF', // mist blue   — chart-1 / --color-info
  '#5EBA8D', // emerald     — chart-2 / --color-success
  '#D6A451', // amber       — warning / --color-attention
  '#A78BFA', // violet      — chart-3 / --color-pending
  '#E07C7C', // rose        — chart-4 / --color-error
  '#38BDF8', // sky         — --color-processing
  '#F59E0B', // orange      — secondary warm
  '#94A3B8', // slate       — --color-neutral
] as const

export type ChartPaletteColor = (typeof CHART_PALETTE)[number]

// Sequential palette for ordered scales (heatmaps, gradient legends).
// Walks dark → light along the blue axis so it remains readable in greyscale.
export const CHART_SEQUENCE = [
  '#2A323D',
  '#4E668F',
  '#8CB8FF',
  '#B7D1FF',
  '#E4EEFF',
] as const

// Warm sequential palette for "fast → slow" / "good → bad" ordered buckets
// (e.g. latency distribution). Walks amber → yellow → orange → rose → deep red
// so adjacent buckets stay distinguishable while reinforcing severity intent.
// `--color-error` (#F87171) sits at index 3; index 4 is intentionally darker
// than the error token to mark the slowest / worst tail without colliding with
// the categorical palette.
export const CHART_WARM_SEQUENCE = [
  '#D6A451', // amber  — --color-warning
  '#E7B967', // light amber — warning progression
  '#F59E0B', // orange — secondary warm
  '#E07C7C', // rose   — --color-error
  '#DC2626', // deep red — slowest bucket (Tailwind red-600 parity)
] as const

const STROKE_DASH_CYCLE = ['', '4 2', '6 3', '2 2', '8 4 2 4'] as const

const MARKER_SHAPE_CYCLE = [
  'circle',
  'square',
  'triangle',
  'diamond',
  'cross',
] as const

export type MarkerShape = (typeof MARKER_SHAPE_CYCLE)[number]

/**
 * Stroke-dash helper for differentiating lines beyond color (CB safety).
 * Returns `undefined` for the first index so the primary series stays solid;
 * subsequent indices rotate through subtle dash patterns so a multi-line
 * chart remains parseable in greyscale or for protanopic / deuteranopic users.
 */
export function strokeDashFor(index: number): string | undefined {
  const dash = STROKE_DASH_CYCLE[index % STROKE_DASH_CYCLE.length]
  return dash === '' ? undefined : dash
}

/**
 * Marker shape rotation for scatter / line markers — pairs with palette index
 * so each series carries a redundant non-color cue.
 */
export function markerShapeFor(index: number): MarkerShape {
  return MARKER_SHAPE_CYCLE[index % MARKER_SHAPE_CYCLE.length]
}

/**
 * Resolve a palette color by series index, deterministic and bounded by
 * `CHART_PALETTE.length`. Use this rather than indexing the array directly
 * so out-of-range indices wrap predictably.
 */
export function paletteColor(index: number): ChartPaletteColor {
  return CHART_PALETTE[index % CHART_PALETTE.length]
}

// Common axis style props for the dark canvas. Spread onto recharts
// `<XAxis>` / `<YAxis>`. CSS variables resolve at SVG render time inside
// React DOM elements (recharts emits them through the JSX attribute path).
export const CHART_AXIS_STYLE = {
  stroke: 'var(--text-muted)',
  fontSize: 12,
  tickLine: { stroke: 'var(--border-standard)' },
  axisLine: { stroke: 'var(--border-standard)' },
  tick: { fill: 'var(--text-muted)', fontSize: 11 },
} as const

// CartesianGrid common style — horizontal-only by default keeps the canvas
// quiet on dense time-series.
export const CHART_GRID_STYLE = {
  stroke: 'var(--border-subtle)',
  strokeDasharray: '3 3',
} as const

export interface LineSeriesProps {
  stroke: string
  strokeDasharray: string | undefined
  dot: { r: number }
  activeDot: { r: number }
  strokeWidth: number
}

/**
 * Wrapper that consumes the palette + dash for a recharts `<Line>` series.
 * Pass an explicit `color` to override the palette assignment (e.g. for
 * status-meaning lines like SLA threshold or error rate).
 */
export function getLineSeriesProps(index: number, color?: string): LineSeriesProps {
  return {
    stroke: color ?? paletteColor(index),
    strokeDasharray: strokeDashFor(index),
    dot: { r: 3 },
    activeDot: { r: 5 },
    strokeWidth: 2,
  }
}

/**
 * Companion for `<Area>` — pairs palette color, stroke width, and a default
 * gradient id so callers can reference the matching `<linearGradient>` they
 * declare in `<defs>` (`gradId-<index>`).
 */
export function getAreaSeriesProps(index: number, color?: string) {
  const stroke = color ?? paletteColor(index)
  return {
    stroke,
    strokeDasharray: strokeDashFor(index),
    strokeWidth: 2,
  }
}

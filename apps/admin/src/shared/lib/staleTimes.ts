/**
 * Standard `staleTime` presets for TanStack Query consistency across the app.
 *
 * Why: prior to this module, individual hooks each picked their own magic
 * number (30_000 / 60_000 / 5 * 60_000 / Infinity). The four-way sprawl made
 * it impossible to reason about cache freshness or change a tier globally.
 * Use these presets instead of raw numbers when configuring `staleTime`.
 *
 * Tier guidance:
 * - REALTIME  (10s)  — dashboards, live counters, anything the operator
 *                       actively watches refresh.
 * - STANDARD  (30s)  — default for list / detail queries.
 * - SLOW      (60s)  — backend health (`/admin/doctor`), polling that hits
 *                       expensive backend checks.
 * - STATIC    (5m)   — slow-changing config (settings, analytics filters,
 *                       metric name lists).
 * - IMMUTABLE (∞)    — content keyed by an id that never mutates server-side
 *                       within a session (resolved system prompts, schemas).
 */
export const STALE_TIMES = {
  /** 10s — realtime/dashboard polling baseline */
  REALTIME: 10_000,
  /** 30s — default for most list/detail */
  STANDARD: 30_000,
  /** 60s — backend health, doctor */
  SLOW: 60_000,
  /** 5min — slow-changing config (settings, analytics) */
  STATIC: 5 * 60_000,
  /** Infinity — immutable (system prompts, schemas) */
  IMMUTABLE: Infinity,
} as const

export type StaleTimePreset = (typeof STALE_TIMES)[keyof typeof STALE_TIMES]

import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

// ─────────────────────────────────────────────────────────────────────────────
// Reduced-motion compliance gate (DESIGN.md §12).
//
// Every CSS file that ships a `transition:` or `animation:` declaration MUST
// also contain a `prefers-reduced-motion` block — either a targeted override
// for transforms/keyframes or, at minimum, a defensive marker that confirms
// the file was audited. The global safety net in `src/index.css` clamps
// duration, but each surface still owns its own audit.
// ─────────────────────────────────────────────────────────────────────────────

const SRC_ROOT = resolve(__dirname, '../../..')

function walkCss(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    const s = statSync(full)
    if (s.isDirectory()) {
      // Skip generated / vendor folders if present.
      if (entry === 'node_modules' || entry === 'dist' || entry === '__tests__') continue
      walkCss(full, acc)
    } else if (entry.endsWith('.css')) {
      acc.push(full)
    }
  }
  return acc
}

const cssFiles = walkCss(SRC_ROOT)
const motionRegex = /(?:^|\s)(?:transition|animation)\s*:/m
const reducedMotionRegex = /prefers-reduced-motion\s*:\s*reduce/

describe('reduced-motion compliance', () => {
  it('discovers at least one CSS file under src/', () => {
    expect(cssFiles.length).toBeGreaterThan(0)
  })

  it('src/index.css contains the global prefers-reduced-motion safety net', () => {
    const indexCss = readFileSync(join(SRC_ROOT, 'index.css'), 'utf8')
    expect(indexCss).toMatch(reducedMotionRegex)
    // Spec-mandated neutralisation knobs.
    expect(indexCss).toMatch(/transition-duration\s*:\s*0\.001ms\s*!important/)
    expect(indexCss).toMatch(/animation-duration\s*:\s*0\.001ms\s*!important/)
    expect(indexCss).toMatch(/animation-iteration-count\s*:\s*1\s*!important/)
    expect(indexCss).toMatch(/scroll-behavior\s*:\s*auto\s*!important/)
  })

  it('every CSS file with transitions/animations declares a prefers-reduced-motion block', () => {
    const offenders: string[] = []
    for (const file of cssFiles) {
      const body = readFileSync(file, 'utf8')
      if (motionRegex.test(body) && !reducedMotionRegex.test(body)) {
        offenders.push(file.replace(SRC_ROOT, 'src'))
      }
    }
    expect(offenders, `Files using transition/animation without a prefers-reduced-motion guard:\n${offenders.join('\n')}`).toEqual([])
  })
})

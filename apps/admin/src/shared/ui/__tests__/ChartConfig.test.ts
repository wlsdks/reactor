import { describe, it, expect } from 'vitest'
import {
  CHART_PALETTE,
  CHART_SEQUENCE,
  CHART_WARM_SEQUENCE,
  CHART_AXIS_STYLE,
  CHART_GRID_STYLE,
  paletteColor,
  strokeDashFor,
  markerShapeFor,
  getLineSeriesProps,
  getAreaSeriesProps,
} from '../ChartConfig'

describe('ChartConfig', () => {
  describe('CHART_PALETTE', () => {
    it('exposes 8 colorblind-safe categorical colors', () => {
      expect(CHART_PALETTE).toHaveLength(8)
    })

    it('every entry is a hex color string', () => {
      for (const c of CHART_PALETTE) {
        expect(c).toMatch(/^#[0-9A-Fa-f]{6}$/)
      }
    })

    it('contains the product status anchors (mist blue, emerald, amber, violet, rose)', () => {
      expect(CHART_PALETTE).toContain('#8CB8FF')
      expect(CHART_PALETTE).toContain('#5EBA8D')
      expect(CHART_PALETTE).toContain('#D6A451')
      expect(CHART_PALETTE).toContain('#A78BFA')
      expect(CHART_PALETTE).toContain('#E07C7C')
    })

    it('does not place red and green at adjacent indices (CB safety)', () => {
      const redIdx = CHART_PALETTE.indexOf('#E07C7C')
      const greenIdx = CHART_PALETTE.indexOf('#5EBA8D')
      expect(Math.abs(redIdx - greenIdx)).toBeGreaterThan(1)
    })
  })

  describe('CHART_SEQUENCE', () => {
    it('is an ordered light-to-dark scale of 5 stops', () => {
      expect(CHART_SEQUENCE).toHaveLength(5)
      for (const c of CHART_SEQUENCE) {
        expect(c).toMatch(/^#[0-9A-Fa-f]{6}$/)
      }
    })
  })

  describe('CHART_WARM_SEQUENCE', () => {
    it('is an ordered fast→slow warm scale of 5 stops', () => {
      expect(CHART_WARM_SEQUENCE).toHaveLength(5)
      for (const c of CHART_WARM_SEQUENCE) {
        expect(c).toMatch(/^#[0-9A-Fa-f]{6}$/)
      }
    })

    it('starts at warning amber and ends at a deep red tail', () => {
      expect(CHART_WARM_SEQUENCE[0]).toBe('#D6A451')
      expect(CHART_WARM_SEQUENCE[CHART_WARM_SEQUENCE.length - 1]).toBe('#DC2626')
    })

    it('places --color-error (rose) before the deep red tail for severity ramp', () => {
      const errorIdx = CHART_WARM_SEQUENCE.indexOf('#E07C7C')
      const tailIdx = CHART_WARM_SEQUENCE.length - 1
      expect(errorIdx).toBeGreaterThanOrEqual(0)
      expect(errorIdx).toBeLessThan(tailIdx)
    })
  })

  describe('paletteColor', () => {
    it('is deterministic per index', () => {
      expect(paletteColor(0)).toBe(paletteColor(0))
      expect(paletteColor(3)).toBe(paletteColor(3))
    })

    it('returns CHART_PALETTE[i] for in-range indices', () => {
      for (let i = 0; i < CHART_PALETTE.length; i++) {
        expect(paletteColor(i)).toBe(CHART_PALETTE[i])
      }
    })

    it('wraps modulo palette length for out-of-range indices', () => {
      expect(paletteColor(CHART_PALETTE.length)).toBe(CHART_PALETTE[0])
      expect(paletteColor(CHART_PALETTE.length + 2)).toBe(CHART_PALETTE[2])
    })
  })

  describe('strokeDashFor', () => {
    it('returns undefined for the first series so primary stays solid', () => {
      expect(strokeDashFor(0)).toBeUndefined()
    })

    it('rotates through dash patterns for subsequent indices', () => {
      expect(strokeDashFor(1)).toBe('4 2')
      expect(strokeDashFor(2)).toBe('6 3')
      expect(strokeDashFor(3)).toBe('2 2')
      expect(strokeDashFor(4)).toBe('8 4 2 4')
    })

    it('cycles back to solid at index 5 (length-5 rotation)', () => {
      expect(strokeDashFor(5)).toBeUndefined()
      expect(strokeDashFor(6)).toBe('4 2')
    })

    it('is deterministic per index', () => {
      for (let i = 0; i < 20; i++) {
        expect(strokeDashFor(i)).toBe(strokeDashFor(i))
      }
    })
  })

  describe('markerShapeFor', () => {
    it('rotates through five distinct shapes by index', () => {
      expect(markerShapeFor(0)).toBe('circle')
      expect(markerShapeFor(1)).toBe('square')
      expect(markerShapeFor(2)).toBe('triangle')
      expect(markerShapeFor(3)).toBe('diamond')
      expect(markerShapeFor(4)).toBe('cross')
    })

    it('wraps modulo cycle length for out-of-range indices', () => {
      expect(markerShapeFor(5)).toBe('circle')
      expect(markerShapeFor(7)).toBe('triangle')
    })

    it('is deterministic per index', () => {
      for (let i = 0; i < 20; i++) {
        expect(markerShapeFor(i)).toBe(markerShapeFor(i))
      }
    })
  })

  describe('getLineSeriesProps', () => {
    it('uses palette color when no override is given', () => {
      expect(getLineSeriesProps(0).stroke).toBe(CHART_PALETTE[0])
      expect(getLineSeriesProps(2).stroke).toBe(CHART_PALETTE[2])
    })

    it('honors an explicit color override', () => {
      const props = getLineSeriesProps(0, '#ABCDEF')
      expect(props.stroke).toBe('#ABCDEF')
    })

    it('attaches stroke-dash differentiation rotated by index', () => {
      expect(getLineSeriesProps(0).strokeDasharray).toBeUndefined()
      expect(getLineSeriesProps(1).strokeDasharray).toBe('4 2')
    })

    it('emits non-zero stroke width and visible dot config', () => {
      const props = getLineSeriesProps(0)
      expect(props.strokeWidth).toBeGreaterThan(0)
      expect(props.dot.r).toBeGreaterThan(0)
      expect(props.activeDot.r).toBeGreaterThan(props.dot.r)
    })
  })

  describe('getAreaSeriesProps', () => {
    it('mirrors palette color and dash rotation', () => {
      const props = getAreaSeriesProps(1)
      expect(props.stroke).toBe(CHART_PALETTE[1])
      expect(props.strokeDasharray).toBe('4 2')
    })

    it('honors explicit color override', () => {
      expect(getAreaSeriesProps(0, '#123456').stroke).toBe('#123456')
    })
  })

  describe('CHART_AXIS_STYLE / CHART_GRID_STYLE', () => {
    it('axis style references semantic tokens, not hardcoded colors', () => {
      expect(CHART_AXIS_STYLE.stroke).toBe('var(--text-muted)')
      expect(CHART_AXIS_STYLE.tickLine.stroke).toBe('var(--border-standard)')
      expect(CHART_AXIS_STYLE.axisLine.stroke).toBe('var(--border-standard)')
    })

    it('grid style uses the subtle border token with a dash pattern', () => {
      expect(CHART_GRID_STYLE.stroke).toBe('var(--border-subtle)')
      expect(CHART_GRID_STYLE.strokeDasharray).toBe('3 3')
    })
  })
})

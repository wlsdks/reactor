import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { TimestampWithZone } from '../TimestampWithZone'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, opts?: Record<string, unknown>) => {
        if (key === 'common.timezone.kst') return 'KST'
        if (key === 'common.timezone.utc') return 'UTC'
        if (key === 'common.timezone.tooltipUtc') return 'UTC (협정 세계시)'
        if (key === 'common.timezone.tooltipLocal') {
          return `${opts?.offset} ${opts?.name} (현지)`
        }
        return key
      },
    }),
  }
})

// Initialize the global i18next singleton so formatRelativeTimeKo can resolve
// its keys to actual Korean strings inside this suite.
await import('../../i18n/config')

const ISO_DATETIME_BODY = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/
const ISO_DATE_BODY = /^\d{4}-\d{2}-\d{2}$/

afterEach(() => {
  vi.restoreAllMocks()
})

describe('TimestampWithZone', () => {
  it('renders "-" for null input', () => {
    render(<TimestampWithZone value={null} />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('renders "-" for undefined input', () => {
    render(<TimestampWithZone value={undefined} />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('renders "-" for invalid date string', () => {
    render(<TimestampWithZone value="not a real date" />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('renders compact datetime format by default', () => {
    const { container } = render(
      <TimestampWithZone value="2026-04-20T17:44:00Z" showZone={false} />,
    )
    const text = container.textContent ?? ''
    expect(text).toMatch(ISO_DATETIME_BODY)
  })

  it('renders date-only format when format="date"', () => {
    const { container } = render(
      <TimestampWithZone value="2026-04-20T17:44:00Z" format="date" showZone={false} />,
    )
    const text = container.textContent ?? ''
    expect(text).toMatch(ISO_DATE_BODY)
  })

  it('formats as UTC when timezone="utc"', () => {
    const { container } = render(
      <TimestampWithZone value="2026-04-20T17:44:00Z" timezone="utc" showZone={false} />,
    )
    expect(container.textContent).toBe('2026-04-20 17:44')
  })

  it('shows the UTC zone label and tooltip when timezone="utc"', () => {
    const { container } = render(
      <TimestampWithZone value="2026-04-20T17:44:00Z" timezone="utc" />,
    )
    expect(screen.getByText('UTC')).toBeInTheDocument()
    const wrapper = container.querySelector('.timestamp-with-zone')
    expect(wrapper?.getAttribute('title')).toBe('UTC (협정 세계시)')
  })

  it('shows a non-empty local zone label and tooltip when timezone="local"', () => {
    const { container } = render(
      <TimestampWithZone value="2026-04-20T17:44:00Z" timezone="local" />,
    )
    const zoneLabel = container.querySelector('.timestamp-with-zone__zone')
    expect(zoneLabel).not.toBeNull()
    expect(zoneLabel?.textContent?.trim().length ?? 0).toBeGreaterThan(0)
    const wrapper = container.querySelector('.timestamp-with-zone')
    const title = wrapper?.getAttribute('title') ?? ''
    expect(title).toMatch(/현지/)
    expect(title).toMatch(/UTC[+-]\d{2}:\d{2}/)
  })

  it('omits the zone suffix when showZone={false}', () => {
    const { container } = render(
      <TimestampWithZone value="2026-04-20T17:44:00Z" showZone={false} />,
    )
    expect(container.querySelector('.timestamp-with-zone__zone')).toBeNull()
  })

  it('renders a relative string when format="relative"', () => {
    // Anchor "now" so the relative diff is deterministic.
    const fixedNow = new Date('2026-04-20T18:00:00Z').getTime()
    vi.spyOn(Date, 'now').mockReturnValue(fixedNow)
    render(
      <TimestampWithZone
        value="2026-04-20T17:44:00Z"
        format="relative"
        showZone={false}
      />,
    )
    // 16 minutes earlier → "16분 전"
    expect(screen.getByText('16분 전')).toBeInTheDocument()
  })

  it('uses a numeric offset fallback for IANA zones not in the short table', () => {
    const { container } = render(
      <TimestampWithZone
        value="2026-04-20T17:44:00Z"
        timezone={'Etc/GMT-7' as 'local'}
      />,
    )
    const zoneLabel = container.querySelector('.timestamp-with-zone__zone')?.textContent ?? ''
    // Either the IANA short name from Intl, or a UTC±HH:MM fallback.
    expect(zoneLabel.length).toBeGreaterThan(0)
  })
})

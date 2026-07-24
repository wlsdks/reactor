import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Home, Compass, Command } from 'lucide-react'
import { useDocumentTitle } from '../shared/lib'

/**
 * Friendly 404 page — N-21 BX audit follow-up.
 *
 * Replaces the bare EmptyState with a brand-correct landing surface:
 *  - Large "404" numerical mark for instant recognition
 *  - Karrot/Toss-tone headline + description (no formal "~합니다")
 *  - Three recovery suggestions (dashboard / sidebar / ⌘K palette)
 *  - Primary "처음으로" action + secondary "이전 페이지" fallback
 *
 * Design notes:
 *  - Uses existing CSS tokens only (no new global classes); layout uses
 *    inline styles built from `--space-*` / `--text-*` / color tokens so we
 *    don't grow `index.css` for a single page.
 *  - Avoids gradients, neon, or futuristic chrome per the "Quiet Authority"
 *    direction in CLAUDE.md / DESIGN.md.
 */
export function NotFoundPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  // BX audit P1-2: 404 page also gets a brand-correct browser tab title.
  useDocumentTitle(t('error.notFoundPage'))

  const suggestions = [
    {
      icon: <Home size={18} aria-hidden="true" />,
      title: t('notFound.suggestions.dashboard.title'),
      description: t('notFound.suggestions.dashboard.description'),
    },
    {
      icon: <Compass size={18} aria-hidden="true" />,
      title: t('notFound.suggestions.sidebar.title'),
      description: t('notFound.suggestions.sidebar.description'),
    },
    {
      icon: <Command size={18} aria-hidden="true" />,
      title: t('notFound.suggestions.search.title'),
      description: t('notFound.suggestions.search.description'),
    },
  ]

  return (
    <div className="page" data-testid="not-found-page">
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          padding: 'var(--space-12) var(--space-6)',
          gap: 'var(--space-4)',
          maxWidth: '640px',
          margin: '0 auto',
        }}
      >
        <div
          aria-hidden="true"
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '96px',
            lineHeight: 1,
            fontWeight: 'var(--font-weight-emphasis)',
            color: 'var(--accent)',
            letterSpacing: '-0.04em',
            marginBottom: 'var(--space-2)',
          }}
        >
          404
        </div>

        <h1
          style={{
            fontSize: 'var(--text-xl)',
            fontWeight: 'var(--font-weight-emphasis)',
            color: 'var(--text-primary)',
            margin: 0,
          }}
        >
          {t('notFound.title')}
        </h1>

        <p
          style={{
            fontSize: 'var(--text-sm)',
            color: 'var(--text-secondary)',
            lineHeight: 1.6,
            maxWidth: '460px',
            margin: 0,
          }}
        >
          {t('notFound.description')}
        </p>

        <div
          style={{
            display: 'flex',
            gap: 'var(--space-2)',
            marginTop: 'var(--space-2)',
            flexWrap: 'wrap',
            justifyContent: 'center',
          }}
        >
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => navigate('/')}
          >
            {t('notFound.actions.goHome')}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => navigate(-1)}
          >
            {t('notFound.actions.goBack')}
          </button>
        </div>

        <ul
          style={{
            listStyle: 'none',
            padding: 0,
            margin: 'var(--space-6) 0 0',
            display: 'grid',
            gap: 'var(--space-2)',
            width: '100%',
            textAlign: 'left',
          }}
          aria-label={t('notFound.suggestionsLabel')}
        >
          {suggestions.map((item) => (
            <li
              key={item.title}
              style={{
                display: 'flex',
                gap: 'var(--space-3)',
                alignItems: 'flex-start',
                padding: 'var(--space-3) var(--space-4)',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius)',
              }}
            >
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '32px',
                  height: '32px',
                  borderRadius: 'var(--radius)',
                  background: 'var(--accent-dim)',
                  color: 'var(--accent)',
                  flexShrink: 0,
                }}
              >
                {item.icon}
              </span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <span
                  style={{
                    fontSize: 'var(--text-sm)',
                    color: 'var(--text-primary)',
                    fontWeight: 'var(--font-weight-emphasis)',
                  }}
                >
                  {item.title}
                </span>
                <span
                  style={{
                    fontSize: 'var(--text-xs)',
                    color: 'var(--text-secondary)',
                    lineHeight: 1.5,
                  }}
                >
                  {item.description}
                </span>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

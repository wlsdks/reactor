import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth, useAuthForm } from '../features/auth'
import { consumeLogoutReason, type LogoutReason } from '../features/auth/logoutReason'
import { AUTH_SELF_REGISTRATION_ENABLED } from '../shared/lib/constants'
import { useDocumentTitle } from '../shared/lib'
import { LoadingSpinner, NetworkStatus, ReactorMark } from '../shared/ui'

function EyeIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function EyeOffIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
      <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  )
}

function PasswordInput({
  id,
  value,
  onChange,
  autoComplete,
  placeholder,
  required,
  ariaInvalid,
  ariaDescribedBy,
}: {
  id: string
  value: string
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  autoComplete: string
  placeholder?: string
  required?: boolean
  ariaInvalid?: boolean
  ariaDescribedBy?: string
}) {
  const { t } = useTranslation()
  const [visible, setVisible] = useState(false)

  return (
    <div className="password-field">
      <input
        id={id}
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={onChange}
        autoComplete={autoComplete}
        placeholder={placeholder}
        required={required}
        aria-invalid={ariaInvalid || undefined}
        aria-describedby={ariaDescribedBy}
      />
      <button
        type="button"
        className="password-toggle"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? t('auth.hidePassword') : t('auth.showPassword')}
      >
        {visible ? <EyeOffIcon /> : <EyeIcon />}
      </button>
    </div>
  )
}

export function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { isAuthenticated, isAdmin, isAuthRequired, isLoading, error, concurrentSession, login: authLogin, loginAsDemo } = useAuth()
  const form = useAuthForm()
  const [demoLoggingIn, setDemoLoggingIn] = useState(false)
  const firstInputRef = useRef<HTMLInputElement>(null)

  // Read-and-clear the logout reason once on mount. This drives the banner
  // that explains *why* the user was bounced back to /login (cross-tab
  // logout, 401 session expiry). Without it, users see no context.
  const [logoutReason] = useState<LogoutReason | null>(() => consumeLogoutReason())

  // BX audit P1-2: distinct browser tab title for the login screen.
  useDocumentTitle(t('auth.login'))

  useEffect(() => {
    if (!isLoading && (!isAuthRequired || (isAuthenticated && isAdmin))) {
      navigate('/', { replace: true })
    }
  }, [isLoading, isAuthRequired, isAuthenticated, isAdmin, navigate])

  useEffect(() => {
    firstInputRef.current?.focus()
  }, [form.mode])

  async function onLogin(e: React.FormEvent) {
    e.preventDefault()
    const ok = await form.handleLogin()
    if (ok) navigate('/', { replace: true })
  }

  async function onRegister(e: React.FormEvent) {
    e.preventDefault()
    const ok = await form.handleRegister()
    if (ok) navigate('/', { replace: true })
  }

  async function onDemoLogin() {
    setDemoLoggingIn(true)
    try {
      const ok = await loginAsDemo()
      if (ok) navigate('/', { replace: true })
    } finally {
      setDemoLoggingIn(false)
    }
  }

  if (isLoading) {
    return (
      <div className="loading-fullscreen">
        <LoadingSpinner size="lg" />
        <span className="loading-fullscreen-text">{t('app.authenticating')}</span>
      </div>
    )
  }

  const hasError = !!(error || form.localError)
  const errorId = 'login-error'

  const logoutReasonMessage =
    logoutReason === 'cross-tab'
      ? t('auth.logoutReason.crossTab')
      : logoutReason === 'session-expired'
        ? t('auth.logoutReason.sessionExpired')
        : null

  return (
    <>
      <NetworkStatus />
      <div className="login-page">
        <div className="login-card">
          {/* Logo + Title */}
          <div className="login-header">
            <ReactorMark className="login-logo" label="Reactor" />
            <h1 className="login-title">Reactor <span>Admin</span></h1>
          </div>

          {/* Mode tabs */}
          {AUTH_SELF_REGISTRATION_ENABLED && (
            <div className="login-tabs" role="tablist" aria-label={t('auth.modeTabs')}>
              <button
                className="login-tab"
                role="tab"
                aria-selected={form.mode === 'login'}
                onClick={() => form.switchMode('login')}
              >
                {t('auth.login')}
              </button>
              <button
                className="login-tab"
                role="tab"
                aria-selected={form.mode === 'register'}
                onClick={() => form.switchMode('register')}
              >
                {t('auth.register')}
              </button>
            </div>
          )}

          {/* Logout-reason banner: surfaces *why* the user is back on /login
              after a cross-tab logout or 401 session-expiry. Suppressed once
              the user starts interacting (any active error overrides it). */}
          {logoutReasonMessage && !hasError && (
            <div
              className="alert alert-info"
              role="status"
              aria-live="polite"
              data-testid="logout-reason-banner"
            >
              {logoutReasonMessage}
            </div>
          )}

          {/* Login form */}
          {form.mode === 'login' || !AUTH_SELF_REGISTRATION_ENABLED ? (
            <form className="login-form" onSubmit={onLogin} aria-busy={isLoading} noValidate>
              {/* Error alert */}
              {error && (
                <div id={errorId} className="alert alert-error" role="alert">
                  {error}
                  {concurrentSession && (
                    <button
                      type="button"
                      className="btn btn-sm btn-outline"
                      style={{ marginTop: 'var(--space-2)', width: '100%' }}
                      onClick={async () => {
                        const ok = await authLogin(form.email, form.password)
                        if (ok) navigate('/', { replace: true })
                      }}
                    >
                      {t('auth.forceLogin')}
                    </button>
                  )}
                </div>
              )}
              {form.localError && (
                <div id={errorId} className="alert alert-error" role="alert">{form.localError}</div>
              )}
              {form.registerMessage && (
                <div className="alert alert-success" role="status">{form.registerMessage}</div>
              )}

              <div className="form-group">
                <label htmlFor="email">{t('auth.email')}</label>
                <input
                  ref={firstInputRef}
                  id="email"
                  type="email"
                  value={form.email}
                  onChange={(e) => form.setEmail(e.target.value)}
                  autoComplete="email"
                  placeholder={t('auth.emailPlaceholder')}
                  required
                  aria-invalid={hasError || undefined}
                  aria-describedby={hasError ? errorId : undefined}
                />
              </div>

              <div className="form-group">
                <label htmlFor="password">{t('auth.password')}</label>
                <PasswordInput
                  id="password"
                  value={form.password}
                  onChange={(e) => form.setPassword(e.target.value)}
                  autoComplete="current-password"
                  placeholder={t('auth.passwordPlaceholder')}
                  required
                  ariaInvalid={hasError}
                  ariaDescribedBy={hasError ? errorId : undefined}
                />
              </div>

              <button className="btn btn-primary btn-full" type="submit" disabled={isLoading}>
                {isLoading ? <LoadingSpinner size="sm" /> : t('auth.login')}
              </button>

              {import.meta.env.DEV && (
                <button
                  className="btn btn-ghost btn-dev-login btn-full"
                  type="button"
                  disabled={demoLoggingIn || isLoading}
                  onClick={() => { void onDemoLogin() }}
                >
                  {demoLoggingIn ? <LoadingSpinner size="sm" /> : (t('auth.demoLogin') || '데모 로그인 (Admin)')}
                </button>
              )}
            </form>
          ) : (
            /* Register form */
            <form className="login-form" onSubmit={onRegister} aria-busy={form.submitting} noValidate>
              {form.localError && (
                <div id={errorId} className="alert alert-error" role="alert">{form.localError}</div>
              )}

              <div className="form-group">
                <label htmlFor="register-name">{t('auth.name')}</label>
                <input
                  ref={firstInputRef}
                  id="register-name"
                  value={form.name}
                  onChange={(e) => form.setName(e.target.value)}
                  autoComplete="name"
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="register-email">{t('auth.email')}</label>
                <input
                  id="register-email"
                  type="email"
                  value={form.email}
                  onChange={(e) => form.setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="register-password">{t('auth.password')}</label>
                <PasswordInput
                  id="register-password"
                  value={form.password}
                  onChange={(e) => form.setPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="register-confirm-password">{t('auth.confirmPassword')}</label>
                <PasswordInput
                  id="register-confirm-password"
                  value={form.confirmPassword}
                  onChange={(e) => form.setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                />
              </div>

              <button className="btn btn-primary btn-full" type="submit" disabled={form.submitting}>
                {form.submitting ? <LoadingSpinner size="sm" /> : t('auth.register')}
              </button>
            </form>
          )}

          <p className="login-hint">{t('auth.adminOnlyHint')}</p>
        </div>
      </div>
    </>
  )
}

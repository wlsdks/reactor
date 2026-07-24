import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from './context'
import * as authApi from './api'
import { AUTH_SELF_REGISTRATION_ENABLED, PASSWORD_MIN_LENGTH } from '../../shared/lib/constants'
import { getErrorMessage } from '../../shared/lib/getErrorMessage'

type AuthMode = 'login' | 'register'

export function useAuthForm() {
  const { t } = useTranslation()
  const { login, clearError } = useAuth()

  const [mode, setMode] = useState<AuthMode>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const [registerMessage, setRegisterMessage] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function clearErrors() {
    setLocalError(null)
    setRegisterMessage(null)
    clearError()
  }

  function switchMode(newMode: AuthMode) {
    setMode(newMode)
    clearErrors()
  }

  async function handleLogin(): Promise<boolean> {
    clearErrors()
    return login(email, password)
  }

  async function handleRegister(): Promise<boolean> {
    clearErrors()
    if (!AUTH_SELF_REGISTRATION_ENABLED) {
      setLocalError(t('auth.registrationDisabled'))
      return false
    }
    if (!name.trim()) { setLocalError(t('auth.nameRequired')); return false }
    if (password.length < PASSWORD_MIN_LENGTH) { setLocalError(t('auth.passwordMinLength')); return false }
    if (password !== confirmPassword) { setLocalError(t('auth.passwordMismatch')); return false }

    setSubmitting(true)
    try {
      await authApi.register({ name: name.trim(), email: email.trim(), password })
      // After registration, try to login directly
      const ok = await login(email, password)
      if (ok) return true
      setRegisterMessage(t('auth.registerSuccess'))
      setMode('login')
      setPassword('')
      setConfirmPassword('')
      return false
    } catch (e) {
      setLocalError(getErrorMessage(e))
      return false
    } finally {
      setSubmitting(false)
    }
  }

  function clearErrorOnChange<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value)
      if (localError) setLocalError(null)
    }
  }

  return {
    mode, name, email, password, confirmPassword,
    localError, registerMessage, submitting,
    setName: clearErrorOnChange(setName),
    setEmail: clearErrorOnChange(setEmail),
    setPassword: clearErrorOnChange(setPassword),
    setConfirmPassword: clearErrorOnChange(setConfirmPassword),
    switchMode, handleLogin, handleRegister,
  }
}

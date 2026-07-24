import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import * as authApi from './api'
import { PASSWORD_MIN_LENGTH } from '../../shared/lib/constants'
import { getErrorMessage } from '../../shared/lib/getErrorMessage'

export function useChangePassword() {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  function open() {
    setIsOpen(true)
    setCurrentPassword('')
    setNewPassword('')
    setConfirmPassword('')
    setError(null)
    setSuccess(null)
  }

  function close() {
    setIsOpen(false)
  }

  async function submit() {
    setError(null)
    setSuccess(null)

    if (!currentPassword || !newPassword) {
      setError(t('auth.passwordRequired'))
      return
    }
    if (newPassword.length < PASSWORD_MIN_LENGTH) {
      setError(t('auth.passwordMinLength'))
      return
    }
    if (newPassword !== confirmPassword) {
      setError(t('auth.passwordMismatch'))
      return
    }

    setIsSubmitting(true)
    try {
      await authApi.changePassword({ currentPassword, newPassword })
      setSuccess(t('auth.passwordChanged'))
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setIsSubmitting(false)
    }
  }

  function clearErrorOnChange<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value)
      if (error) setError(null)
      if (success) setSuccess(null)
    }
  }

  return {
    isOpen,
    currentPassword,
    newPassword,
    confirmPassword,
    error,
    success,
    isSubmitting,
    setCurrentPassword: clearErrorOnChange(setCurrentPassword),
    setNewPassword: clearErrorOnChange(setNewPassword),
    setConfirmPassword: clearErrorOnChange(setConfirmPassword),
    open,
    close,
    submit,
  }
}

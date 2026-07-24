import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import ko from './ko.json'

// One-shot cleanup of legacy localStorage key from the EN/KO toggle era.
try {
  localStorage.removeItem('reactor-admin-lang')
} catch {
  // localStorage unavailable in some test environments
}

i18n
  .use(initReactI18next)
  .init({
    resources: {
      ko: { translation: ko },
    },
    lng: 'ko',
    // No fallbackLng: only one resource. Missing keys render as the key string.
    // escapeValue: false is intentional — React already escapes interpolated values.
    interpolation: { escapeValue: false },
  })

try { document.documentElement.lang = 'ko' } catch { /* noop */ }

export default i18n

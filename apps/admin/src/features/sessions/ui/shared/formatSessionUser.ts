import { formatUserId } from '../../../../shared/lib/formatters'

type Translate = (key: string, options?: Record<string, unknown>) => string

/**
 * Keep opaque account keys out of the primary operator interface while
 * preserving a stable, human-readable label for each conversation owner.
 */
export function formatSessionUser(t: Translate, userId: string, email?: string | null): string {
  if (email) return email
  if (userId === 'local-user') return t('conversations.users.localUser')

  const generatedUser = /^user[_-]?(\d+)$/i.exec(userId)
  if (generatedUser) return t('conversations.users.anonymousUser', { id: generatedUser[1] })

  const compactId = formatUserId(userId).replaceAll('_', ' ').replace(/\s+…$/, '…')
  return t('conversations.users.anonymousUser', { id: compactId })
}

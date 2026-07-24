import { useTranslation } from 'react-i18next'
import { createAuditLabelLocalizers } from '../auditLabels'

export { createAuditLabelLocalizers } from '../auditLabels'
export type { AuditResourceReference } from '../auditLabels'

export function useAuditLabelLocalizers() {
  const { t } = useTranslation()
  return createAuditLabelLocalizers(t)
}

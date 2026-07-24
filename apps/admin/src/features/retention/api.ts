import { api } from '../../shared/api/client'
import type { RetentionPolicy } from './types'

export const getRetentionPolicy = async (): Promise<RetentionPolicy> => {
  return api.get('admin/retention').json<RetentionPolicy>()
}

export const updateRetentionPolicy = async (
  policy: Partial<RetentionPolicy>,
): Promise<RetentionPolicy> => {
  return api.put('admin/retention', { json: policy }).json<RetentionPolicy>()
}

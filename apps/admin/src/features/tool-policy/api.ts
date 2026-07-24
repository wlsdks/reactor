import type { ToolPolicyState, ToolPolicyRuleSet, UpdateToolPolicyRequest } from './types'
import { api } from '../../shared/api/client'

export const getPolicy = (): Promise<ToolPolicyState> =>
  api.get('tool-policy').json()

export const updatePolicy = (request: UpdateToolPolicyRequest): Promise<ToolPolicyRuleSet> =>
  api.put('tool-policy', { json: request }).json()

export const deletePolicy = (): Promise<void> =>
  api.delete('tool-policy').json()

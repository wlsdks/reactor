import { api } from '../../shared/api/client'
import type { McpSecurityPolicyRuleSet, McpSecurityPolicyState, UpdateMcpSecurityPolicyRequest } from './types'

function normalizeRuleSet(raw: McpSecurityPolicyRuleSet): McpSecurityPolicyRuleSet {
  return {
    ...raw,
    allowedServerNames: [...raw.allowedServerNames].map((item) => item.trim()).filter(Boolean).sort(),
  }
}

export const getMcpSecurityPolicy = async (): Promise<McpSecurityPolicyState> => {
  const data = await api.get('mcp/security').json<McpSecurityPolicyState>()
  return {
    effective: normalizeRuleSet(data.effective),
    stored: data.stored ? normalizeRuleSet(data.stored) : null,
    configDefault: normalizeRuleSet(data.configDefault),
  }
}

export const updateMcpSecurityPolicy = async (
  request: UpdateMcpSecurityPolicyRequest,
): Promise<McpSecurityPolicyRuleSet> => {
  const data = await api.put('mcp/security', { json: request }).json<McpSecurityPolicyRuleSet>()
  return normalizeRuleSet(data)
}

export const deleteMcpSecurityPolicy = (): Promise<void> =>
  api.delete('mcp/security').json()

export interface McpSecurityPolicyRuleSet {
  allowedServerNames: string[]
  maxToolOutputLength: number
  createdAt: number
  updatedAt: number
}

export interface McpSecurityPolicyState {
  effective: McpSecurityPolicyRuleSet
  stored: McpSecurityPolicyRuleSet | null
  configDefault: McpSecurityPolicyRuleSet
}

export interface UpdateMcpSecurityPolicyRequest {
  allowedServerNames: string[]
  maxToolOutputLength: number
}

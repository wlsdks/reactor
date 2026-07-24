import { http, HttpResponse } from 'msw'
import type { RawRole } from '../../features/rbac/types'

function buildPermissions(entries: Array<[string, string]>): string[] {
  return entries.map(([resource, action]) => `${resource}:${action}`)
}

export const mockRoles: RawRole[] = [
  {
    role: 'ADMIN',
    scope: 'FULL',
    permissions: buildPermissions([
      ['persona', 'read'], ['persona', 'write'], ['prompt', 'read'], ['prompt', 'write'],
      ['session', 'read'], ['session', 'export'], ['feedback', 'read'], ['guard', 'read'],
      ['guard', 'write'], ['mcp', 'read'], ['mcp', 'write'], ['scheduler', 'read'],
      ['scheduler', 'write'], ['eval', 'read'], ['eval', 'write'], ['audit', 'read'],
      ['audit', 'export'], ['tenant', 'read'], ['tenant', 'write'], ['tenant', 'export'],
      ['user', 'read'], ['user', 'write'], ['settings', 'read'], ['settings', 'write'],
      ['slack', 'write'], ['agent-spec', 'read'], ['agent-spec', 'write'],
    ]),
  },
  {
    role: 'ADMIN_DEVELOPER',
    scope: 'DEVELOPER',
    permissions: buildPermissions([
      ['persona', 'read'], ['persona', 'write'], ['prompt', 'read'], ['prompt', 'write'],
      ['session', 'read'], ['feedback', 'read'], ['guard', 'read'], ['guard', 'write'],
      ['mcp', 'read'], ['mcp', 'write'], ['scheduler', 'read'], ['scheduler', 'write'],
      ['audit', 'read'], ['agent-spec', 'read'], ['agent-spec', 'write'],
    ]),
  },
  {
    role: 'ADMIN_MANAGER',
    scope: 'MANAGER',
    permissions: buildPermissions([
      ['session', 'read'], ['session', 'export'], ['feedback', 'read'],
      ['audit', 'read'],
      ['persona', 'read'],
    ]),
  },
  {
    role: 'USER',
    scope: null,
    permissions: buildPermissions([
      ['chat', 'use'], ['persona', 'select'],
    ]),
  },
]

export const rbacHandlers = [
  http.get('/api/admin/rbac/roles', () => {
    return HttpResponse.json(mockRoles)
  }),

  http.put('/api/admin/rbac/users/:userId/role', async ({ request }) => {
    const body = await request.json() as { role: string }
    void body
    return new HttpResponse(null, { status: 200 })
  }),
]

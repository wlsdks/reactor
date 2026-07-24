import { http, HttpResponse } from 'msw'

function base64url(obj: Record<string, unknown>): string {
  return btoa(JSON.stringify(obj))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

export const mockUser = {
  id: 'user-1',
  username: 'admin',
  role: 'ADMIN' as const,
  email: 'admin@example.com',
  createdAt: '2024-01-01T00:00:00Z',
}

const mockToken = [
  base64url({ alg: 'HS256', typ: 'JWT' }),
  base64url({
    sub: mockUser.id,
    email: mockUser.email,
    name: 'Admin',
    role: mockUser.role,
    exp: Math.floor(Date.now() / 1000) + 86400,
    iat: Math.floor(Date.now() / 1000),
  }),
  'fakesignature',
].join('.')

export const authHandlers = [
  http.post('/api/auth/login', async ({ request }) => {
    const body = await request.json() as { username: string; password: string }
    if (body.password === 'wrong') {
      return HttpResponse.json({ error: 'Invalid credentials' }, { status: 401 })
    }
    return HttpResponse.json({
      token: mockToken,
      user: mockUser,
    })
  }),

  http.get('/api/auth/me', () => {
    return HttpResponse.json(mockUser)
  }),

  http.post('/api/auth/change-password', () => {
    return HttpResponse.json({ message: '비밀번호가 성공적으로 변경되었습니다' })
  }),
]

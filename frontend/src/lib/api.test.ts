import { HttpResponse, http } from 'msw'
import { setupServer } from 'msw/node'

import { ApiError, api, login, session } from './api'

let refreshCalls = 0
let validAccess = 'access-1'

const server = setupServer(
  http.post('/api/v1/auth/login', () =>
    HttpResponse.json({ access_token: 'access-1', refresh_token: 'refresh-1', expires_in: 900 })),
  http.post('/api/v1/auth/refresh', async ({ request }) => {
    refreshCalls++
    const { refresh_token } = (await request.json()) as { refresh_token: string }
    if (refresh_token !== 'refresh-1') return HttpResponse.json({ error: { code: 'unauthenticated' } }, { status: 401 })
    validAccess = 'access-2'
    return HttpResponse.json({ access_token: 'access-2', refresh_token: 'refresh-2', expires_in: 900 })
  }),
  http.get('/api/v1/candidates/me', ({ request }) => {
    if (request.headers.get('authorization') !== `Bearer ${validAccess}`) {
      return HttpResponse.json({ error: { code: 'unauthenticated', message: 'expired' } }, { status: 401 })
    }
    return HttpResponse.json({ full_name: 'Asha' })
  }),
  http.get('/api/v1/jobs/missing', () =>
    HttpResponse.json(
      { error: { code: 'not_found', message: 'Job not found', details: null, request_id: 'req-9' } },
      { status: 404 },
    )),
)

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
afterEach(() => {
  server.resetHandlers()
  session.clear()
  refreshCalls = 0
  validAccess = 'access-1'
})
afterAll(() => server.close())

it('logs in and sends the bearer token', async () => {
  await login('a@example.com', 'long-password-1')
  expect(session.isAuthenticated()).toBe(true)
  expect(await api<{ full_name: string }>('/candidates/me')).toEqual({ full_name: 'Asha' })
})

it('refreshes once on 401 and retries, even with concurrent requests', async () => {
  await login('a@example.com', 'long-password-1')
  validAccess = 'rotated-on-server' // the current access token is now rejected
  server.use(
    http.post('/api/v1/auth/refresh', () => {
      refreshCalls++
      validAccess = 'access-2'
      return HttpResponse.json({ access_token: 'access-2', refresh_token: 'refresh-2', expires_in: 900 })
    }),
  )
  const results = await Promise.all([api('/candidates/me'), api('/candidates/me'), api('/candidates/me')])
  expect(results).toHaveLength(3)
  expect(refreshCalls).toBe(1) // one shared refresh, so server-side reuse detection isn't triggered
})

it('ends the session when refresh fails and notifies listeners', async () => {
  await login('a@example.com', 'long-password-1')
  localStorage.setItem('tie.refresh', 'revoked')
  validAccess = 'nope'
  let expired = false
  const off = session.onExpired(() => { expired = true })
  await expect(api('/candidates/me')).rejects.toBeInstanceOf(ApiError)
  expect(expired).toBe(true)
  expect(session.hasRefreshToken()).toBe(false)
  off()
})

it('maps the backend error envelope onto ApiError', async () => {
  const err = await api('/jobs/missing', { auth: false }).catch((e: unknown) => e)
  expect(err).toBeInstanceOf(ApiError)
  expect(err).toMatchObject({ status: 404, code: 'not_found', message: 'Job not found', requestId: 'req-9' })
})

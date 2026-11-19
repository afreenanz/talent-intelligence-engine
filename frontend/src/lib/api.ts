/**
 * Typed client for the FastAPI backend.
 *
 * Tokens: the short-lived access token lives in memory only. The refresh token is kept in
 * localStorage so a reload keeps you signed in. Trade-off: localStorage is readable by any
 * script on the page (XSS), whereas an httpOnly cookie would not be. The backend issues refresh
 * tokens in the response body, so moving to a cookie is a backend change, noted in
 * engineering-decisions.md. Refresh tokens rotate on every use and reuse is detected server-side.
 *
 * Concurrency: when several requests hit 401 at once, they share ONE refresh call. Without this,
 * parallel refreshes would send the same refresh token twice, and the server's reuse detection
 * would (correctly) revoke the whole session.
 */

const BASE = '/api/v1'
const REFRESH_KEY = 'tie.refresh'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown
  readonly requestId: string | null

  constructor(status: number, code: string, message: string, details: unknown, requestId: string | null) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
    this.requestId = requestId
  }
}

interface TokenPair {
  access_token: string
  refresh_token: string
  expires_in: number
}

let accessToken: string | null = null
let refreshing: Promise<boolean> | null = null
const listeners = new Set<() => void>()

export const session = {
  hasRefreshToken: () => readRefresh() !== null,
  isAuthenticated: () => accessToken !== null,
  store(tokens: TokenPair) {
    accessToken = tokens.access_token
    try {
      localStorage.setItem(REFRESH_KEY, tokens.refresh_token)
    } catch {
      /* storage unavailable (private mode): session lasts until reload */
    }
  },
  clear() {
    accessToken = null
    try {
      localStorage.removeItem(REFRESH_KEY)
    } catch {
      /* ignore */
    }
  },
  /** Called when the session ends unexpectedly (refresh failed). */
  onExpired(fn: () => void) {
    listeners.add(fn)
    return () => {
      listeners.delete(fn)
    }
  },
}

function readRefresh(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY)
  } catch {
    return null
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let body: { error?: { code?: string; message?: string; details?: unknown; request_id?: string } } = {}
  try {
    body = await res.json()
  } catch {
    /* non-JSON error */
  }
  const e = body.error ?? {}
  return new ApiError(res.status, e.code ?? 'http_error', e.message ?? res.statusText, e.details ?? null,
    e.request_id ?? res.headers.get('x-request-id'))
}

/** Rotate the refresh token. Shared by all concurrent callers. Resolves false if the session is gone. */
export function refreshSession(): Promise<boolean> {
  if (refreshing) return refreshing
  const token = readRefresh()
  if (!token) return Promise.resolve(false)
  refreshing = (async () => {
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: token }),
      })
      if (!res.ok) {
        session.clear()
        return false
      }
      session.store((await res.json()) as TokenPair)
      return true
    } catch {
      return false // network error: keep the refresh token, the next call can retry
    } finally {
      refreshing = null
    }
  })()
  return refreshing
}

interface RequestOptions {
  method?: string
  body?: unknown
  form?: FormData
  auth?: boolean
  signal?: AbortSignal
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, form, auth = true, signal } = opts
  const send = () => {
    const headers: Record<string, string> = {}
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`
    return fetch(`${BASE}${path}`, {
      method,
      headers,
      body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal,
    })
  }
  if (auth && !accessToken && readRefresh()) await refreshSession()
  let res = await send()
  if (res.status === 401 && auth && readRefresh()) {
    const ok = await refreshSession()
    if (ok) res = await send()
    else listeners.forEach((fn) => fn())
  }
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

// ---------------------------------------------------------------- auth calls

export interface Account {
  id: string
  email: string
  is_active: boolean
  is_admin: boolean
  created_at: string
}

export async function login(email: string, password: string): Promise<void> {
  session.store(await api<TokenPair>('/auth/login', { method: 'POST', body: { email, password }, auth: false }))
}

export async function register(email: string, password: string, fullName?: string): Promise<void> {
  await api<Account>('/auth/register', {
    method: 'POST',
    body: { email, password, ...(fullName ? { full_name: fullName } : {}) },
    auth: false,
  })
  await login(email, password)
}

export async function logout(): Promise<void> {
  const token = readRefresh()
  session.clear()
  if (token) {
    await fetch(`${BASE}/auth/logout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: token }),
    }).catch(() => undefined)
  }
}

export interface PublicStats {
  active_jobs: number
  companies_hiring: number
  skills_tracked: number
  real_jobs: number
}

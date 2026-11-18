import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { type Account, api, login as apiLogin, logout as apiLogout, register as apiRegister, refreshSession, session } from '@/lib/api'

import { AuthContext, type AuthState, type AuthStatus as Status } from './context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>(session.hasRefreshToken() ? 'loading' : 'anonymous')
  const [account, setAccount] = useState<Account | null>(null)

  const loadAccount = useCallback(async () => {
    const me = await api<Account>('/auth/me')
    setAccount(me)
    setStatus('authenticated')
  }, [])

  useEffect(() => {
    // Restore a session after a reload: rotate the stored refresh token, then load the account.
    if (status !== 'loading') return
    refreshSession()
      .then((ok) => (ok ? loadAccount() : setStatus('anonymous')))
      .catch(() => setStatus('anonymous'))
  }, [status, loadAccount])

  useEffect(
    () => session.onExpired(() => {
      setAccount(null)
      setStatus('anonymous')
    }),
    [],
  )

  const value = useMemo<AuthState>(() => ({
    status,
    account,
    login: async (email, password) => {
      await apiLogin(email, password)
      await loadAccount()
    },
    register: async (email, password, fullName) => {
      await apiRegister(email, password, fullName)
      await loadAccount()
    },
    logout: async () => {
      await apiLogout()
      setAccount(null)
      setStatus('anonymous')
    },
  }), [status, account, loadAccount])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

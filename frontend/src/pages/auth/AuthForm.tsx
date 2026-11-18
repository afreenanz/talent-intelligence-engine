import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'

import { Mark } from '@/components/brand/Mark'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/features/auth/context'
import { ApiError } from '@/lib/api'

const MIN_PASSWORD = 10

function messageFor(err: unknown, mode: 'login' | 'register'): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return 'That email and password don’t match an account.'
    if (err.status === 409) return 'An account with this email already exists. Sign in instead.'
    if (err.status === 422) return 'Check the highlighted fields and try again.'
    if (err.status === 429) return err.message // the server says how long to wait
    if (err.status >= 500) return 'The server had a problem. Try again in a moment.'
  }
  return mode === 'login' ? 'Couldn’t sign in. Check your connection and try again.'
    : 'Couldn’t create the account. Check your connection and try again.'
}

export function AuthForm({ mode }: { mode: 'login' | 'register' }) {
  const auth = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const tooShort = mode === 'register' && password.length > 0 && password.length < MIN_PASSWORD

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (tooShort) return
    setBusy(true)
    setError(null)
    try {
      if (mode === 'login') await auth.login(email, password)
      else await auth.register(email, password, fullName || undefined)
      const next = (location.state as { from?: string } | null)?.from ?? '/app'
      navigate(next, { replace: true })
    } catch (err) {
      setError(messageFor(err, mode))
    } finally {
      setBusy(false)
    }
  }

  const title = mode === 'login' ? 'Sign in' : 'Create your profile'
  return (
    <main className="dark grid min-h-[100svh] place-items-center bg-background px-5 text-foreground">
      <div className="w-full max-w-sm">
        <Link to="/" className="mb-10 flex items-center gap-2.5 font-semibold">
          <Mark /> Talent Intelligence Engine
        </Link>
        <h1 className="text-h2 font-semibold tracking-[-0.03em]">{title}</h1>
        <p className="mt-1 text-muted-foreground">
          {mode === 'login' ? 'Welcome back.' : 'It takes a minute. You’ll add your résumé next.'}
        </p>
        <form onSubmit={onSubmit} noValidate className="mt-8 space-y-4">
          {mode === 'register' && (
            <div className="space-y-1.5">
              <Label htmlFor="fullName">Full name (optional)</Label>
              <Input id="fullName" autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" required autoComplete="email" value={email}
              onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" required minLength={mode === 'register' ? MIN_PASSWORD : 1}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password}
              aria-invalid={tooShort || undefined} aria-describedby={mode === 'register' ? 'password-hint' : undefined}
              onChange={(e) => setPassword(e.target.value)} />
            {mode === 'register' && (
              <p id="password-hint" className={tooShort ? 'text-small text-rose' : 'text-small text-muted-foreground'}>
                At least {MIN_PASSWORD} characters.
              </p>
            )}
          </div>
          {error && <p role="alert" className="rounded-md border border-rose/30 bg-rose/10 px-3 py-2 text-small text-rose">{error}</p>}
          <Button type="submit" className="w-full" disabled={busy || !email || !password || tooShort}>
            {busy ? (mode === 'login' ? 'Signing in…' : 'Creating profile…') : title}
          </Button>
        </form>
        <p className="mt-6 text-small text-muted-foreground">
          {mode === 'login' ? <>New here? <Link className="text-foreground underline underline-offset-4" to="/register">Create your profile</Link></>
            : <>Already have an account? <Link className="text-foreground underline underline-offset-4" to="/login">Sign in</Link></>}
        </p>
      </div>
    </main>
  )
}

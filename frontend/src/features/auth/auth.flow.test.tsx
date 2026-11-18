import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { setupServer } from 'msw/node'

import { renderApp } from '@/test/renderApp'

const account = { id: '1', email: 'asha@example.com', is_active: true, is_admin: false, created_at: '2026-11-18T00:00:00Z' }
const server = setupServer(
  http.post('/api/v1/auth/login', async ({ request }) => {
    const body = (await request.json()) as { password: string }
    return body.password === 'correct-horse-1'
      ? HttpResponse.json({ access_token: 'a', refresh_token: 'r', expires_in: 900 })
      : HttpResponse.json({ error: { code: 'unauthenticated', message: 'Invalid email or password' } }, { status: 401 })
  }),
  http.post('/api/v1/auth/register', () =>
    HttpResponse.json({ error: { code: 'conflict', message: 'exists' } }, { status: 409 })),
  http.get('/api/v1/auth/me', () => HttpResponse.json(account)),
  http.get('/api/v1/candidates/me', () =>
    HttpResponse.json({ full_name: 'Asha Verma', skills: [], experience_years: null, location: null })),
)
beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

it('redirects an anonymous visitor from the app to sign-in', async () => {
  const router = renderApp('/app/saved')
  await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
  expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
})

it('signs in and lands on the page they asked for', async () => {
  const router = renderApp('/app')
  await screen.findByRole('heading', { name: 'Sign in' })
  await userEvent.type(screen.getByLabelText('Email'), 'asha@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'correct-horse-1')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByRole('heading', { name: 'Hello, Asha.' })).toBeInTheDocument()
  expect(router.state.location.pathname).toBe('/app')
  expect(screen.getByText(/Still missing: skills, experience, location/)).toBeInTheDocument()
})

it('shows a plain error for wrong credentials', async () => {
  renderApp('/login')
  await userEvent.type(screen.getByLabelText('Email'), 'asha@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'wrong')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('That email and password don’t match an account.')
})

it('blocks short passwords on sign-up and explains a duplicate email', async () => {
  renderApp('/register')
  await userEvent.type(screen.getByLabelText('Email'), 'asha@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'short')
  expect(screen.getByRole('button', { name: 'Create your profile' })).toBeDisabled()
  expect(screen.getByLabelText('Password')).toHaveAttribute('aria-invalid', 'true')
  await userEvent.type(screen.getByLabelText('Password'), '-but-longer')
  await userEvent.click(screen.getByRole('button', { name: 'Create your profile' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('already exists')
})

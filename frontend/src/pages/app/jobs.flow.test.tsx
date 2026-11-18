import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { setupServer } from 'msw/node'

import { renderApp } from '@/test/renderApp'

const job = (id: string, title: string) => ({
  id, title, company: 'Acme', location: null, city: 'Pune', location_type: 'hybrid', employment_type: 'full_time',
  salary_min: 1_200_000, salary_max: 1_800_000, salary_currency: 'INR', experience_min: 2, experience_max: 5,
  status: 'active', listed_at: '2026-11-10T00:00:00Z', expires_at: null,
})
const hit = (id: string, title: string, score: number) => ({
  job_id: id, title, company: 'Acme', score, explanation: ['Matches 2 of 3 required skills (Python, SQL)', 'Missing: Go'],
  contributions: { required_skill_coverage: 0.2, location_fit: 0.05 }, missing_features: [], exploration: false, job: job(id, title),
})
const searchBodies: unknown[] = []
const feedback: { interaction_type: string; position: number }[] = []

const server = setupServer(
  http.post('/api/v1/auth/refresh', () => HttpResponse.json({ access_token: 'a', refresh_token: 'r2', expires_in: 900 })),
  http.get('/api/v1/auth/me', () => HttpResponse.json({ id: '1', email: 'a@example.com', is_active: true, is_admin: false, created_at: '' })),
  http.get('/api/v1/candidates/me/searches', () => HttpResponse.json([])),
  http.get('/api/v1/saved-jobs', () => HttpResponse.json({ items: [], next_cursor: null })),
  http.post('/api/v1/jobs/search', async ({ request }) => {
    searchBodies.push(await request.json())
    return HttpResponse.json({ results: [hit('j1', 'Backend Engineer', 0.81), hit('j2', 'Data Engineer', 0.64)], mode: 'hybrid',
      ranking: 'features', search_log_id: 'log-1', used_profile: false, timings_ms: {} })
  }),
  http.get('/api/v1/recommendations', () =>
    HttpResponse.json({ results: [hit('j1', 'Backend Engineer', 0.81), hit('j2', 'Data Engineer', 0.64)], mode: 'hybrid',
      ranking: 'features', search_log_id: 'log-2', used_profile: true, timings_ms: {} })),
  http.post('/api/v1/recommendations/feedback', async ({ request }) => {
    feedback.push((await request.json()) as never)
    return HttpResponse.json({ status: 'recorded' }, { status: 201 })
  }),
  http.get('/api/v1/applications', () =>
    HttpResponse.json([{ id: 'a1', application_status: 'applied', notes: null, created_at: '2026-11-17T00:00:00Z', updated_at: '2026-11-17T00:00:00Z', job: job('j1', 'Backend Engineer') }])),
)
beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
beforeEach(() => { localStorage.setItem('tie.refresh', 'r1'); searchBodies.length = 0; feedback.length = 0 })
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

it('runs the search described by the URL and shows ranked, explained results', async () => {
  renderApp('/app/search?q=backend&city=Pune&min_lpa=12')
  await screen.findByRole('link', { name: 'Backend Engineer' })
  expect(screen.getByText(/best matches for “backend”/)).toHaveTextContent('2 best matches for “backend”')
  expect(searchBodies[0]).toMatchObject({ query: 'backend', filters: { city: 'Pune', min_salary: 1_200_000 }, use_profile: false })
  const first = screen.getAllByRole('listitem')[0]
  expect(within(first).getByRole('link', { name: 'Backend Engineer' })).toBeInTheDocument()
  expect(within(first).getByText('81')).toBeInTheDocument()
  expect(within(first).getByText('12–18 LPA')).toBeInTheDocument()
  expect(within(first).getByText('Missing: Go')).toBeInTheDocument()
})

it('features the top match and records "not interested" with its position', async () => {
  renderApp('/app/recommendations')
  expect(await screen.findByText('Best match right now')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Not interested in Data Engineer' }))
  await waitFor(() => expect(feedback).toEqual([expect.objectContaining({ interaction_type: 'dismiss', position: 2, search_log_id: 'log-2' })]))
  expect(screen.queryByText('Data Engineer')).not.toBeInTheDocument()
})

it('explains an empty profile instead of showing an error', async () => {
  server.use(http.get('/api/v1/recommendations', () =>
    HttpResponse.json({ error: { code: 'empty_search', message: 'Your profile is empty' } }, { status: 400 })))
  renderApp('/app/recommendations')
  expect(await screen.findByText('Add your skills to get matches')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Upload your résumé' })).toHaveAttribute('href', '/app/resume')
})

it('shows the application pipeline and only offers allowed status moves', async () => {
  renderApp('/app/applications')
  await screen.findByRole('link', { name: 'Backend Engineer' })
  const pipeline = screen.getByRole('region', { name: 'Pipeline' })
  expect(within(pipeline).getByText('Applied').previousSibling).toHaveTextContent('1')
  await userEvent.click(screen.getByRole('combobox', { name: 'Status for Backend Engineer' }))
  const options = screen.getAllByRole('option').map((o) => o.textContent)
  expect(options).toEqual(['Applied', 'Move to screening', 'Move to rejected', 'Move to withdrawn'])
})

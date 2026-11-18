import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { setupServer } from 'msw/node'

import { renderApp } from '@/test/renderApp'

const parsed = {
  id: 'r1', original_filename: 'riya.pdf', size_bytes: 2000, page_count: 1, parsing_status: 'parsed', parsing_error: null,
  llm_model: 'gemini', created_at: '2026-11-18T10:00:00Z', reviewed_at: null,
  parsed_data: {
    full_name: 'Riya Kapoor', location: '', summary: 'Backend engineer.', experience_years: 5.4,
    experience_years_method: 'sum of 1 merged date range(s) = 65 months', warnings: [], text_truncated: false,
    skills: [
      { name: 'Python', skill_id: 1, provenance: 'both', suggested: false },
      { name: 'ETL', skill_id: 2, provenance: 'dictionary', suggested: true },
    ],
    work_experience: [], education: [{ institution: 'PIT', degree: 'B.Tech' }], projects: [], preferred_roles: [],
  },
}
let applied: Record<string, unknown> | null = null
const server = setupServer(
  http.post('/api/v1/auth/refresh', () => HttpResponse.json({ access_token: 'a', refresh_token: 'r2', expires_in: 900 })),
  http.get('/api/v1/auth/me', () => HttpResponse.json({ id: '1', email: 'a@example.com', is_active: true, is_admin: false, created_at: '' })),
  http.get('/api/v1/candidates/resumes', () => HttpResponse.json([applied ? { ...parsed, parsing_status: 'reviewed', reviewed_at: '2026-11-18T10:01:00Z' } : parsed])),
  http.post('/api/v1/candidates/resumes/r1/apply', async ({ request }) => {
    applied = (await request.json()) as Record<string, unknown>
    return HttpResponse.json({ id: 'p1', full_name: 'Riya Kapoor', skills: [], experience_years: 5.4, location: null, salary_currency: 'INR' })
  }),
)
beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
beforeEach(() => { localStorage.setItem('tie.refresh', 'r1'); applied = null })
afterAll(() => server.close())

it('applies only reviewed fields: keyword-only skills unticked, empty fields left out, fractional years accepted', async () => {
  renderApp('/app/resume')
  await screen.findByText('Check what we found')
  expect(screen.getByLabelText('Years of experience')).toBeValid() // 5.4 years must not block the form
  expect(screen.getByRole('checkbox', { name: 'ETL' })).not.toBeChecked()
  await userEvent.click(screen.getByRole('button', { name: 'Add to my profile' }))
  await waitFor(() => expect(applied).not.toBeNull())
  expect(applied).toEqual({
    full_name: 'Riya Kapoor', experience_years: 5.4, profile_summary: 'Backend engineer.',
    skills: [{ name: 'Python' }], education: [{ institution: 'PIT', degree: 'B.Tech' }], projects: null,
  })
  expect(await screen.findByText('Your résumé is on your profile')).toBeInTheDocument()
})

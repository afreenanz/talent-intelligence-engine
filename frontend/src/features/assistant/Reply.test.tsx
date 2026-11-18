import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

import { Reply } from './Reply'

const id = '03c45e50-603f-4361-aeb8-962d6a634e02'

it('renders lists, bold text and job references as links', () => {
  render(<MemoryRouter><Reply text={`Here are two jobs:\n\n1. **Backend Engineer** at Acme [job_id: ${id}]\n2. **Data Engineer** at Beta\n\nSaved the first.`} /></MemoryRouter>)
  expect(screen.getByRole('list').tagName).toBe('OL')
  expect(screen.getAllByRole('listitem')).toHaveLength(2)
  expect(screen.getByText('Backend Engineer').tagName).toBe('STRONG')
  expect(screen.getByRole('link', { name: 'View job' })).toHaveAttribute('href', `/app/jobs/${id}`)
  expect(screen.getByText('Saved the first.')).toBeInTheDocument()
})

it('never turns model output into HTML', () => {
  const { container } = render(<MemoryRouter><Reply text={'<img src=x onerror="alert(1)"> **<b>hi</b>**'} /></MemoryRouter>)
  expect(container.querySelector('img')).toBeNull()
  expect(container.querySelector('b')).toBeNull()
  expect(container.textContent).toContain('<img src=x onerror="alert(1)">')
})

it('replaces a bare job id with the job title', async () => {
  const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query')
  const qc = new QueryClient()
  qc.setQueryData(['job', id], { id, title: 'Backend Engineer', company: 'Acme' })
  render(<QueryClientProvider client={qc}><MemoryRouter><Reply text={`Please confirm: Save job ${id} to your saved jobs.`} /></MemoryRouter></QueryClientProvider>)
  expect(screen.getByRole('link', { name: 'Backend Engineer at Acme' })).toHaveAttribute('href', `/app/jobs/${id}`)
  expect(screen.queryByText(id, { exact: false })).toBeNull()
})

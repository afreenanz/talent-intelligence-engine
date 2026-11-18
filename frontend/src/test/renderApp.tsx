import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { RouterProvider, createMemoryRouter } from 'react-router'

import { routes } from '@/app/router'
import { AuthProvider } from '@/features/auth/AuthProvider'

/** Render the real route tree at a URL, with fresh query cache and auth state. */
export function renderApp(url: string) {
  const router = createMemoryRouter(routes, { initialEntries: [url] })
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return router
}

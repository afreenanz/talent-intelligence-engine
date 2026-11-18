import type { ComponentType } from 'react'
import { Navigate, createBrowserRouter } from 'react-router'

import { AppShell } from '@/app/AppShell'
import { GuestOnly, RequireAuth } from '@/features/auth/guards'
import Landing from '@/pages/Landing'
import NotBuiltYet from '@/pages/app/NotBuiltYet'
import { AuthForm } from '@/pages/auth/AuthForm'

/** App pages load on demand, so the landing page doesn't download the whole app. */
const page = (load: () => Promise<{ default: ComponentType }>) => ({
  lazy: async () => ({ Component: (await load()).default }),
  // Shown only while the page's code downloads on a first visit straight to its URL.
  hydrateFallbackElement: <p className="text-muted-foreground">Loading…</p>,
})

const planned = (title: string, milestone: string, about: string) => <NotBuiltYet title={title} milestone={milestone} about={about} />

export const routes = [
  { path: '/', element: <Landing /> },
  { path: '/login', element: <GuestOnly><AuthForm mode="login" /></GuestOnly> },
  { path: '/register', element: <GuestOnly><AuthForm mode="register" /></GuestOnly> },
  {
    path: '/app',
    element: <RequireAuth><AppShell /></RequireAuth>,
    children: [
      { index: true, ...page(() => import('@/pages/app/Overview')) },
      { path: 'search', ...page(() => import('@/pages/app/Search')) },
      { path: 'recommendations', ...page(() => import('@/pages/app/ForYou')) },
      { path: 'assistant', element: planned('Assistant', 'Milestone 8C', 'Ask in plain language. The assistant searches, explains and saves jobs, and asks before it changes anything.') },
      { path: 'jobs/:id', ...page(() => import('@/pages/app/JobDetail')) },
      { path: 'saved', ...page(() => import('@/pages/app/Saved')) },
      { path: 'applications', ...page(() => import('@/pages/app/Applications')) },
      { path: 'resume', element: planned('Résumé', 'Milestone 8C', 'Upload a PDF, review what we extracted, then add it to your profile.') },
      { path: 'preferences', ...page(() => import('@/pages/app/Preferences')) },
      { path: 'evaluation', element: planned('Evaluation', 'Milestone 8C', 'Benchmark results for retrieval, ranking, the assistant and résumé extraction (admins only).') },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]

export const router = createBrowserRouter(routes)

import type { ComponentType } from 'react'
import { Navigate, createBrowserRouter } from 'react-router'

import { AppShell } from '@/app/AppShell'
import { GuestOnly, RequireAuth } from '@/features/auth/guards'
import Landing from '@/pages/Landing'
import { AuthForm } from '@/pages/auth/AuthForm'

/** App pages load on demand, so the landing page doesn't download the whole app. */
const page = (load: () => Promise<{ default: ComponentType }>) => ({
  lazy: async () => ({ Component: (await load()).default }),
  // Shown only while the page's code downloads on a first visit straight to its URL.
  hydrateFallbackElement: <p className="text-muted-foreground">Loading…</p>,
})


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
      { path: 'assistant', ...page(() => import('@/pages/app/Assistant')) },
      { path: 'jobs/:id', ...page(() => import('@/pages/app/JobDetail')) },
      { path: 'saved', ...page(() => import('@/pages/app/Saved')) },
      { path: 'applications', ...page(() => import('@/pages/app/Applications')) },
      { path: 'resume', ...page(() => import('@/pages/app/Resume')) },
      { path: 'preferences', ...page(() => import('@/pages/app/Preferences')) },
      { path: 'evaluation', ...page(() => import('@/pages/app/Evaluation')) },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]

export const router = createBrowserRouter(routes)

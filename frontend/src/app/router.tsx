import { Navigate, createBrowserRouter } from 'react-router'

import { AppShell } from '@/app/AppShell'
import { GuestOnly, RequireAuth } from '@/features/auth/guards'
import Landing from '@/pages/Landing'
import NotBuiltYet from '@/pages/app/NotBuiltYet'
import Overview from '@/pages/app/Overview'
import { AuthForm } from '@/pages/auth/AuthForm'

const planned = (title: string, milestone: string, about: string) => <NotBuiltYet title={title} milestone={milestone} about={about} />

export const routes = [
  { path: '/', element: <Landing /> },
  { path: '/login', element: <GuestOnly><AuthForm mode="login" /></GuestOnly> },
  { path: '/register', element: <GuestOnly><AuthForm mode="register" /></GuestOnly> },
  {
    path: '/app',
    element: <RequireAuth><AppShell /></RequireAuth>,
    children: [
      { index: true, element: <Overview /> },
      { path: 'search', element: planned('Search', 'Milestone 8B', 'Search every open role by keywords or meaning, filter by city, salary and work mode, and see why each result ranks where it does.') },
      { path: 'recommendations', element: planned('For you', 'Milestone 8B', 'Roles ranked for your profile and preferences, with the reasons for each match.') },
      { path: 'assistant', element: planned('Assistant', 'Milestone 8C', 'Ask in plain language. The assistant searches, explains and saves jobs, and asks before it changes anything.') },
      { path: 'saved', element: planned('Saved', 'Milestone 8B', 'Jobs you saved, newest first.') },
      { path: 'applications', element: planned('Applications', 'Milestone 8B', 'Track every application from applied to offer.') },
      { path: 'resume', element: planned('Résumé', 'Milestone 8C', 'Upload a PDF, review what we extracted, then add it to your profile.') },
      { path: 'preferences', element: planned('Preferences', 'Milestone 8B', 'Everything stored about your preferences: what you stated and what was learned from your activity. You can edit or remove any of it.') },
      { path: 'evaluation', element: planned('Evaluation', 'Milestone 8C', 'Benchmark results for retrieval, ranking, the assistant and résumé extraction (admins only).') },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]

export const router = createBrowserRouter(routes)

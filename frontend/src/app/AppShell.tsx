import {
  Bookmark, Bot, BriefcaseBusiness, FileText, FlaskConical, LayoutDashboard, LogOut, Moon, Search,
  SlidersHorizontal, Sparkles, Sun,
} from 'lucide-react'
import { NavLink, Outlet } from 'react-router'

import { Mark } from '@/components/brand/Mark'
import { useAuth } from '@/features/auth/context'
import { useTheme } from '@/lib/theme'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/app', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/app/search', label: 'Search', icon: Search },
  { to: '/app/recommendations', label: 'For you', icon: Sparkles },
  { to: '/app/assistant', label: 'Assistant', icon: Bot },
  { to: '/app/saved', label: 'Saved', icon: Bookmark },
  { to: '/app/applications', label: 'Applications', icon: BriefcaseBusiness },
  { to: '/app/resume', label: 'Résumé', icon: FileText },
  { to: '/app/preferences', label: 'Preferences', icon: SlidersHorizontal },
]

export function AppShell() {
  const { account, logout } = useAuth()
  const { theme, setTheme } = useTheme()
  const items = account?.is_admin ? [...NAV, { to: '/app/evaluation', label: 'Evaluation', icon: FlaskConical }] : NAV

  return (
    <div className="grid min-h-[100svh] grid-cols-1 md:grid-cols-[15rem_1fr]">
      <aside className="flex flex-col border-b border-sidebar-border bg-sidebar md:sticky md:top-0 md:h-[100svh] md:border-b-0 md:border-r">
        <div className="flex items-center gap-2.5 px-5 py-5 font-semibold tracking-tight">
          <Mark /> <span className="truncate">Talent Engine</span>
          {/* Phones: the account controls live in the top bar (the sidebar footer is hidden). */}
          <div className="ml-auto flex gap-1 md:hidden">
            <button type="button" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className="rounded-md p-2 text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
              {theme === 'dark' ? <Sun className="size-4" aria-hidden="true" /> : <Moon className="size-4" aria-hidden="true" />}
            </button>
            <button type="button" onClick={() => void logout()} aria-label="Sign out"
              className="rounded-md p-2 text-muted-foreground hover:bg-sidebar-accent hover:text-foreground">
              <LogOut className="size-4" aria-hidden="true" />
            </button>
          </div>
        </div>
        <nav aria-label="App" className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:overflow-visible">
          {items.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) => cn(
                'flex shrink-0 items-center gap-3 rounded-md px-3 py-2 text-small text-muted-foreground hover:bg-sidebar-accent hover:text-foreground',
                isActive && 'bg-sidebar-accent text-foreground',
              )}>
              {({ isActive }) => (
                <>
                  <Icon aria-hidden="true" className={cn('size-4', isActive && 'text-signal')} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto hidden border-t border-sidebar-border p-3 md:block">
          <p className="truncate px-2 pb-2 text-small text-muted-foreground" title={account?.email}>{account?.email}</p>
          <div className="flex gap-1">
            <button type="button" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className="flex flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-small text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
              {theme === 'dark' ? <Sun className="size-4" aria-hidden="true" /> : <Moon className="size-4" aria-hidden="true" />}
              {theme === 'dark' ? 'Light theme' : 'Dark theme'}
            </button>
            <button type="button" onClick={() => void logout()}
              className="flex items-center gap-2 rounded-md px-2 py-1.5 text-small text-muted-foreground hover:bg-sidebar-accent hover:text-foreground">
              <LogOut className="size-4" aria-hidden="true" /> Sign out
            </button>
          </div>
        </div>
      </aside>
      <main id="main" className="min-w-0 px-5 py-8 sm:px-8 lg:px-12">
        <Outlet />
      </main>
    </div>
  )
}

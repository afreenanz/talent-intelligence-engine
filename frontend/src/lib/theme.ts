import { useSyncExternalStore } from 'react'

/**
 * Theme: dark by default, light on request, remembered per browser.
 * index.html applies the stored choice before first paint (no flash); this module keeps it in sync
 * afterwards. Replaces next-themes, whose inline <script> is meant for server rendering and only
 * produces a warning in a client-only React 19 app.
 */
export type Theme = 'dark' | 'light'
const KEY = 'tie.theme'
const listeners = new Set<() => void>()

function current(): Theme {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

export function setTheme(theme: Theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark')
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#07080c' : '#eef0f3')
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    /* storage unavailable: the choice lasts until reload */
  }
  listeners.forEach((fn) => fn())
}

export function useTheme(): { theme: Theme; setTheme: (t: Theme) => void } {
  const theme = useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => {
        listeners.delete(fn)
      }
    },
    current,
    () => 'dark' as const,
  )
  return { theme, setTheme }
}

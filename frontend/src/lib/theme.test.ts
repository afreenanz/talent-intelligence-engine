import { act, renderHook } from '@testing-library/react'

import { setTheme, useTheme } from './theme'

afterEach(() => document.documentElement.classList.add('dark'))

it('toggles the html class, remembers the choice and re-renders subscribers', () => {
  document.documentElement.classList.add('dark')
  const { result } = renderHook(() => useTheme())
  expect(result.current.theme).toBe('dark')
  act(() => setTheme('light'))
  expect(result.current.theme).toBe('light')
  expect(document.documentElement.classList.contains('dark')).toBe(false)
  expect(localStorage.getItem('tie.theme')).toBe('light')
})

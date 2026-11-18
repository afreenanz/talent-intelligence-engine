import { ago, experience, fit, place, salary } from './format'

it('formats INR salaries as lakhs per annum', () => {
  expect(salary({ salary_min: 1_200_000, salary_max: 1_850_000, salary_currency: 'INR' })).toBe('12–18.5 LPA')
  expect(salary({ salary_min: 800_000, salary_max: null, salary_currency: 'INR' })).toBe('From 8 LPA')
  expect(salary({ salary_min: null, salary_max: null, salary_currency: 'INR' })).toBeNull()
  expect(salary({ salary_min: 90_000, salary_max: 120_000, salary_currency: 'USD' })).toBe('90k–120k USD')
})

it('formats experience ranges, places and fit', () => {
  expect(experience({ experience_min: 2, experience_max: 5 })).toBe('2–5 yrs')
  expect(experience({ experience_min: 3, experience_max: null })).toBe('3+ yrs')
  expect(place({ city: 'Pune', location: null, location_type: 'remote' })).toBe('Remote, Pune')
  expect(place({ city: 'Pune', location: null, location_type: 'hybrid' })).toBe('Pune')
  expect(fit(0.7288)).toBe(73)
  expect(fit(null)).toBeNull()
})

it('describes dates relative to now', () => {
  const now = new Date('2026-11-18T12:00:00Z').getTime()
  expect(ago('2026-11-18T08:00:00Z', now)).toBe('today')
  expect(ago('2026-11-15T12:00:00Z', now)).toBe('3 days ago')
  expect(ago('2026-08-18T12:00:00Z', now)).toBe('3 months ago')
})

it('only offers application moves the backend allows', async () => {
  const { NEXT_STATUS } = await import('./format')
  expect(NEXT_STATUS.applied).toEqual(['screening', 'rejected', 'withdrawn'])
  expect(NEXT_STATUS.applied).not.toContain('interviewing') // the 409 seen in the browser check
  expect(NEXT_STATUS.rejected).toEqual([])
})

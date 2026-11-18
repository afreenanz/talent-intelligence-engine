import { JOB_TYPE, WORK_MODE } from './format'
import type { PreferenceKey } from './types'

export const ROLES: Record<string, string> = {
  backend: 'Backend', frontend: 'Frontend', fullstack: 'Full-stack', data: 'Data', ml: 'Machine learning',
  devops: 'DevOps', mobile: 'Mobile', qa: 'QA and testing', security: 'Security', design: 'Design', product: 'Product',
}

export const PREFERENCE_LABEL: Record<PreferenceKey, string> = {
  role_categories: 'kinds of roles', locations: 'cities', location_type: 'work mode', min_salary: 'minimum salary',
  employment_type: 'job type', company_avoid: 'companies to avoid', skills_to_use: 'skills you want to use',
}

type Value = Record<string, unknown>
export const list = (v: unknown) => (Array.isArray(v) ? (v as string[]) : [])

/** How a stored preference value reads in plain words. */
export function describePreference(key: PreferenceKey, v: Value): string {
  switch (key) {
    case 'role_categories': {
      const p = list(v.prefer).map((r) => ROLES[r] ?? r)
      const a = list(v.avoid).map((r) => ROLES[r] ?? r)
      return [p.length && `Prefer ${p.join(', ')}`, a.length && `avoid ${a.join(', ')}`].filter(Boolean).join('; ')
    }
    case 'locations': return list(v.cities).join(', ')
    case 'location_type': return WORK_MODE[v.value as keyof typeof WORK_MODE] ?? String(v.value)
    case 'employment_type': return JOB_TYPE[v.value as keyof typeof JOB_TYPE] ?? String(v.value)
    case 'min_salary': return v.currency === 'INR' || !v.currency ? `${Number(v.amount) / 100_000} LPA` : `${v.amount} ${v.currency}`
    case 'company_avoid': return list(v.companies).join(', ')
    case 'skills_to_use': return list(v.skills).join(', ')
  }
}

import type { ApplicationStatus, EmploymentType, JobSummary, LocationType } from './types'

export const WORK_MODE: Record<LocationType, string> = { onsite: 'On-site', remote: 'Remote', hybrid: 'Hybrid' }
export const JOB_TYPE: Record<EmploymentType, string> = {
  full_time: 'Full-time', part_time: 'Part-time', contract: 'Contract', internship: 'Internship', temporary: 'Temporary',
}
export const APP_STATUS: Record<ApplicationStatus, string> = {
  applied: 'Applied', screening: 'Screening', interviewing: 'Interviewing', offer: 'Offer', rejected: 'Rejected', withdrawn: 'Withdrawn',
}

/** Mirrors ALLOWED_TRANSITIONS in the backend, so the menu only offers moves the server accepts. */
export const NEXT_STATUS: Record<ApplicationStatus, ApplicationStatus[]> = {
  applied: ['screening', 'rejected', 'withdrawn'],
  screening: ['interviewing', 'rejected', 'withdrawn'],
  interviewing: ['offer', 'rejected', 'withdrawn'],
  offer: ['withdrawn'],
  rejected: [],
  withdrawn: [],
}

/** What each ranking feature means to a candidate (keys come from the ranker). */
export const FEATURE_LABEL: Record<string, string> = {
  required_skill_coverage: 'Required skills',
  preferred_skill_coverage: 'Nice-to-have skills',
  skill_jaccard: 'Overall skill overlap',
  semantic_similarity: 'Profile similarity',
  retrieval_score: 'Search relevance',
  experience_fit: 'Experience',
  salary_fit: 'Salary',
  location_fit: 'Location',
  employment_type_match: 'Job type',
  recency: 'How recent',
}

/** INR as lakhs per annum (the way Indian job ads state pay); other currencies in thousands. */
export function salary(job: Pick<JobSummary, 'salary_min' | 'salary_max' | 'salary_currency'>): string | null {
  const { salary_min: lo, salary_max: hi } = job
  const cur = job.salary_currency ?? 'INR'
  if (lo == null && hi == null) return null
  const f = cur === 'INR'
    ? (n: number) => `${trim(n / 100_000)}`
    : (n: number) => `${trim(n / 1000)}k`
  const unit = cur === 'INR' ? ' LPA' : ` ${cur}`
  if (lo != null && hi != null) return lo === hi ? `${f(lo)}${unit}` : `${f(lo)}–${f(hi)}${unit}`
  return lo != null ? `From ${f(lo)}${unit}` : `Up to ${f(hi!)}${unit}`
}

function trim(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, '')
}

export function experience(job: Pick<JobSummary, 'experience_min' | 'experience_max'>): string | null {
  const { experience_min: lo, experience_max: hi } = job
  if (lo == null && hi == null) return null
  if (lo != null && hi != null) return lo === hi ? `${lo} yrs` : `${lo}–${hi} yrs`
  return lo != null ? `${lo}+ yrs` : `Up to ${hi} yrs`
}

const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
export function ago(iso: string, now = Date.now()): string {
  const days = Math.round((new Date(iso).getTime() - now) / 86_400_000)
  if (Math.abs(days) < 1) return 'today'
  if (Math.abs(days) < 30) return rtf.format(days, 'day')
  if (Math.abs(days) < 365) return rtf.format(Math.round(days / 30), 'month')
  return rtf.format(Math.round(days / 365), 'year')
}

export function place(job: Pick<JobSummary, 'city' | 'location' | 'location_type'>): string | null {
  if (job.location_type === 'remote') return job.city ? `Remote, ${job.city}` : 'Remote'
  return job.city ?? job.location
}

/** Ranking score (0–1 weighted sum) as a 0–100 fit score. It orders jobs; it is not a probability. */
export const fit = (score: number | null | undefined) => (score == null ? null : Math.round(score * 100))

/** API shapes, mirrored from the FastAPI OpenAPI schema (docs/api-documentation.md). */

export type LocationType = 'onsite' | 'remote' | 'hybrid'
export type EmploymentType = 'full_time' | 'part_time' | 'contract' | 'internship' | 'temporary'
export type ApplicationStatus = 'applied' | 'screening' | 'interviewing' | 'offer' | 'rejected' | 'withdrawn'
export type SkillImportance = 'required' | 'preferred' | 'mentioned'

export interface JobSummary {
  id: string
  title: string
  company: string
  location: string | null
  city: string | null
  location_type: LocationType | null
  employment_type: EmploymentType | null
  salary_min: number | null
  salary_max: number | null
  salary_currency: string | null
  experience_min: number | null
  experience_max: number | null
  status: 'active' | 'expired' | 'duplicate' | 'removed'
  listed_at: string
  expires_at: string | null
}

export interface JobDetail extends JobSummary {
  description: string
  source: string
  posted_at: string | null
  skills: { skill_id: number; name: string; importance: SkillImportance }[]
}

export interface SearchHit {
  job_id: string
  title: string
  company: string
  score?: number | null
  cross_encoder_score?: number | null
  explanation?: string[] | null
  personalization?: number | null
  role_categories?: string[] | null
  exploration?: boolean | null
  features?: Record<string, number> | null
  contributions?: Record<string, number> | null
  missing_features?: string[] | null
  job?: JobSummary | null
}

export interface SearchResponse {
  results: SearchHit[]
  mode: 'lexical' | 'dense' | 'hybrid'
  ranking: string
  search_log_id: string | null
  used_profile: boolean
  timings_ms: Record<string, number>
}

export interface JobFilters {
  city?: string
  location_type?: LocationType
  employment_type?: EmploymentType
  min_salary?: number
}

export interface Page<T> {
  items: T[]
  next_cursor: string | null
}

export interface SavedJob {
  saved_at: string
  job: JobSummary
}

export interface Application {
  id: string
  application_status: ApplicationStatus
  notes: string | null
  created_at: string
  updated_at: string
  job: JobSummary
}

export interface Profile {
  id: string
  full_name: string | null
  experience_years: number | null
  location: string | null
  preferred_salary_min: number | null
  salary_currency: string
  skills: { skill_id: number; name: string; normalized_name: string }[]
}

export type PreferenceKey =
  | 'role_categories' | 'locations' | 'location_type' | 'min_salary' | 'employment_type' | 'company_avoid' | 'skills_to_use'

export interface Preference {
  key: PreferenceKey
  value: Record<string, unknown>
  memory_type: 'explicit_preference' | 'derived_preference'
  source: 'settings' | 'agent' | 'derived'
  confidence: number
  updated_at: string | null
}

export interface RecentSearch {
  id: string
  query: string | null
  filters: JobFilters
  result_count: number
  created_at: string
}

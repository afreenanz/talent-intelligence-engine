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
  /** "synthetic_v1" for demo data, "adzuna_in" etc. for real feed listings. */
  source: string
  apply_url: string | null
}

export interface JobDetail extends JobSummary {
  description: string
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
  sources?: string[]
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

// ------------------------------------------------------------------ assistant
export interface PendingAction {
  tool: string
  arguments: Record<string, unknown>
  summary: string
}
export interface ToolCallTrace {
  tool: string
  arguments: Record<string, unknown>
  ok: boolean
  error_code?: string | null
  confirmed?: boolean | null
}
export interface ChatResponse {
  conversation_id: string
  status: 'completed' | 'awaiting_confirmation'
  reply: string
  pending_actions?: PendingAction[]
  tool_calls?: ToolCallTrace[]
  grounded?: boolean | null
  grounding_issues?: string[]
}
export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}
export interface Message {
  id: string
  role: 'user' | 'assistant' | string
  content: string
  tool_metadata: { tool_calls?: ToolCallTrace[]; pending_actions?: PendingAction[]; grounded?: boolean } | null
  created_at: string
}
export interface ConversationDetail extends Conversation {
  messages: Message[]
  awaiting_confirmation: boolean
}

// --------------------------------------------------------------------- résumé
export type ResumeStatus = 'pending' | 'processing' | 'parsed' | 'failed' | 'reviewed'
export interface ParsedResume {
  full_name: string | null
  location: string | null
  summary: string | null
  skills: { name: string; skill_id: number | null; provenance: 'llm' | 'dictionary' | 'both'; suggested?: boolean }[]
  work_experience: { company: string | null; title: string | null; start_date: string | null; end_date: string | null; is_current: boolean; grounded: boolean }[]
  education: { institution: string; degree?: string | null; field_of_study?: string | null; start_year?: number | null; end_year?: number | null }[]
  projects: { name: string; description?: string | null; technologies?: string[]; url?: string | null }[]
  preferred_roles: string[]
  experience_years: number | null
  experience_years_method: string
  warnings: string[]
  text_truncated: boolean
}
export interface Resume {
  id: string
  original_filename: string
  size_bytes: number
  page_count: number | null
  parsing_status: ResumeStatus
  parsing_error: string | null
  parsed_data: ParsedResume | null
  llm_model: string | null
  created_at: string
  reviewed_at: string | null
}

// ----------------------------------------------------------------- evaluation
export interface EvaluationRun {
  id: string
  experiment_name: string
  dataset_version: string
  split: string
  configuration: Record<string, unknown>
  metrics: Record<string, unknown>
  git_commit: string | null
  created_at: string
}

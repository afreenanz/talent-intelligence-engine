import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type {
  Application, ApplicationStatus, JobDetail, JobFilters, Page, Preference, PreferenceKey, Profile, RecentSearch,
  SavedJob, SearchHit, SearchResponse,
} from '@/lib/types'

export const keys = {
  search: (q: string, f: JobFilters, useProfile: boolean) => ['search', q, f, useProfile] as const,
  recs: ['recommendations'] as const,
  job: (id: string) => ['job', id] as const,
  hit: (id: string) => ['hit', id] as const,
  saved: ['saved'] as const,
  savedIds: ['saved', 'ids'] as const,
  applications: ['applications'] as const,
  preferences: ['preferences'] as const,
  profile: ['profile'] as const,
  recent: ['recent-searches'] as const,
}

/** Context carried from a result list to the detail page: the match breakdown and where it was shown. */
export interface HitContext {
  hit: SearchHit
  searchLogId: string | null
  position: number
}

function useRememberHits() {
  const qc = useQueryClient()
  // Remember each hit so the job page can show its match breakdown without re-ranking.
  return (res: SearchResponse) => {
    res.results.forEach((hit, i) =>
      qc.setQueryData<HitContext>(keys.hit(hit.job_id), { hit, searchLogId: res.search_log_id, position: i + 1 }))
    return res
  }
}

export function useSearch(query: string, filters: JobFilters, useProfile: boolean) {
  const remember = useRememberHits()
  // Explicit TData: otherwise inference picks it up from placeholderData and fails.
  return useQuery<SearchResponse>({
    queryKey: keys.search(query, filters, useProfile),
    queryFn: ({ signal }) =>
      api<SearchResponse>('/jobs/search', {
        method: 'POST', signal,
        body: { query, filters, top_k: 20, use_profile: useProfile },
      }).then(remember),
    enabled: query.trim().length > 0,
    placeholderData: keepPreviousData, // keep old results on screen while refetching
    staleTime: 60_000,
  })
}

export function useRecommendations() {
  const remember = useRememberHits()
  return useQuery({
    queryKey: keys.recs,
    queryFn: ({ signal }) => api<SearchResponse>('/recommendations?top_k=20', { signal }).then(remember),
    staleTime: 5 * 60_000,
  })
}

export const useJob = (id: string) =>
  useQuery({ queryKey: keys.job(id), queryFn: ({ signal }) => api<JobDetail>(`/jobs/${id}`, { signal }) })

export const useHitContext = (id: string) =>
  useQuery<HitContext | null>({ queryKey: keys.hit(id), queryFn: () => null, staleTime: Infinity, gcTime: 30 * 60_000 })

export const useProfile = () => useQuery({ queryKey: keys.profile, queryFn: () => api<Profile>('/candidates/me') })

export const useRecentSearches = () =>
  useQuery({ queryKey: keys.recent, queryFn: () => api<RecentSearch[]>('/candidates/me/searches?limit=6') })

/** Fire-and-forget: a click or "not interested", attributed to the search that showed it. */
export function sendFeedback(jobId: string, type: 'click' | 'dismiss', ctx?: Pick<HitContext, 'searchLogId' | 'position'> | null) {
  void api('/recommendations/feedback', {
    method: 'POST',
    body: { job_id: jobId, interaction_type: type, search_log_id: ctx?.searchLogId ?? null, position: ctx?.position ?? null },
  }).catch(() => undefined) // analytics must never break the page
}

// ------------------------------------------------------------------ saved jobs

export function useSavedJobs() {
  return useInfiniteQuery({
    queryKey: keys.saved,
    queryFn: ({ pageParam, signal }) =>
      api<Page<SavedJob>>(`/saved-jobs?limit=20${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ''}`, { signal }),
    initialPageParam: '',
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
}

/** Ids of everything saved, for the bookmark state on cards (the API caps a page at 100). */
export const useSavedIds = () =>
  useQuery({
    queryKey: keys.savedIds,
    queryFn: () => api<Page<SavedJob>>('/saved-jobs?limit=100').then((p) => new Set(p.items.map((s) => s.job.id))),
    staleTime: 60_000,
  })

export function useToggleSave() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ jobId, saved }: { jobId: string; saved: boolean }) =>
      saved ? api(`/saved-jobs/${jobId}`, { method: 'DELETE' }) : api('/saved-jobs', { method: 'POST', body: { job_id: jobId } }),
    onMutate: async ({ jobId, saved }) => {
      await qc.cancelQueries({ queryKey: keys.savedIds })
      const prev = qc.getQueryData<Set<string>>(keys.savedIds)
      const next = new Set(prev)
      if (saved) next.delete(jobId)
      else next.add(jobId)
      qc.setQueryData(keys.savedIds, next)
      return { prev }
    },
    onError: (_e, _v, ctx) => qc.setQueryData(keys.savedIds, ctx?.prev),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.saved }),
  })
}

// ---------------------------------------------------------------- applications

export const useApplications = () =>
  useQuery({ queryKey: keys.applications, queryFn: () => api<Application[]>('/applications') })

export function useApply() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { job_id: string; notes?: string }) => api<Application>('/applications', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.applications }),
  })
}

export function useUpdateApplication() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; application_status?: ApplicationStatus; notes?: string | null }) =>
      api<Application>(`/applications/${id}`, { method: 'PATCH', body }),
    onSuccess: (updated) =>
      qc.setQueryData<Application[]>(keys.applications, (list) => list?.map((a) => (a.id === updated.id ? updated : a))),
  })
}

// ----------------------------------------------------------------- preferences

export const usePreferences = () =>
  useQuery({ queryKey: keys.preferences, queryFn: () => api<Preference[]>('/candidates/me/preferences') })

export function useSetPreference() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ key, value }: { key: PreferenceKey; value: Record<string, unknown> | null }) =>
      value === null
        ? api(`/candidates/me/preferences/${key}`, { method: 'DELETE' })
        : api(`/candidates/me/preferences/${key}`, { method: 'PUT', body: { value } }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.preferences })
      void qc.invalidateQueries({ queryKey: keys.recs }) // preferences change the ranking
    },
  })
}

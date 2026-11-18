import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type { Profile, Resume } from '@/lib/types'

export const MAX_RESUME_BYTES = 5 * 1024 * 1024
const busy = (r: Resume) => r.parsing_status === 'pending' || r.parsing_status === 'processing'

export const useResumes = () =>
  useQuery({
    queryKey: ['resumes'],
    queryFn: () => api<Resume[]>('/candidates/resumes'),
    // Parsing runs in the background on the server: poll only while something is in progress.
    refetchInterval: (q) => (q.state.data?.some(busy) ? 2000 : false),
  })

export function useUploadResume() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api<Resume>('/candidates/resume', { method: 'POST', form })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['resumes'] }),
  })
}

export interface ResumeApply {
  full_name?: string | null
  location?: string | null
  experience_years?: number | null
  profile_summary?: string | null
  skills: { name: string }[]
  education?: unknown[] | null
  projects?: unknown[] | null
}

export function useApplyResume() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ResumeApply }) =>
      api<Profile>(`/candidates/resumes/${id}/apply`, { method: 'POST', body }),
    onSuccess: (profile) => {
      qc.setQueryData(['profile'], profile)
      void qc.invalidateQueries({ queryKey: ['resumes'] })
      void qc.invalidateQueries({ queryKey: ['recommendations'] })
    },
  })
}

export function useDeleteResume() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api(`/candidates/resumes/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['resumes'] }),
  })
}

export function useReprocessResume() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api<Resume>(`/candidates/resumes/${id}/reprocess`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['resumes'] }),
  })
}

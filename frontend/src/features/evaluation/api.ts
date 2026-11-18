import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type { EvaluationRun } from '@/lib/types'

export const useEvaluationRuns = () =>
  useQuery({ queryKey: ['evaluations'], queryFn: () => api<EvaluationRun[]>('/evaluations?limit=200') })

export function useRunRetrievalEval() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (split: 'dev' | 'test') =>
      api<{ status: string }>('/evaluations/run', { method: 'POST', body: { experiment: 'retrieval', split } }),
    // The run takes about a minute in the background; refresh after that.
    onSuccess: () => setTimeout(() => void qc.invalidateQueries({ queryKey: ['evaluations'] }), 75_000),
  })
}

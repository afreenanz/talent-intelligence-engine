import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type { ChatResponse, Conversation, ConversationDetail } from '@/lib/types'

export const assistantKeys = {
  list: ['conversations'] as const,
  detail: (id: string) => ['conversation', id] as const,
}

export const useConversations = () =>
  useQuery({ queryKey: assistantKeys.list, queryFn: () => api<Conversation[]>('/agent/conversations') })

export const useConversation = (id: string | null) =>
  useQuery({
    queryKey: assistantKeys.detail(id ?? ''),
    queryFn: () => api<ConversationDetail>(`/agent/conversations/${id}`),
    enabled: !!id,
  })

/** After any turn: the conversation and anything the assistant may have changed. */
function useRefreshAfterTurn() {
  const qc = useQueryClient()
  return (res: ChatResponse) => {
    void qc.invalidateQueries({ queryKey: assistantKeys.detail(res.conversation_id) })
    void qc.invalidateQueries({ queryKey: assistantKeys.list })
    void qc.invalidateQueries({ queryKey: ['saved'] })
    void qc.invalidateQueries({ queryKey: ['preferences'] })
    void qc.invalidateQueries({ queryKey: ['recommendations'] })
  }
}

export function useSendMessage() {
  const refresh = useRefreshAfterTurn()
  return useMutation({
    mutationFn: (body: { message: string; conversation_id?: string | null }) =>
      api<ChatResponse>('/agent/chat', { method: 'POST', body }),
    onSuccess: refresh,
  })
}

export function useConfirm() {
  const refresh = useRefreshAfterTurn()
  return useMutation({
    mutationFn: ({ id, approved }: { id: string; approved: boolean }) =>
      api<ChatResponse>(`/agent/conversations/${id}/confirm`, { method: 'POST', body: { approved } }),
    onSuccess: refresh,
  })
}

export function useDeleteConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api(`/agent/conversations/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: assistantKeys.list }),
  })
}

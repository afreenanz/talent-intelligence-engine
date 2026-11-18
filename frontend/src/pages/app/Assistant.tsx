import { History, MessageSquarePlus, SendHorizontal, Trash2 } from 'lucide-react'
import { type FormEvent, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { Reply } from '@/features/assistant/Reply'
import { ActionText, Steps, Ungrounded } from '@/features/assistant/parts'
import { useConfirm, useConversation, useConversations, useDeleteConversation, useSendMessage } from '@/features/assistant/api'
import { ApiError } from '@/lib/api'
import { ago } from '@/lib/format'
import type { Conversation, Message, PendingAction } from '@/lib/types'
import { cn } from '@/lib/utils'

const EXAMPLES = [
  'Find remote backend jobs paying at least 15 LPA',
  'Which of my saved jobs fits me best, and why?',
  'What skills am I missing for data engineering roles?',
  'I prefer data roles from now on',
]

function errorText(e: unknown): string {
  if (e instanceof ApiError && e.code === 'rate_limited') return e.message // this app's own limit
  if (e instanceof ApiError && (e.status === 429 || e.status === 503)) {
    return 'The assistant is busy (free-tier rate limit). Wait a minute, then send again.'
  }
  return e instanceof Error ? e.message : 'Something went wrong. Try again.'
}

export default function Assistant() {
  const [params, setParams] = useSearchParams()
  const id = params.get('c')
  const conversation = useConversation(id)
  const send = useSendMessage()
  const confirm = useConfirm()
  const [draft, setDraft] = useState('')
  const [sentText, setSentText] = useState<string | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  const messages = conversation.data?.messages ?? []
  const last = messages.at(-1)
  const pending: PendingAction[] =
    conversation.data?.awaiting_confirmation && last?.role === 'assistant' ? last.tool_metadata?.pending_actions ?? [] : []
  const busy = send.isPending || confirm.isPending

  useEffect(() => { bottom.current?.scrollIntoView({ block: 'end' }) }, [messages.length, sentText, busy])

  const submit = (text: string, e?: FormEvent) => {
    e?.preventDefault()
    const message = text.trim()
    if (!message || busy || pending.length) return
    setSentText(message)
    setDraft('')
    send.mutate({ message, conversation_id: id }, {
      onSuccess: (res) => { if (res.conversation_id !== id) setParams({ c: res.conversation_id }) },
      onError: (err) => { setDraft(message); toast.error(errorText(err)) },
      onSettled: () => setSentText(null),
    })
  }

  const answer = (approved: boolean) =>
    id && confirm.mutate({ id, approved }, {
      onSuccess: () => toast(approved ? 'Done' : 'Cancelled. Nothing was changed.'),
      onError: (err) => toast.error(errorText(err)),
    })

  return (
    <div className="flex max-w-5xl gap-8 md:-my-8 md:h-[100svh]">
      <aside className="hidden w-60 shrink-0 flex-col py-8 lg:flex">
        <ConversationList activeId={id} onPick={(c) => setParams(c ? { c } : {})} />
      </aside>

      <section aria-label="Conversation" className="flex min-w-0 flex-1 flex-col py-8">
        <header className="mb-4 flex items-center justify-between gap-3">
          <h1 className="truncate text-h2 font-semibold tracking-[-0.02em]">{conversation.data?.title ?? 'Assistant'}</h1>
          <div className="flex gap-1">
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="ghost" size="sm" className="lg:hidden"><History aria-hidden="true" /> History</Button>
              </SheetTrigger>
              <SheetContent side="left" className="p-4">
                <SheetHeader className="sr-only"><SheetTitle>Conversations</SheetTitle></SheetHeader>
                <ConversationList activeId={id} onPick={(c) => setParams(c ? { c } : {})} />
              </SheetContent>
            </Sheet>
            {id && <Button variant="outline" size="sm" onClick={() => setParams({})}><MessageSquarePlus aria-hidden="true" /> New chat</Button>}
          </div>
        </header>

        <div className="min-h-0 flex-1 pr-1 md:overflow-y-auto" aria-live="polite">
          {!id && !sentText ? (
            <Welcome onPick={(t) => submit(t)} />
          ) : (
            <ol className="space-y-6 pb-4">
              {messages.map((m) => <MessageItem key={m.id} message={m} />)}
              {sentText && (
                <>
                  <MessageItem message={{ id: 'sending', role: 'user', content: sentText, tool_metadata: null, created_at: '' }} />
                  <li className="text-small text-muted-foreground"><span className="animate-pulse">Working on it…</span></li>
                </>
              )}
              {confirm.isPending && <li className="text-small text-muted-foreground"><span className="animate-pulse">Working on it…</span></li>}
            </ol>
          )}
          {pending.length > 0 && !confirm.isPending && (
            <div role="group" aria-labelledby="confirm-title" className="mb-4 rounded-lg border border-signal/40 bg-signal/5 p-4">
              <h2 id="confirm-title" className="font-semibold tracking-tight">Confirm before I do this</h2>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {pending.map((a, i) => <li key={i}><ActionText action={a} /></li>)}
              </ul>
              <div className="mt-4 flex gap-2">
                <Button size="sm" onClick={() => answer(true)}>Yes, go ahead</Button>
                <Button size="sm" variant="ghost" onClick={() => answer(false)}>No, cancel</Button>
              </div>
            </div>
          )}
          <div ref={bottom} />
        </div>

        <form onSubmit={(e) => submit(draft, e)} className="sticky bottom-3 mt-2 flex items-end gap-2 rounded-lg border border-line bg-card p-2 focus-within:border-ring md:static">
          <Textarea aria-label="Message the assistant" rows={1} maxLength={2000} value={draft}
            placeholder={pending.length ? 'Answer the confirmation above first' : 'Ask about jobs, your matches or your preferences'}
            disabled={pending.length > 0}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(draft) } }}
            className="max-h-40 min-h-9 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent" />
          <Button type="submit" size="icon" aria-label="Send" disabled={!draft.trim() || busy || pending.length > 0}>
            <SendHorizontal aria-hidden="true" />
          </Button>
        </form>
        <p className="mt-2 text-micro text-muted-foreground">
          Messages are processed by Google Gemini on its free tier, where Google may use them to improve its models. Don’t share anything you wouldn’t want stored.
        </p>
      </section>
    </div>
  )
}

function MessageItem({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <li className="flex justify-end">
        <p className="max-w-[80%] whitespace-pre-wrap rounded-lg rounded-br-sm bg-secondary px-3.5 py-2">{message.content}</p>
      </li>
    )
  }
  const meta = message.tool_metadata
  return (
    <li className="max-w-[68ch]">
      <Reply text={message.content} />
      {meta?.grounded === false && <Ungrounded />}
      <Steps calls={meta?.tool_calls} />
    </li>
  )
}

function Welcome({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="max-w-[60ch] pt-4">
      <p className="text-lede">Ask in plain words. I search the live job index, explain matches using your profile, and ask before I save anything or change your preferences.</p>
      <h2 className="mt-8 text-small text-muted-foreground">Try one of these</h2>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2">
        {EXAMPLES.map((t) => (
          <li key={t}>
            <button type="button" onClick={() => onPick(t)}
              className="w-full rounded-lg border border-line px-3.5 py-3 text-left text-small hover:border-foreground/20 hover:bg-muted/40">
              {t}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function ConversationList({ activeId, onPick }: { activeId: string | null; onPick: (id: string | null) => void }) {
  const list = useConversations()
  const del = useDeleteConversation()
  return (
    <nav aria-label="Conversations" className="flex min-h-0 flex-1 flex-col">
      <Button variant="outline" className="mb-4 justify-start" onClick={() => onPick(null)}>
        <MessageSquarePlus aria-hidden="true" /> New chat
      </Button>
      <h2 className="mb-2 text-micro text-muted-foreground">History</h2>
      {list.data?.length === 0 && <p className="text-small text-muted-foreground">No conversations yet.</p>}
      <ul className="-mx-2 min-h-0 flex-1 space-y-0.5 overflow-y-auto">
        {list.data?.map((c: Conversation) => (
          <li key={c.id} className={cn('group flex items-center rounded-md hover:bg-muted/50', c.id === activeId && 'bg-muted')}>
            <button type="button" onClick={() => onPick(c.id)} aria-current={c.id === activeId ? 'page' : undefined}
              className="min-w-0 flex-1 px-2 py-1.5 text-left">
              <span className="block truncate text-small">{c.title}</span>
              <span className="block text-micro text-muted-foreground">{ago(c.updated_at)}</span>
            </button>
            <Button variant="ghost" size="icon-xs" aria-label={`Delete “${c.title}”`}
              className="mr-1 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
              onClick={() => del.mutate(c.id, {
                onSuccess: () => { if (c.id === activeId) onPick(null); toast('Conversation deleted') },
              })}>
              <Trash2 aria-hidden="true" />
            </Button>
          </li>
        ))}
      </ul>
    </nav>
  )
}

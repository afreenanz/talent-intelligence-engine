import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Notice, PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useApplications, useUpdateApplication } from '@/features/jobs/api'
import { JobFacts, ListSkeleton } from '@/features/jobs/components'
import { APP_STATUS, NEXT_STATUS as NEXT, ago } from '@/lib/format'
import type { Application, ApplicationStatus } from '@/lib/types'
import { cn } from '@/lib/utils'

/** The pipeline in order. Rejected and withdrawn are outcomes, shown apart from the stages. */
const STAGES: ApplicationStatus[] = ['applied', 'screening', 'interviewing', 'offer']
const CLOSED: ApplicationStatus[] = ['rejected', 'withdrawn']

export default function Applications() {
  const apps = useApplications()
  const header = <PageHeader title="Applications">Every role you marked as applied, and where each one stands.</PageHeader>

  if (apps.isPending) return <div className="max-w-4xl">{header}<ListSkeleton rows={3} /></div>
  if (apps.isError) {
    return (
      <div className="max-w-4xl">{header}
        <Notice tone="error" title="Couldn’t load applications" action={<Button variant="outline" onClick={() => apps.refetch()}>Try again</Button>}>
          {apps.error.message}
        </Notice>
      </div>
    )
  }
  const list = apps.data
  if (!list.length) {
    return (
      <div className="max-w-4xl">{header}
        <Notice title="No applications tracked yet" action={<Button asChild><Link to="/app/recommendations">See your matches</Link></Button>}>
          Open a job and choose “Mark as applied” to track it here.
        </Notice>
      </div>
    )
  }
  const count = (s: ApplicationStatus) => list.filter((a) => a.application_status === s).length
  return (
    <div className="max-w-4xl">
      {header}
      <section aria-label="Pipeline" className="mb-8">
        <ol className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4">
          {STAGES.map((s) => (
            <li key={s} className="bg-background px-4 py-3">
              <p className="tnum text-h3 font-semibold leading-none">{count(s)}</p>
              <p className="mt-1.5 text-small text-muted-foreground">{APP_STATUS[s]}</p>
            </li>
          ))}
        </ol>
        {CLOSED.some(count) && (
          <p className="mt-2 text-small text-muted-foreground">
            Closed: {CLOSED.filter(count).map((s) => `${count(s)} ${APP_STATUS[s].toLowerCase()}`).join(', ')}
          </p>
        )}
      </section>
      <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line">
        {list.map((a) => <ApplicationRow key={a.id} app={a} />)}
      </ul>
    </div>
  )
}

function ApplicationRow({ app }: { app: Application }) {
  const update = useUpdateApplication()
  const [notes, setNotes] = useState(app.notes ?? '')
  const closed = CLOSED.includes(app.application_status)
  const saveNotes = () => {
    const next = notes.trim()
    if (next === (app.notes ?? '')) return
    update.mutate({ id: app.id, notes: next || null }, {
      onSuccess: () => toast('Notes saved'),
      onError: (e) => toast.error(e.message),
    })
  }
  return (
    <li className={cn('grid gap-4 px-5 py-5 sm:grid-cols-[1fr_11rem]', closed && 'opacity-70')}>
      <div className="min-w-0">
        <h2 className="font-semibold tracking-tight">
          <Link to={`/app/jobs/${app.job.id}`} className="hover:underline">{app.job.title}</Link>
        </h2>
        <p className="text-small">{app.job.company}</p>
        <JobFacts job={app.job} className="mt-1" />
        <label className="mt-3 block">
          <span className="sr-only">Notes for {app.job.title}</span>
          <Textarea rows={1} maxLength={2000} placeholder="Add a note" value={notes}
            onChange={(e) => setNotes(e.target.value)} onBlur={saveNotes}
            className="min-h-0 resize-y border-transparent bg-transparent px-0 shadow-none focus-visible:border-input focus-visible:px-2" />
        </label>
      </div>
      <div className="space-y-2">
        {NEXT[app.application_status].length === 0 ? (
          <p className="flex h-9 items-center rounded-md border border-line px-2.5 text-sm">{APP_STATUS[app.application_status]}</p>
        ) : (
        <Select value={app.application_status}
          onValueChange={(v) => update.mutate({ id: app.id, application_status: v as ApplicationStatus }, {
            onSuccess: () => toast(`Moved to ${APP_STATUS[v as ApplicationStatus].toLowerCase()}`),
            onError: (e) => toast.error(e.message),
          })}>
          <SelectTrigger aria-label={`Status for ${app.job.title}`} className="w-full"><SelectValue /></SelectTrigger>
          <SelectContent>
            {[app.application_status, ...NEXT[app.application_status]].map((s) => (
              <SelectItem key={s} value={s}>{s === app.application_status ? APP_STATUS[s] : `Move to ${APP_STATUS[s].toLowerCase()}`}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        )}
        <p className="text-micro text-muted-foreground">
          Applied {ago(app.created_at)}{app.updated_at !== app.created_at && `, updated ${ago(app.updated_at)}`}
        </p>
      </div>
    </li>
  )
}

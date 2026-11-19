import { ArrowLeft, Check } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { Notice } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useApplications, useApply, useHitContext, useJob, useProfile } from '@/features/jobs/api'
import { JobFacts, Listed, MatchBreakdown, SaveButton } from '@/features/jobs/components'
import { ApiError } from '@/lib/api'
import { APP_STATUS } from '@/lib/format'
import type { JobDetail as Job, SkillImportance } from '@/lib/types'
import { cn } from '@/lib/utils'

const GROUPS: { importance: SkillImportance; title: string }[] = [
  { importance: 'required', title: 'Required' },
  { importance: 'preferred', title: 'Nice to have' },
  { importance: 'mentioned', title: 'Also mentioned' },
]

export default function JobDetail() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const job = useJob(id)
  const { data: ctx } = useHitContext(id)

  const back = (
    <Button variant="ghost" size="sm" className="-ml-2 mb-6 text-muted-foreground"
      onClick={() => (window.history.length > 1 ? navigate(-1) : navigate('/app/search'))}>
      <ArrowLeft aria-hidden="true" /> Back
    </Button>
  )

  if (job.isPending) return <div className="max-w-5xl">{back}<p className="text-muted-foreground">Loading the job…</p></div>
  if (job.isError) {
    const missing = job.error instanceof ApiError && job.error.status === 404
    return (
      <div className="max-w-5xl">
        {back}
        <Notice tone="error" title={missing ? 'This job doesn’t exist' : 'Couldn’t load this job'}
          action={<Button asChild variant="outline"><Link to="/app/search">Search jobs</Link></Button>}>
          {missing ? 'It may have been removed. Search for similar roles instead.' : job.error.message}
        </Notice>
      </div>
    )
  }

  const j = job.data
  return (
    <div className="max-w-5xl">
      {back}
      <header className="flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0">
          <h1 className="text-h1 font-semibold leading-tight tracking-[-0.03em]">{j.title}</h1>
          <p className="mt-1 text-lede">{j.company}</p>
          <JobFacts job={j} className="mt-3" />
          <p className="mt-2 text-micro text-muted-foreground">
            <Listed iso={j.listed_at} />
          </p>
          {j.status !== 'active' && (
            <p className="mt-3 inline-block rounded-md border border-rose/40 px-2.5 py-1 text-small text-rose">
              This role is no longer open.
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {j.apply_url && (
            <Button asChild variant="outline">
              <a href={j.apply_url} target="_blank" rel="noopener noreferrer">View original ad</a>
            </Button>
          )}
          <SaveButton jobId={j.id} withLabel />
          <ApplyAction job={j} />
        </div>
      </header>

      <div className="mt-10 grid gap-10 lg:grid-cols-[1fr_22rem]">
        <div className="min-w-0 space-y-10">
          <Skills job={j} />
          <section aria-labelledby="about">
            <h2 id="about" className="font-semibold tracking-tight">About the role</h2>
            <p className="mt-3 max-w-[70ch] whitespace-pre-line text-muted-foreground">{j.description}</p>
          </section>
        </div>
        <aside className="lg:sticky lg:top-8 lg:self-start">
          {ctx ? (
            <MatchBreakdown hit={ctx.hit} />
          ) : (
            <Notice title="No match breakdown here">
              Open this job from Search or For you to see how it scores against your profile.
            </Notice>
          )}
        </aside>
      </div>
    </div>
  )
}

function Skills({ job }: { job: Job }) {
  const { data: profile } = useProfile()
  const mine = new Set(profile?.skills.map((s) => s.name.toLowerCase()))
  const groups = GROUPS.map((g) => ({ ...g, skills: job.skills.filter((s) => s.importance === g.importance) }))
    .filter((g) => g.skills.length)
  if (!groups.length) return null
  const have = job.skills.filter((s) => mine.has(s.name.toLowerCase())).length
  return (
    <section aria-labelledby="skills">
      <h2 id="skills" className="font-semibold tracking-tight">Skills</h2>
      {profile && (
        <p className="mt-1 text-small text-muted-foreground">
          You have <span className="tnum">{have}</span> of <span className="tnum">{job.skills.length}</span>.
        </p>
      )}
      <div className="mt-4 space-y-4">
        {groups.map((g) => (
          <div key={g.importance}>
            <h3 className="text-micro text-muted-foreground">{g.title}</h3>
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {g.skills.map((s) => {
                const has = mine.has(s.name.toLowerCase())
                return (
                  <li key={s.skill_id}
                    className={cn('inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-small',
                      has ? 'border-sage/40 text-foreground' : 'border-line text-muted-foreground')}>
                    {has && <Check aria-hidden="true" className="size-3.5 text-sage" />}
                    {s.name}
                    {has && <span className="sr-only"> (you have this)</span>}
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </div>
    </section>
  )
}

function ApplyAction({ job }: { job: Job }) {
  const apps = useApplications()
  const apply = useApply()
  const [open, setOpen] = useState(false)
  const [notes, setNotes] = useState('')
  const existing = apps.data?.find((a) => a.job.id === job.id)

  if (existing) {
    return (
      <Button asChild variant="secondary">
        <Link to="/app/applications">{APP_STATUS[existing.application_status]}</Link>
      </Button>
    )
  }
  if (job.status !== 'active') return null
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button>Mark as applied</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Mark as applied</DialogTitle>
          <DialogDescription>
            This tracks the application here. It doesn’t send anything to {job.company}.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="notes">Notes (optional)</Label>
          <Textarea id="notes" rows={3} maxLength={2000} placeholder="Referral, contact name, salary discussed…"
            value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          <Button disabled={apply.isPending}
            onClick={() => apply.mutate({ job_id: job.id, ...(notes.trim() ? { notes: notes.trim() } : {}) }, {
              onSuccess: () => { setOpen(false); toast('Marked as applied') },
              onError: (e) => toast.error(e.message),
            })}>
            {apply.isPending ? 'Saving…' : 'Mark as applied'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

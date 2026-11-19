import { Bookmark, BookmarkCheck, Check, Minus, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { type HitContext, sendFeedback, useSavedIds, useToggleSave } from '@/features/jobs/api'
import { FEATURE_LABEL, JOB_TYPE, WORK_MODE, ago, experience, fit, place, salary } from '@/lib/format'
import type { JobSummary, SearchHit } from '@/lib/types'
import { cn } from '@/lib/utils'

const FEED_SITES: Record<string, string> = { adzuna_in: 'https://www.adzuna.in' }
const isSynthetic = (source: string) => source.startsWith('synthetic')

/**
 * Where a listing came from. Real feed listings carry the provider's label: Adzuna's terms ask for
 * the word "Adzuna", at least 116 x 23 px, linked to the local Adzuna site, on every displayed ad.
 * Demo listings say they're synthetic.
 */
export function SourceTag({ source }: { source: string }) {
  const site = FEED_SITES[source]
  if (site) {
    return (
      <a href={site} target="_blank" rel="noopener noreferrer"
        className="relative z-[1] inline-flex h-[23px] min-w-[116px] items-center justify-center rounded-full border border-line px-2.5 text-micro font-semibold text-foreground hover:border-foreground/30">
        Jobs by Adzuna
      </a>
    )
  }
  return isSynthetic(source) ? <span className="text-micro text-muted-foreground/80">Synthetic demo listing</span> : null
}

/** Plain facts about a job, as separate items (no dot-joined meta string). */
export function JobFacts({ job, className }: { job: JobSummary; className?: string }) {
  const items = [
    place(job),
    job.location_type && job.location_type !== 'remote' ? WORK_MODE[job.location_type] : null,
    salary(job),
    experience(job),
    job.employment_type && job.employment_type !== 'full_time' ? JOB_TYPE[job.employment_type] : null,
  ].filter(Boolean) as string[]
  return (
    <ul className={cn('flex flex-wrap items-center gap-x-4 gap-y-1 text-small text-muted-foreground', className)}>
      {items.map((t) => <li key={t}>{t}</li>)}
      <li><SourceTag source={job.source} /></li>
    </ul>
  )
}

/** Fit score: a number plus a hairline meter. Amber is reserved for this. */
export function FitMeter({ score, className }: { score: number | null | undefined; className?: string }) {
  const value = fit(score)
  if (value === null) return null
  return (
    <div className={cn('w-20 shrink-0 text-right', className)}>
      <p className="tnum text-h3 font-semibold leading-none tracking-tight">{value}</p>
      <p className="mt-1 text-micro text-muted-foreground">fit score</p>
      <div className="mt-1.5 h-0.5 overflow-hidden rounded-full bg-line" aria-hidden="true">
        <div className="h-full rounded-full bg-signal" style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}

/** The 1–2 explanation lines that matter in a list: what matches, what's missing. */
export function ReasonLines({ lines }: { lines: string[] | null | undefined }) {
  const shown = (lines ?? []).filter((l) => !l.startsWith('Not enough information') && !l.startsWith('Biggest factor'))
  const good = shown.find((l) => !l.startsWith('Missing'))
  const missing = shown.find((l) => l.startsWith('Missing'))
  if (!good && !missing) return null
  return (
    <ul className="mt-3 space-y-1 text-small">
      {good && <li className="flex gap-2"><Check aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-sage" />{good}</li>}
      {missing && <li className="flex gap-2"><Minus aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-rose" />{missing}</li>}
    </ul>
  )
}

export function SaveButton({ jobId, withLabel = false }: { jobId: string; withLabel?: boolean }) {
  const { data: savedIds } = useSavedIds()
  const toggle = useToggleSave()
  const saved = savedIds?.has(jobId) ?? false
  const Icon = saved ? BookmarkCheck : Bookmark
  const label = saved ? 'Saved' : 'Save'
  return (
    <Button
      type="button" variant={withLabel ? 'outline' : 'ghost'} size={withLabel ? 'default' : 'icon'}
      aria-pressed={saved} aria-label={withLabel ? undefined : saved ? 'Remove from saved' : 'Save job'}
      onClick={() => toggle.mutate({ jobId, saved }, {
        onSuccess: () => toast(saved ? 'Removed from saved' : 'Saved'),
        onError: () => toast.error('Couldn’t update saved jobs. Try again.'),
      })}
    >
      <Icon className={cn(saved && 'text-signal')} aria-hidden="true" />
      {withLabel && label}
    </Button>
  )
}

/** One ranked result. `rank` is shown because the list IS an ordering. */
export function JobRow({ hit, rank, ctx, onDismiss, aside }: {
  hit: SearchHit
  rank: number
  ctx: Pick<HitContext, 'searchLogId' | 'position'>
  onDismiss?: () => void
  aside?: ReactNode
}) {
  return (
    <li className="group relative grid grid-cols-[2rem_1fr_auto] gap-x-4 px-5 py-5 hover:bg-muted/40">
      <span className="tnum pt-0.5 text-small text-muted-foreground">{rank}</span>
      <div className="min-w-0">
        <h3 className="font-semibold tracking-tight">
          <Link to={`/app/jobs/${hit.job_id}`} onClick={() => sendFeedback(hit.job_id, 'click', ctx)}
            className="after:absolute after:inset-0 hover:underline focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-ring">
            {hit.title}
          </Link>
        </h3>
        <p className="text-small">{hit.company}</p>
        {hit.job && <JobFacts job={hit.job} className="mt-1" />}
        {hit.exploration && (
          <p className="mt-2 text-micro text-signal-soft">Outside your usual roles: shown so your matches don’t narrow too far</p>
        )}
        <ReasonLines lines={hit.explanation} />
      </div>
      <div className="relative z-[1] flex flex-col items-end justify-between gap-3">
        <FitMeter score={hit.score} />
        <div className="flex items-center gap-1">
          {aside}
          {onDismiss && (
            <Button type="button" variant="ghost" size="icon" aria-label={`Not interested in ${hit.title}`} onClick={onDismiss}>
              <X aria-hidden="true" />
            </Button>
          )}
          <SaveButton jobId={hit.job_id} />
        </div>
      </div>
    </li>
  )
}

/** Why a job ranks where it does: each factor's contribution to the score, largest first. */
export function MatchBreakdown({ hit }: { hit: SearchHit }) {
  const contributions = Object.entries(hit.contributions ?? {}).sort((a, b) => b[1] - a[1])
  const max = Math.max(...contributions.map(([, v]) => v), 0.0001)
  const unknown = new Set(hit.missing_features ?? [])
  return (
    <section aria-labelledby="why" className="rounded-lg border border-line bg-card p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id="why" className="font-semibold tracking-tight">Why it ranks here</h2>
          <p className="mt-1 text-small text-muted-foreground">Each bar is how much a factor added to the fit score.</p>
        </div>
        <FitMeter score={hit.score} />
      </div>
      <ul className="mt-5 space-y-2.5">
        {contributions.map(([k, v]) => (
          <li key={k} className="grid grid-cols-[9.5rem_1fr_2.5rem] items-center gap-3 text-small">
            <span className="text-muted-foreground">{FEATURE_LABEL[k] ?? k}</span>
            <span className="h-1.5 overflow-hidden rounded-full bg-line" aria-hidden="true">
              <span className={cn('block h-full rounded-full', unknown.has(k) ? 'bg-muted-foreground/40' : 'bg-foreground/70')}
                style={{ width: `${(v / max) * 100}%` }} />
            </span>
            <span className="tnum text-right">{unknown.has(k) ? '?' : `+${Math.round(v * 100)}`}</span>
          </li>
        ))}
      </ul>
      {unknown.size > 0 && (
        <p className="mt-4 text-micro text-muted-foreground">
          “?” means the job or your profile doesn’t say, so the factor counts as neutral.
        </p>
      )}
      {(hit.explanation?.length ?? 0) > 0 && (
        <ul className="mt-5 space-y-1.5 border-t border-line pt-4 text-small">
          {hit.explanation!.map((l) => <li key={l}>{l}</li>)}
        </ul>
      )}
    </section>
  )
}

export function ListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <ul aria-hidden="true" className="divide-y divide-line rounded-lg border border-line">
      {Array.from({ length: rows }, (_, i) => (
        <li key={i} className="space-y-2 px-5 py-5">
          <div className="h-4 w-1/3 animate-pulse rounded bg-muted" />
          <div className="h-3 w-1/2 animate-pulse rounded bg-muted" />
        </li>
      ))}
    </ul>
  )
}

export function Listed({ iso }: { iso: string }) {
  return <time dateTime={iso}>Listed {ago(iso)}</time>
}

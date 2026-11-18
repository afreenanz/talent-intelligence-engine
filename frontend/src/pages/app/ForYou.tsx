import { RefreshCw, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { BorderBeam } from '@/components/brand/BorderBeam'
import { Notice, PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { sendFeedback, useRecommendations } from '@/features/jobs/api'
import { FitMeter, JobFacts, JobRow, ListSkeleton, ReasonLines, SaveButton } from '@/features/jobs/components'
import { ApiError } from '@/lib/api'
import type { SearchHit } from '@/lib/types'

export default function ForYou() {
  const recs = useRecommendations()
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const logId = recs.data?.search_log_id ?? null
  const all = recs.data?.results ?? []
  const hits = all.filter((h) => !dismissed.has(h.job_id))

  const dismiss = (hit: SearchHit) => {
    sendFeedback(hit.job_id, 'dismiss', { searchLogId: logId, position: all.indexOf(hit) + 1 })
    setDismissed((s) => new Set(s).add(hit.job_id))
    toast(`Hidden: ${hit.title}`, { description: 'Fewer roles like this will appear next time.' })
  }

  const header = (
    <PageHeader title="For you"
      actions={recs.data && (
        <Button variant="outline" size="sm" disabled={recs.isFetching} onClick={() => { setDismissed(new Set()); void recs.refetch() }}>
          <RefreshCw aria-hidden="true" className={recs.isFetching ? 'animate-spin' : undefined} /> Refresh
        </Button>
      )}>
      Ranked for your profile and preferences. What you open, save and hide adjusts the next ranking.
    </PageHeader>
  )

  if (recs.isPending) return <div className="max-w-4xl">{header}<ListSkeleton /></div>
  if (recs.isError) {
    const empty = recs.error instanceof ApiError && recs.error.code === 'empty_search'
    return (
      <div className="max-w-4xl">
        {header}
        {empty ? (
          <Notice title="Add your skills to get matches"
            action={<div className="flex gap-2">
              <Button asChild><Link to="/app/resume">Upload your résumé</Link></Button>
              <Button asChild variant="outline"><Link to="/app/search">Search instead</Link></Button>
            </div>}>
            Recommendations come from your profile, and it has no skills or summary yet.
          </Notice>
        ) : (
          <Notice tone="error" title="Couldn’t load your matches" action={<Button variant="outline" onClick={() => recs.refetch()}>Try again</Button>}>
            {recs.error.message}
          </Notice>
        )}
      </div>
    )
  }
  if (!hits.length) {
    return <div className="max-w-4xl">{header}<Notice title="Nothing left to show">Refresh for a new ranking, or search for something specific.</Notice></div>
  }

  const [top, ...rest] = hits
  return (
    <div className="max-w-4xl">
      {header}
      <TopMatch hit={top} ctx={{ searchLogId: logId, position: all.indexOf(top) + 1 }} onDismiss={() => dismiss(top)} />
      {rest.length > 0 && (
        <>
          <h2 className="mb-3 mt-10 text-small text-muted-foreground">More matches</h2>
          <ol className="divide-y divide-line overflow-hidden rounded-lg border border-line">
            {rest.map((hit, i) => (
              <JobRow key={hit.job_id} hit={hit} rank={i + 2} ctx={{ searchLogId: logId, position: all.indexOf(hit) + 1 }}
                onDismiss={() => dismiss(hit)} />
            ))}
          </ol>
        </>
      )}
    </div>
  )
}

/** The one place the beam appears in the app: your best match right now. */
function TopMatch({ hit, ctx, onDismiss }: {
  hit: SearchHit
  ctx: { searchLogId: string | null; position: number }
  onDismiss: () => void
}) {
  return (
    <BorderBeam radius={20} className="live-card">
      <article aria-labelledby="top-match" className="relative grid gap-6 p-7 sm:grid-cols-[1fr_auto]">
        <div className="min-w-0">
          <p className="text-micro text-signal">Best match right now</p>
          <h2 id="top-match" className="mt-2 text-h2 font-semibold leading-tight tracking-[-0.02em]">
            <Link to={`/app/jobs/${hit.job_id}`} onClick={() => sendFeedback(hit.job_id, 'click', ctx)} className="hover:underline">
              {hit.title}
            </Link>
          </h2>
          <p className="mt-1">{hit.company}</p>
          {hit.job && <JobFacts job={hit.job} className="mt-2" />}
          <ReasonLines lines={hit.explanation} />
        </div>
        <div className="flex flex-row items-end justify-between gap-4 sm:flex-col">
          <FitMeter score={hit.score} />
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" aria-label={`Not interested in ${hit.title}`} onClick={onDismiss}>
              <X aria-hidden="true" />
            </Button>
            <SaveButton jobId={hit.job_id} />
            <Button asChild size="sm" className="ml-1">
              <Link to={`/app/jobs/${hit.job_id}`} onClick={() => sendFeedback(hit.job_id, 'click', ctx)}>View role</Link>
            </Button>
          </div>
        </div>
      </article>
    </BorderBeam>
  )
}

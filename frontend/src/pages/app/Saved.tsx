import { Link } from 'react-router'

import { Notice, PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { useSavedJobs } from '@/features/jobs/api'
import { JobFacts, ListSkeleton, SaveButton } from '@/features/jobs/components'
import { ago } from '@/lib/format'

export default function Saved() {
  const saved = useSavedJobs()
  const items = saved.data?.pages.flatMap((p) => p.items) ?? []
  const header = <PageHeader title="Saved">Jobs you bookmarked, newest first.</PageHeader>

  if (saved.isPending) return <div className="max-w-4xl">{header}<ListSkeleton rows={3} /></div>
  if (saved.isError) {
    return (
      <div className="max-w-4xl">{header}
        <Notice tone="error" title="Couldn’t load saved jobs" action={<Button variant="outline" onClick={() => saved.refetch()}>Try again</Button>}>
          {saved.error.message}
        </Notice>
      </div>
    )
  }
  if (!items.length) {
    return (
      <div className="max-w-4xl">{header}
        <Notice title="Nothing saved yet" action={<Button asChild><Link to="/app/recommendations">See your matches</Link></Button>}>
          Use the bookmark on any job to keep it here.
        </Notice>
      </div>
    )
  }
  return (
    <div className="max-w-4xl">
      {header}
      <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line">
        {items.map(({ job, saved_at }) => (
          <li key={job.id} className="relative flex items-start justify-between gap-4 px-5 py-4 hover:bg-muted/40">
            <div className="min-w-0">
              <h2 className="font-semibold tracking-tight">
                <Link to={`/app/jobs/${job.id}`} className="after:absolute after:inset-0 hover:underline">{job.title}</Link>
              </h2>
              <p className="text-small">{job.company}</p>
              <JobFacts job={job} className="mt-1" />
              {job.status !== 'active' && <p className="mt-2 text-micro text-rose">No longer open</p>}
            </div>
            <div className="relative z-[1] flex items-center gap-3">
              <time dateTime={saved_at} className="hidden text-micro text-muted-foreground sm:block">Saved {ago(saved_at)}</time>
              <SaveButton jobId={job.id} />
            </div>
          </li>
        ))}
      </ul>
      {saved.hasNextPage && (
        <Button variant="outline" className="mt-4" disabled={saved.isFetchingNextPage} onClick={() => saved.fetchNextPage()}>
          {saved.isFetchingNextPage ? 'Loading…' : 'Show more'}
        </Button>
      )}
    </div>
  )
}

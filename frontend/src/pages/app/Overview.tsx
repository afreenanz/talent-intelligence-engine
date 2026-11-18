import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/context'
import { useApplications, useProfile, useRecentSearches, useRecommendations, useSavedIds } from '@/features/jobs/api'
import { FitMeter, JobFacts } from '@/features/jobs/components'
import { APP_STATUS } from '@/lib/format'
import type { ApplicationStatus } from '@/lib/types'

const STAGES: ApplicationStatus[] = ['applied', 'screening', 'interviewing', 'offer']

/** The dashboard: where your profile stands, your best matches, and what you're tracking. Real data only. */
export default function Overview() {
  const { account } = useAuth()
  const profile = useProfile()
  const p = profile.data
  const missing = p
    ? ([!p.skills.length && 'skills', p.experience_years == null && 'experience', !p.location && 'location'].filter(Boolean) as string[])
    : []
  const ready = !!p && p.skills.length > 0

  return (
    <div className="max-w-5xl">
      <h1 className="text-h1 font-semibold tracking-[-0.03em]">
        {p?.full_name ? `Hello, ${p.full_name.split(' ')[0]}.` : 'Welcome.'}
      </h1>
      <p className="mt-2 text-muted-foreground">Signed in as {account?.email}.</p>

      {profile.isPending ? <p className="mt-8 text-muted-foreground">Loading your profile…</p> : (
        <div className="mt-10 grid gap-6 lg:grid-cols-[1fr_20rem]">
          <div className="min-w-0 space-y-6">
            {missing.length > 0 && (
              <section aria-labelledby="next" className="rounded-lg border border-line bg-card p-6">
                <h2 id="next" className="text-h3 font-semibold tracking-tight">Finish your profile to get ranked matches</h2>
                <p className="mt-2 max-w-[60ch] text-muted-foreground">
                  Still missing: {missing.join(', ')}. The fastest way is to upload your résumé. You review what we extract before anything is saved.
                </p>
                <Button asChild className="mt-5"><Link to="/app/resume">Upload your résumé</Link></Button>
              </section>
            )}
            {ready && <TopMatches />}
          </div>
          <div className="space-y-6">
            {p && (
              <section aria-labelledby="profile" className="rounded-lg border border-line p-5">
                <h2 id="profile" className="font-semibold tracking-tight">Your profile</h2>
                <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-small">
                  <dt className="text-muted-foreground">Skills</dt><dd className="tnum">{p.skills.length}</dd>
                  <dt className="text-muted-foreground">Experience</dt><dd>{p.experience_years == null ? 'Not set' : `${p.experience_years} yrs`}</dd>
                  <dt className="text-muted-foreground">Location</dt><dd>{p.location ?? 'Not set'}</dd>
                </dl>
                <div className="mt-4 flex gap-2">
                  <Button asChild variant="outline" size="sm"><Link to="/app/resume">Résumé</Link></Button>
                  <Button asChild variant="outline" size="sm"><Link to="/app/preferences">Preferences</Link></Button>
                </div>
              </section>
            )}
            <Tracking />
            <Recent />
          </div>
        </div>
      )}
    </div>
  )
}

function TopMatches() {
  const recs = useRecommendations()
  const top = recs.data?.results.slice(0, 3) ?? []
  return (
    <section aria-labelledby="matches">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 id="matches" className="text-h3 font-semibold tracking-tight">Your best matches</h2>
        <Link to="/app/recommendations" className="text-small text-muted-foreground hover:text-foreground">See all</Link>
      </div>
      {recs.isPending ? <p className="text-muted-foreground">Ranking jobs for you…</p> : recs.isError ? (
        <p className="text-muted-foreground">Couldn’t load matches right now.</p>
      ) : (
        <ol className="divide-y divide-line rounded-lg border border-line">
          {top.map((h) => (
            <li key={h.job_id} className="relative flex items-start justify-between gap-4 px-5 py-4 hover:bg-muted/40">
              <div className="min-w-0">
                <h3 className="font-semibold tracking-tight">
                  <Link to={`/app/jobs/${h.job_id}`} className="after:absolute after:inset-0 hover:underline">{h.title}</Link>
                </h3>
                <p className="text-small">{h.company}</p>
                {h.job && <JobFacts job={h.job} className="mt-1" />}
              </div>
              <FitMeter score={h.score} />
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function Tracking() {
  const apps = useApplications()
  const saved = useSavedIds()
  const count = (s: ApplicationStatus) => apps.data?.filter((a) => a.application_status === s).length ?? 0
  return (
    <section aria-labelledby="tracking" className="rounded-lg border border-line p-5">
      <h2 id="tracking" className="font-semibold tracking-tight">Tracking</h2>
      <dl className="mt-3 grid grid-cols-[1fr_auto] gap-y-1.5 text-small">
        <dt><Link to="/app/saved" className="text-muted-foreground hover:text-foreground">Saved jobs</Link></dt>
        <dd className="tnum text-right">{saved.data?.size ?? '…'}</dd>
        {STAGES.map((s) => (
          <div key={s} className="contents">
            <dt><Link to="/app/applications" className="text-muted-foreground hover:text-foreground">{APP_STATUS[s]}</Link></dt>
            <dd className="tnum text-right">{apps.data ? count(s) : '…'}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function Recent() {
  const recent = useRecentSearches()
  const queries = [...new Set((recent.data ?? []).map((s) => s.query).filter(Boolean) as string[])].slice(0, 5)
  if (!queries.length) return null
  return (
    <section aria-labelledby="recent" className="rounded-lg border border-line p-5">
      <h2 id="recent" className="font-semibold tracking-tight">Recent searches</h2>
      <ul className="mt-3 flex flex-wrap gap-1.5">
        {queries.map((q) => (
          <li key={q}><Button asChild variant="outline" size="xs"><Link to={`/app/search?q=${encodeURIComponent(q)}`}>{q}</Link></Button></li>
        ))}
      </ul>
    </section>
  )
}

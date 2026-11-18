import { Search as SearchIcon } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { useSearchParams } from 'react-router'

import { Notice, PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useRecentSearches, useSearch } from '@/features/jobs/api'
import { JobRow, ListSkeleton } from '@/features/jobs/components'
import { ApiError } from '@/lib/api'
import { JOB_TYPE, WORK_MODE } from '@/lib/format'
import type { EmploymentType, JobFilters, LocationType } from '@/lib/types'

const ANY = 'any'

/** Search state lives in the URL, so back/forward and shared links reproduce the same results. */
function readParams(p: URLSearchParams): { q: string; filters: JobFilters; useProfile: boolean } {
  const lpa = Number(p.get('min_lpa'))
  return {
    q: p.get('q') ?? '',
    useProfile: p.get('profile') === '1',
    filters: {
      ...(p.get('city') ? { city: p.get('city')! } : {}),
      ...(p.get('mode') ? { location_type: p.get('mode') as LocationType } : {}),
      ...(p.get('type') ? { employment_type: p.get('type') as EmploymentType } : {}),
      ...(lpa > 0 ? { min_salary: Math.round(lpa * 100_000) } : {}),
    },
  }
}

export default function Search() {
  const [params, setParams] = useSearchParams()
  const { q, filters, useProfile } = readParams(params)
  const [draft, setDraft] = useState({
    q, city: params.get('city') ?? '', mode: params.get('mode') ?? ANY, type: params.get('type') ?? ANY,
    minLpa: params.get('min_lpa') ?? '', profile: useProfile,
  })
  const search = useSearch(q, filters, useProfile)
  const recent = useRecentSearches()

  const submit = (e?: FormEvent) => {
    e?.preventDefault()
    const next = new URLSearchParams()
    if (draft.q.trim()) next.set('q', draft.q.trim())
    if (draft.city.trim()) next.set('city', draft.city.trim())
    if (draft.mode !== ANY) next.set('mode', draft.mode)
    if (draft.type !== ANY) next.set('type', draft.type)
    if (Number(draft.minLpa) > 0) next.set('min_lpa', draft.minLpa)
    if (draft.profile) next.set('profile', '1')
    setParams(next)
  }

  const results = search.data?.results ?? []
  const profileError = search.error instanceof ApiError && search.error.code === 'empty_search'

  return (
    <div className="max-w-4xl">
      <PageHeader title="Search">
        Search by keywords or by what the role involves. Results are ranked on your skills, experience,
        salary and location, and each one says why.
      </PageHeader>

      <form onSubmit={submit} role="search" className="rounded-lg border border-line bg-card p-4">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <SearchIcon aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input aria-label="Search jobs" placeholder="e.g. backend engineer, python, payments" className="h-10 pl-9"
              value={draft.q} onChange={(e) => setDraft({ ...draft, q: e.target.value })} />
          </div>
          <Button type="submit" size="lg" className="h-10 px-5" disabled={!draft.q.trim()}>Search</Button>
        </div>
        <div className="mt-4 grid items-start gap-4 sm:grid-cols-2 lg:grid-cols-[1fr_9rem_9rem_8rem_auto]">
          <div className="space-y-1.5">
            <Label htmlFor="city">City</Label>
            <Input id="city" placeholder="Any city" value={draft.city} onChange={(e) => setDraft({ ...draft, city: e.target.value })} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="mode">Work mode</Label>
            <Select value={draft.mode} onValueChange={(v) => setDraft({ ...draft, mode: v })}>
              <SelectTrigger id="mode" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ANY}>Any</SelectItem>
                {Object.entries(WORK_MODE).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="type">Job type</Label>
            <Select value={draft.type} onValueChange={(v) => setDraft({ ...draft, type: v })}>
              <SelectTrigger id="type" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ANY}>Any</SelectItem>
                {Object.entries(JOB_TYPE).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="min">Min salary (LPA)</Label>
            <Input id="min" type="number" inputMode="decimal" min={0} step={0.5} placeholder="Any" className="tnum"
              value={draft.minLpa} onChange={(e) => setDraft({ ...draft, minLpa: e.target.value })} />
          </div>
          <div className="flex h-9 items-center gap-2 sm:mt-[1.375rem]">
            <Switch id="profile" checked={draft.profile} onCheckedChange={(v) => setDraft({ ...draft, profile: v })} />
            <Label htmlFor="profile" className="font-normal">Blend in my profile</Label>
          </div>
        </div>
      </form>

      <div className="mt-8" aria-live="polite">
        {!q ? (
          <RecentSearches items={recent.data ?? []} onPick={(text) => { setDraft({ ...draft, q: text }); setParams({ q: text }) }} />
        ) : search.isPending ? (
          <ListSkeleton />
        ) : profileError ? (
          <Notice title="Your profile is empty" tone="error">
            “Blend in my profile” needs skills or a summary on your profile. Turn it off, or add your résumé first.
          </Notice>
        ) : search.isError ? (
          <Notice title="Search failed" tone="error" action={<Button variant="outline" onClick={() => search.refetch()}>Try again</Button>}>
            {search.error.message}
          </Notice>
        ) : results.length === 0 ? (
          <Notice title={`No open roles match “${q}”`}>
            Try fewer words, or remove a filter. Searching is by meaning as well as keywords, so a description of the work also works.
          </Notice>
        ) : (
          <>
            <p className="mb-3 text-small text-muted-foreground">
              <span className="tnum">{results.length}</span> best matches for “{q}”
              {search.isFetching && ' (updating…)'}
            </p>
            <ol className="divide-y divide-line overflow-hidden rounded-lg border border-line">
              {results.map((hit, i) => (
                <JobRow key={hit.job_id} hit={hit} rank={i + 1} ctx={{ searchLogId: search.data!.search_log_id, position: i + 1 }} />
              ))}
            </ol>
          </>
        )}
      </div>
    </div>
  )
}

function RecentSearches({ items, onPick }: { items: { id: string; query: string | null }[]; onPick: (q: string) => void }) {
  const queries = [...new Set(items.map((s) => s.query).filter(Boolean) as string[])]
  if (!queries.length) {
    return <Notice title="Start with a role or a skill">Type what you’re looking for. Filters are optional.</Notice>
  }
  return (
    <section aria-labelledby="recent">
      <h2 id="recent" className="text-small text-muted-foreground">Your recent searches</h2>
      <ul className="mt-3 flex flex-wrap gap-2">
        {queries.map((q) => (
          <li key={q}>
            <Button variant="outline" size="sm" onClick={() => onPick(q)}>{q}</Button>
          </li>
        ))}
      </ul>
    </section>
  )
}

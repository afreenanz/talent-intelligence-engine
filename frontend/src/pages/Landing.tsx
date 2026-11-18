import { useQuery } from '@tanstack/react-query'
import { useCallback, useState } from 'react'
import { Link } from 'react-router'

import { Mark } from '@/components/brand/Mark'
import { BorderBeam } from '@/components/brand/BorderBeam'
import { TerrainField } from '@/components/brand/TerrainField'
import { type PublicStats, api } from '@/lib/api'

const nf = new Intl.NumberFormat('en-IN')

/** Real platform counts for the hero readout (public, aggregate-only endpoint). */
function useReadout() {
  const { data, isError } = useQuery({
    queryKey: ['public-stats'],
    queryFn: () => api<PublicStats>('/stats', { auth: false }),
    staleTime: 60_000,
  })
  const [points, setPoints] = useState<number | null>(null)
  const onPoints = useCallback((n: number) => setPoints(n), [])
  const value = (n: number | undefined) => (n === undefined ? (isError ? 'n/a' : '…') : nf.format(n))
  return { onPoints, panel: (
    <BorderBeam radius={20} className="live-card w-[17rem] max-w-full">
      <section aria-labelledby="live-index" className="p-4 text-small">
        <div className="mb-3 flex items-center justify-between">
          <h2 id="live-index" className="text-micro text-muted-foreground">Live index</h2>
          <span className="rounded-full border border-signal/25 bg-signal/10 px-2 py-px text-[10px] font-semibold uppercase tracking-[0.08em] text-signal">
            Live
          </span>
        </div>
        <dl className="grid grid-cols-[1fr_auto] gap-x-6 gap-y-2 [font-variant-numeric:proportional-nums]">
          <dt className="text-muted-foreground">Open roles</dt><dd className="text-right">{value(data?.active_jobs)}</dd>
          <dt className="text-muted-foreground">Companies hiring</dt><dd className="text-right">{value(data?.companies_hiring)}</dd>
          <dt className="text-muted-foreground">Skills tracked</dt><dd className="text-right">{value(data?.skills_tracked)}</dd>
          <dt className="text-muted-foreground">Points in view</dt><dd className="text-right">{points === null ? '…' : nf.format(points)}</dd>
        </dl>
      </section>
    </BorderBeam>
  ) }
}

const STEPS = [
  { title: 'Add your résumé', body: 'We read the PDF, keep only skills that are actually written in it, and work out your experience from your job dates. You check everything before it’s saved.' },
  { title: 'Get ranked matches', body: 'Every open role is scored on skills, experience, salary and location. Each match says why it ranks where it does, and what you’re missing.' },
  { title: 'Ask the assistant', body: 'Search, compare and save jobs in plain language. It asks before it saves anything or changes your preferences.' },
]

export default function Landing() {
  const { onPoints, panel } = useReadout()
  return (
    <div className="dark bg-background text-foreground">
      <section className="relative h-[100svh] min-h-[620px] overflow-hidden bg-[radial-gradient(120%_80%_at_70%_20%,#10131c_0%,#07080c_60%)]">
        {/* Dimmed so the field reads as atmosphere, not as the subject. */}
        <div className="absolute inset-0 opacity-55">
          <TerrainField onPointsInView={onPoints} />
        </div>
        {/* Veil: opaque at the bottom-left corner, clear by three quarters out, so no dot fights the copy. */}
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(130%_110%_at_0%_100%,#07080c_0%,rgb(7_8_12/0.94)_38%,rgb(7_8_12/0.5)_62%,transparent_85%)]" />
        {/* On narrow screens the copy spans the full width, so the veil rises from the bottom edge instead. */}
        <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 bottom-0 h-[78%] bg-[linear-gradient(to_top,#07080c_0%,rgb(7_8_12/0.9)_55%,transparent_100%)] sm:hidden" />
        <div aria-hidden="true" className="grain pointer-events-none absolute inset-0" />

        <header className="hero-nav relative z-10 flex items-center justify-between px-5 py-5 sm:px-8">
          <Link to="/" className="flex items-center gap-2.5 font-semibold tracking-tight">
            <Mark className="size-5 text-foreground" />
            <span className="whitespace-nowrap max-[400px]:sr-only">Talent Intelligence Engine</span>
          </Link>
          <nav aria-label="Main" className="flex items-center gap-6 text-small">
            <a href="#how" className="hidden text-muted-foreground hover:text-foreground sm:inline">How it works</a>
            <Link to="/login" className="whitespace-nowrap text-muted-foreground hover:text-foreground">Sign in</Link>
            <Link to="/register" className="hidden whitespace-nowrap rounded-full sm:inline-flex bg-primary px-4 py-2 font-semibold text-primary-foreground hover:bg-white">
              Create your profile
            </Link>
          </nav>
        </header>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex flex-col gap-8 px-5 pb-8 sm:px-8 lg:flex-row lg:items-end lg:justify-between">
          <div className="hero-copy pointer-events-auto max-w-[58rem]">
            <h1 className="hero-title font-[700] leading-[0.9] tracking-[-0.055em] [font-size:clamp(48px,8vw,132px)] [filter:drop-shadow(0_0_16px_rgb(238_232_220/0.32))_drop-shadow(0_0_48px_rgb(255_138_61/0.22))]">
              {'See where you stand in the job market.'.split(' ').map((w, i) => (
                <span key={i} className="-mb-[0.16em] inline-block overflow-hidden pb-[0.22em] align-bottom">
                  <span className="hero-word inline-block" style={{ animationDelay: `${120 + i * 60}ms` }}>{w}&nbsp;</span>
                </span>
              ))}
            </h1>
            <Link to="/register" className="mt-9 inline-flex rounded-full bg-primary px-5 py-2.5 font-semibold text-primary-foreground hover:bg-white">
              Create your profile
            </Link>
          </div>
          <div className="pointer-events-auto">{panel}</div>
        </div>
      </section>

      <section id="how" className="mx-auto max-w-6xl px-5 py-24 sm:px-8">
        <h2 className="max-w-[24ch] text-h1 font-semibold leading-tight tracking-[-0.03em]">
          Three steps from a PDF to a shortlist you can trust.
        </h2>
        <ol className="mt-12 grid gap-px overflow-hidden rounded-lg border border-line bg-line md:grid-cols-3">
          {STEPS.map((s, i) => (
            <li key={s.title} className="bg-background p-6">
              <span className="tnum text-small text-signal">{i + 1}</span>
              <h3 className="mt-3 text-h3 font-semibold tracking-tight">{s.title}</h3>
              <p className="mt-2 max-w-[38ch] text-muted-foreground">{s.body}</p>
            </li>
          ))}
        </ol>
        <p className="mt-10 max-w-[60ch] text-small text-muted-foreground">
          The job listings in this demo are synthetic and labelled as such. Ranking quality is measured on
          a public benchmark with human relevance labels. The numbers are on the evaluation page.
        </p>
      </section>
    </div>
  )
}

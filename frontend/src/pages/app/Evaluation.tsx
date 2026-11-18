import { Play } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { toast } from 'sonner'

import { Notice, PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAuth } from '@/features/auth/context'
import { useEvaluationRuns, useRunRetrievalEval } from '@/features/evaluation/api'
import { configName, latestBatch, num } from '@/features/evaluation/batches'
import type { EvaluationRun } from '@/lib/types'
import { cn } from '@/lib/utils'

interface Col { key: string; label: string; lowerIsBetter?: boolean; noBest?: boolean; fmt?: (n: number) => string }
const f3 = (n: number) => n.toFixed(3)
const ms = (n: number) => `${n.toFixed(n < 100 ? 1 : 0)} ms`

export default function Evaluation() {
  const { account } = useAuth()
  const runs = useEvaluationRuns()
  const header = (
    <PageHeader title="Evaluation">
      Measured results for each part of the system, from the latest recorded runs. Every number links back to a
      stored run with its dataset, split and code version.
    </PageHeader>
  )
  if (!account?.is_admin) return <div className="max-w-5xl">{header}<Notice title="Admins only">Ask an admin to grant you access with the make-admin command.</Notice></div>
  if (runs.isPending) return <div className="max-w-5xl">{header}<p className="text-muted-foreground">Loading runs…</p></div>
  if (runs.isError) return <div className="max-w-5xl">{header}<Notice tone="error" title="Couldn’t load runs">{runs.error.message}</Notice></div>

  const all = runs.data
  return (
    <div className="max-w-5xl space-y-14">
      {header}
      <Ranking runs={latestBatch(all, 'ranking_comparison')} />
      <Retrieval all={all} />
      <Personalization runs={latestBatch(all, 'personalization_personas')} />
      <Assistant run={latestBatch(all, 'agent_benchmark')[0]} total={all.filter((r) => r.experiment_name === 'agent_benchmark').length} />
      <Extraction run={latestBatch(all, 'resume_extraction')[0]} />
      <Performance run={latestBatch(all, 'performance')[0]} />
    </div>
  )
}

function Section({ title, about, runs, children, actions }: {
  title: string; about: ReactNode; runs: EvaluationRun[]; children: ReactNode; actions?: ReactNode
}) {
  const r = runs[0]
  return (
    <section aria-labelledby={title}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 id={title} className="text-h2 font-semibold tracking-[-0.02em]">{title}</h2>
        {actions}
      </div>
      <p className="mt-2 max-w-[70ch] text-muted-foreground">{about}</p>
      {r ? (
        <>
          <div className="mt-5">{children}</div>
          <p className="mt-3 text-micro text-muted-foreground">
            Dataset {r.dataset_version}, split {r.split}, recorded {new Date(r.created_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}
            {r.git_commit && <>, commit <code className="font-mono">{r.git_commit.slice(0, 7)}</code></>}
          </p>
        </>
      ) : <p className="mt-4 text-small text-muted-foreground">No runs recorded yet.</p>}
    </section>
  )
}

/** Configurations as rows, metrics as columns; the best value in each column is bold. */
function MetricTable({ rows, cols, mark }: { rows: { name: string; values: Record<string, unknown> }[]; cols: Col[]; mark?: string }) {
  const best = Object.fromEntries(cols.map((c) => {
    const vals = rows.map((r) => num(r.values[c.key])).filter((v): v is number => v !== null)
    // No "best" for counts, or when every row ties (bolding all of them says nothing).
    if (c.noBest || vals.length < 2 || vals.every((v) => v === vals[0])) return [c.key, null]
    return [c.key, c.lowerIsBetter ? Math.min(...vals) : Math.max(...vals)]
  }))
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full text-small">
        <thead>
          <tr className="border-b border-line text-left text-muted-foreground">
            <th scope="col" className="px-4 py-2.5 font-normal">Configuration</th>
            {cols.map((c) => <th key={c.key} scope="col" className="px-4 py-2.5 text-right font-normal">{c.label}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) => (
            <tr key={r.name} className={cn(r.name === mark && 'bg-signal/5')}>
              <th scope="row" className="px-4 py-2.5 text-left font-normal [font-variant-numeric:normal]">
                {r.name}{r.name === mark && <span className="ml-2 text-micro text-signal">used in the app</span>}
              </th>
              {cols.map((c) => {
                const v = num(r.values[c.key])
                return (
                  <td key={c.key} className={cn('px-4 py-2.5 text-right', v !== null && v === best[c.key] && 'font-semibold')}>
                    {v === null ? '–' : (c.fmt ?? f3)(v)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const mean = (r: EvaluationRun) => (r.metrics.mean ?? {}) as Record<string, unknown>

function Ranking({ runs }: { runs: EvaluationRun[] }) {
  const base = runs.find((r) => configName(r) === 'hybrid (RRF k=60)')
  const full = runs.find((r) => configName(r) === 'hybrid + features + cross-encoder')
  const gain = base && full ? num(mean(full)['map@100'])! - num(mean(base)['map@100'])! : null
  return (
    <Section title="Ranking quality" runs={runs} about={<>
      TalentCLEF 2026 job-matching benchmark: real job titles with human relevance labels (CC BY 4.0).
      {gain !== null && <> Adding ranking features and the cross-encoder to hybrid retrieval changes MAP@100 by <strong className="tnum">{gain >= 0 ? '+' : ''}{gain.toFixed(3)}</strong>.</>}
      {' '}{runs[0] ? `${String(runs[0].metrics.n_queries ?? '')} queries, so treat small differences with care.` : ''}
    </>}>
      <MetricTable mark="hybrid + features (weighted_v1)"
        rows={runs.map((r) => ({ name: configName(r), values: mean(r) }))}
        cols={[{ key: 'map@100', label: 'MAP@100' }, { key: 'ndcg@10', label: 'NDCG@10' }, { key: 'p@10', label: 'P@10' }, { key: 'mrr@10', label: 'MRR@10' }, { key: 'recall@100', label: 'Recall@100' }]} />
    </Section>
  )
}

function Retrieval({ all }: { all: EvaluationRun[] }) {
  const [split, setSplit] = useState<'dev' | 'test'>('test')
  const run = useRunRetrievalEval()
  const runs = latestBatch(all, 'retrieval_comparison', split)
  return (
    <Section title="Retrieval" runs={runs}
      about="How well each retrieval method finds relevant jobs, on the synthetic job set with generated (silver) labels. Useful for comparing methods with each other, not as an absolute score. Settings were tuned on dev; test is the honest check."
      actions={
        <div className="flex items-center gap-2">
          <Tabs value={split} onValueChange={(v) => setSplit(v as 'dev' | 'test')}>
            <TabsList><TabsTrigger value="dev">Dev</TabsTrigger><TabsTrigger value="test">Test</TabsTrigger></TabsList>
          </Tabs>
          <Button size="sm" variant="outline" disabled={run.isPending || run.isSuccess}
            onClick={() => run.mutate(split, {
              onSuccess: () => toast(`Retrieval evaluation started on ${split}. Results appear here in about a minute.`),
              onError: (e) => toast.error(e.message),
            })}>
            <Play aria-hidden="true" /> {run.isSuccess ? 'Running…' : `Run on ${split}`}
          </Button>
        </div>
      }>
      <MetricTable rows={runs.map((r) => ({ name: configName(r), values: mean(r) }))}
        cols={[{ key: 'ndcg@10', label: 'NDCG@10' }, { key: 'p@10', label: 'P@10' }, { key: 'mrr@10', label: 'MRR@10' }, { key: 'recall@100', label: 'Recall@100' }]} />
    </Section>
  )
}

function Personalization({ runs }: { runs: EvaluationRun[] }) {
  return (
    <Section title="Personalisation" runs={runs}
      about="Simulated users with fixed tastes click through four rounds of recommendations. Measures whether learning from clicks surfaces roles they like on fresh results. Simulated, so it shows the mechanism works, not how real people behave.">
      <MetricTable rows={runs.map((r) => ({ name: configName(r), values: r.metrics }))}
        cols={[{ key: 'ndcg@10_fresh', label: 'NDCG@10 (fresh)' }, { key: 'liked_share@10', label: 'Liked in top 10' }, { key: 'disliked_share@10', label: 'Disliked in top 10', lowerIsBetter: true }]} />
    </Section>
  )
}

function Summary({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
      {items.map(([label, value]) => (
        <div key={label} className="bg-background px-4 py-3">
          <dt className="text-small text-muted-foreground">{label}</dt>
          <dd className="tnum mt-0.5 text-lede font-semibold">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

const pct = (v: unknown) => (num(v) === null ? '–' : `${Math.round(num(v)! * 1000) / 10}%`)
const raw = (v: unknown) => (v == null ? '–' : String(v))

function Assistant({ run, total }: { run?: EvaluationRun; total: number }) {
  const s = (run?.metrics.summary ?? {}) as Record<string, unknown>
  return (
    <Section title="Assistant" runs={run ? [run] : []}
      about={<>Scripted conversations ({raw(s.cases)} cases) checked automatically: the right tools, valid arguments, no unconfirmed changes, and every fact in the reply traceable to tool output. {total > 1 && `${total} runs recorded; the latest is shown.`}</>}>
      <Summary items={[
        ['Task completion', pct(s.task_completion)],
        ['Right tool chosen', pct(s.tool_selection_accuracy)],
        ['Grounded replies', pct(s.groundedness)],
        ['Facts checked against data', raw(s.factual_consistency)],
        ['Changes made without asking', pct(s.forbidden_tool_violation_rate)],
        ['Unrequested filters added', raw(s.cases_with_unrequested_filters)],
        ['Latency (median)', num(s.latency_ms_p50) === null ? '–' : ms(num(s.latency_ms_p50)!)],
        ['Tool calls that succeeded', pct(s.tool_success_rate)],
        ['Cost per run (paid tier)', num(s.estimated_cost_usd_paid_tier) === null ? '–' : `$${num(s.estimated_cost_usd_paid_tier)!.toFixed(4)}`],
      ]} />
    </Section>
  )
}

function Extraction({ run }: { run?: EvaluationRun }) {
  const s = (run?.metrics.summary ?? {}) as Record<string, unknown>
  return (
    <Section title="Résumé extraction" runs={run ? [run] : []}
      about={<>{raw(s.resumes)} fictional résumés with known answers, including a planted prompt injection. The current fixes were designed after seeing the first run, so these scores are optimistic until checked on new résumés.</>}>
      <Summary items={[
        ['Skill precision', pct(s.skills_precision_after_checks)],
        ['Skill recall', pct(s.skills_recall_after_checks)],
        ['Injected skills accepted', raw(s.forbidden_skills_final)],
        ['Names correct', pct(s.name_accuracy)],
        ['Experience in range', pct(s.experience_in_range)],
        ['Latency (median)', num(s.latency_ms_median) === null ? '–' : ms(num(s.latency_ms_median)!)],
      ]} />
    </Section>
  )
}

function Performance({ run }: { run?: EvaluationRun }) {
  const m = (run?.metrics ?? {}) as Record<string, Record<string, unknown>>
  const LABEL: Record<string, string> = {
    post_jobs_search_features: 'Search request, end to end (HTTP)', stage1_features_100_jobs: 'Rank 100 jobs (features)',
    stage1_plus_cross_encoder_top50: 'Rank + cross-encoder on top 50', query_encode: 'Encode the query',
    lexical: 'Keyword retrieval', dense: 'Vector retrieval', hybrid: 'Hybrid retrieval',
  }
  const rows = ['http', 'retrieval', 'ranking', 'embedding'].flatMap((g) =>
    Object.entries(m[g] ?? {}).filter(([, v]) => typeof v === 'object' && v !== null && 'p50_ms' in v)
      .map(([k, v]) => ({ name: LABEL[k] ?? k, values: v as Record<string, unknown> })))
  return (
    <Section title="Speed" runs={run ? [run] : []}
      about={<>Latency on a laptop CPU over {raw(m.corpus_active_jobs as unknown)} active jobs. The cross-encoder is accurate but slow, which is why it is opt-in.</>}>
      <MetricTable rows={rows}
        cols={[{ key: 'p50_ms', label: 'Median', lowerIsBetter: true, fmt: ms }, { key: 'p95_ms', label: '95th percentile', lowerIsBetter: true, fmt: ms }, { key: 'n', label: 'Samples', noBest: true, fmt: (n) => String(n) }]} />
    </Section>
  )
}

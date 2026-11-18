import { Check, ShieldAlert, X } from 'lucide-react'

import { useJob } from '@/features/jobs/api'
import { PREFERENCE_LABEL, describePreference } from '@/lib/preferences'
import type { PendingAction, PreferenceKey, ToolCallTrace } from '@/lib/types'

const STEP: Record<string, string> = {
  search_jobs: 'Searched jobs',
  get_job_details: 'Read a job',
  rank_jobs: 'Ranked jobs',
  analyze_candidate_profile: 'Read your profile',
  explain_job_match: 'Explained a match',
  save_job: 'Saved a job',
  get_saved_jobs: 'Read your saved jobs',
  update_candidate_preferences: 'Changed a preference',
  get_candidate_preferences: 'Read your preferences',
  get_application_status: 'Read your applications',
}

/** What the assistant did to produce an answer: every tool call, in order, with its outcome. */
export function Steps({ calls }: { calls: ToolCallTrace[] | undefined }) {
  if (!calls?.length) return null
  return (
    <details className="group mt-3 text-small text-muted-foreground">
      <summary className="cursor-pointer select-none list-none hover:text-foreground">
        <span className="tnum">{calls.length}</span> {calls.length === 1 ? 'step' : 'steps'}
        <span className="ml-1 inline-block transition-transform group-open:rotate-90" aria-hidden="true">›</span>
      </summary>
      <ol className="mt-2 space-y-1 border-l border-line pl-3">
        {calls.map((c, i) => (
          <li key={i} className="flex items-start gap-2">
            {c.ok ? <Check aria-hidden="true" className="mt-0.5 size-3.5 text-sage" /> : <X aria-hidden="true" className="mt-0.5 size-3.5 text-rose" />}
            <span>
              {STEP[c.tool] ?? c.tool}
              {c.tool === 'search_jobs' && typeof c.arguments.query === 'string' && <>: “{c.arguments.query}”{c.arguments.city ? ` in ${String(c.arguments.city)}` : ''}</>}
              {!c.ok && <span className="text-rose"> (failed{c.error_code ? `: ${c.error_code}` : ''})</span>}
              {c.confirmed === false && ' (you declined)'}
              <span className="sr-only">{c.ok ? ' succeeded' : ' failed'}</span>
            </span>
          </li>
        ))}
      </ol>
    </details>
  )
}

function SaveJobText({ jobId }: { jobId: string }) {
  const { data } = useJob(jobId)
  return <>Save <strong className="font-semibold">{data ? `${data.title} at ${data.company}` : 'this job'}</strong> to your saved jobs</>
}

/** A pending action in plain words: job titles instead of ids, preference values described. */
export function ActionText({ action }: { action: PendingAction }) {
  const a = action.arguments
  if (action.tool === 'save_job' && typeof a.job_id === 'string') return <SaveJobText jobId={a.job_id} />
  if (action.tool === 'update_candidate_preferences' && typeof a.key === 'string') {
    const key = a.key as PreferenceKey
    if (a.value == null) return <>Remove your {PREFERENCE_LABEL[key] ?? key} preference</>
    return <>Set your {PREFERENCE_LABEL[key] ?? key} to <strong className="font-semibold">{describePreference(key, a.value as Record<string, unknown>)}</strong></>
  }
  return <>{action.summary}</>
}

export function Ungrounded({ issues }: { issues?: string[] }) {
  return (
    <p className="mt-3 flex gap-2 rounded-md border border-rose/30 px-3 py-2 text-small text-rose">
      <ShieldAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      <span>
        Some details in this answer couldn’t be checked against the job data. Open the job before relying on them.
        {issues?.length ? <span className="sr-only"> Issues: {issues.join('; ')}</span> : null}
      </span>
    </p>
  )
}

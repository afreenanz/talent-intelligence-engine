import { type ReactNode, useState } from 'react'
import { toast } from 'sonner'

import { Notice, PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { usePreferences, useSetPreference } from '@/features/jobs/api'
import { ListSkeleton } from '@/features/jobs/components'
import { JOB_TYPE, WORK_MODE } from '@/lib/format'
import type { Preference, PreferenceKey } from '@/lib/types'
import { cn } from '@/lib/utils'

const ROLES: Record<string, string> = {
  backend: 'Backend', frontend: 'Frontend', fullstack: 'Full-stack', data: 'Data', ml: 'Machine learning',
  devops: 'DevOps', mobile: 'Mobile', qa: 'QA and testing', security: 'Security', design: 'Design', product: 'Product',
}

type Value = Record<string, unknown>
const list = (v: unknown) => (Array.isArray(v) ? (v as string[]) : [])
const csv = (s: string) => [...new Set(s.split(',').map((x) => x.trim()).filter(Boolean))]

/** How each stored value reads in plain words. */
function describe(key: PreferenceKey, v: Value): string {
  switch (key) {
    case 'role_categories': {
      const p = list(v.prefer).map((r) => ROLES[r] ?? r)
      const a = list(v.avoid).map((r) => ROLES[r] ?? r)
      return [p.length && `Prefer ${p.join(', ')}`, a.length && `avoid ${a.join(', ')}`].filter(Boolean).join('; ')
    }
    case 'locations': return list(v.cities).join(', ')
    case 'location_type': return WORK_MODE[v.value as keyof typeof WORK_MODE] ?? String(v.value)
    case 'employment_type': return JOB_TYPE[v.value as keyof typeof JOB_TYPE] ?? String(v.value)
    case 'min_salary': return v.currency === 'INR' || !v.currency ? `${Number(v.amount) / 100_000} LPA` : `${v.amount} ${v.currency}`
    case 'company_avoid': return list(v.companies).join(', ')
    case 'skills_to_use': return list(v.skills).join(', ')
  }
}

export default function Preferences() {
  const prefs = usePreferences()
  const header = (
    <PageHeader title="Preferences">
      What you set here ranks higher than anything learned from your activity. You can change or remove any of it.
    </PageHeader>
  )
  if (prefs.isPending) return <div className="max-w-3xl">{header}<ListSkeleton rows={4} /></div>
  if (prefs.isError) {
    return <div className="max-w-3xl">{header}<Notice tone="error" title="Couldn’t load preferences">{prefs.error.message}</Notice></div>
  }
  const find = (key: PreferenceKey, type: Preference['memory_type']) =>
    prefs.data.find((p) => p.key === key && p.memory_type === type)
  const row = (key: PreferenceKey, title: string, about: string, editor: (v: Value | undefined) => EditorSpec) => (
    <PreferenceRow key={key} prefKey={key} title={title} about={about}
      explicit={find(key, 'explicit_preference')} derived={find(key, 'derived_preference')} editor={editor} />
  )

  return (
    <div className="max-w-3xl">
      {header}
      <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line">
        {row('role_categories', 'Kinds of roles', 'Click once to prefer, twice to avoid, again to clear.', (v) => roleEditor(v))}
        {row('locations', 'Cities', 'Comma-separated, e.g. Bengaluru, Pune.', (v) => textEditor(v, 'cities', 'Bengaluru, Pune'))}
        {row('location_type', 'Work mode', 'Remote, hybrid or on-site.', (v) => selectEditor(v, WORK_MODE))}
        {row('employment_type', 'Job type', 'Full-time, contract, internship…', (v) => selectEditor(v, JOB_TYPE))}
        {row('min_salary', 'Minimum salary', 'Annual, in lakhs (LPA).', (v) => salaryEditor(v))}
        {row('skills_to_use', 'Skills you want to use', 'Roles that use these rank higher.', (v) => textEditor(v, 'skills', 'Go, Kubernetes'))}
        {row('company_avoid', 'Companies to avoid', 'These never appear in your matches.', (v) => textEditor(v, 'companies', 'Company names'))}
      </ul>
    </div>
  )
}

/** An editor: renders the input, and turns its state into an API value (or null when invalid/empty). */
interface EditorSpec {
  render: (state: string, set: (s: string) => void) => ReactNode
  initial: string
  toValue: (state: string) => Value | null
}

function PreferenceRow({ prefKey, title, about, explicit, derived, editor }: {
  prefKey: PreferenceKey
  title: string
  about: string
  explicit?: Preference
  derived?: Preference
  editor: (v: Value | undefined) => EditorSpec
}) {
  const [editing, setEditing] = useState(false)
  const spec = editor(explicit?.value)
  const [state, setState] = useState(spec.initial)
  const save = useSetPreference()
  const value = spec.toValue(state)

  const commit = (v: Value | null) =>
    save.mutate({ key: prefKey, value: v }, {
      onSuccess: () => { setEditing(false); toast(v ? `${title} saved` : `${title} removed`) },
      onError: (e) => toast.error(e.message),
    })

  return (
    <li className="px-5 py-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-semibold tracking-tight">{title}</h2>
          {explicit ? (
            <p className="mt-1">{describe(prefKey, explicit.value)}</p>
          ) : (
            <p className="mt-1 text-muted-foreground">Not set</p>
          )}
          {derived && (
            <p className={cn('mt-1 text-small text-muted-foreground', explicit && 'line-through decoration-muted-foreground/50')}>
              Learned from your activity: {describe(prefKey, derived.value)}
              <span className="tnum"> (confidence {Math.round(derived.confidence * 100)}%)</span>
              {explicit && <span className="sr-only"> (overridden by your setting)</span>}
            </p>
          )}
        </div>
        {!editing && (
          <div className="flex gap-1">
            <Button variant="outline" size="sm" onClick={() => { setState(spec.initial); setEditing(true) }}>
              {explicit ? 'Change' : 'Set'}
            </Button>
            {explicit && <Button variant="ghost" size="sm" disabled={save.isPending} onClick={() => commit(null)}>Remove</Button>}
          </div>
        )}
      </div>
      {editing && (
        <form className="mt-4 space-y-3" onSubmit={(e) => { e.preventDefault(); if (value) commit(value) }}>
          <p className="text-small text-muted-foreground">{about}</p>
          {spec.render(state, setState)}
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={!value || save.isPending}>{save.isPending ? 'Saving…' : 'Save'}</Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
          </div>
        </form>
      )}
    </li>
  )
}

function textEditor(v: Value | undefined, field: string, placeholder: string): EditorSpec {
  return {
    initial: list(v?.[field]).join(', '),
    toValue: (s) => (csv(s).length ? { [field]: csv(s) } : null),
    render: (s, set) => <Input aria-label={field} placeholder={placeholder} value={s} onChange={(e) => set(e.target.value)} />,
  }
}

function selectEditor(v: Value | undefined, options: Record<string, string>): EditorSpec {
  return {
    initial: (v?.value as string | undefined) ?? '',
    toValue: (s) => (s ? { value: s } : null),
    render: (s, set) => (
      <Select value={s || undefined} onValueChange={set}>
        <SelectTrigger aria-label="Choose one" className="w-56"><SelectValue placeholder="Choose one" /></SelectTrigger>
        <SelectContent>{Object.entries(options).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
      </Select>
    ),
  }
}

function salaryEditor(v: Value | undefined): EditorSpec {
  return {
    initial: v?.amount ? String(Number(v.amount) / 100_000) : '',
    toValue: (s) => (Number(s) > 0 ? { amount: Math.round(Number(s) * 100_000), currency: 'INR' } : null),
    render: (s, set) => (
      <div className="flex items-center gap-2">
        <Input aria-label="Minimum salary in LPA" type="number" inputMode="decimal" min={0} step={0.5}
          className="tnum w-32" value={s} onChange={(e) => set(e.target.value)} />
        <span className="text-small text-muted-foreground">LPA</span>
      </div>
    ),
  }
}

/** State is "prefer:a,b|avoid:c" so the generic row can hold it as a string. */
function roleEditor(v: Value | undefined): EditorSpec {
  const encode = (p: string[], a: string[]) => `${p.join(',')}|${a.join(',')}`
  const decode = (s: string) => {
    const [p = '', a = ''] = s.split('|')
    return { prefer: p.split(',').filter(Boolean), avoid: a.split(',').filter(Boolean) }
  }
  return {
    initial: encode(list(v?.prefer), list(v?.avoid)),
    toValue: (s) => {
      const d = decode(s)
      return d.prefer.length || d.avoid.length ? d : null
    },
    render: (s, set) => {
      const { prefer, avoid } = decode(s)
      const cycle = (r: string) => {
        if (prefer.includes(r)) set(encode(prefer.filter((x) => x !== r), [...avoid, r]))
        else if (avoid.includes(r)) set(encode(prefer, avoid.filter((x) => x !== r)))
        else set(encode([...prefer, r], avoid))
      }
      return (
        <ul className="flex flex-wrap gap-1.5">
          {Object.entries(ROLES).map(([r, label]) => {
            const state = prefer.includes(r) ? 'prefer' : avoid.includes(r) ? 'avoid' : 'none'
            return (
              <li key={r}>
                <button type="button" onClick={() => cycle(r)}
                  aria-label={`${label}: ${state === 'none' ? 'no preference' : state}`}
                  className={cn('rounded-md border px-2.5 py-1 text-small transition-colors',
                    state === 'prefer' && 'border-sage/50 bg-sage/10 text-foreground',
                    state === 'avoid' && 'border-rose/50 bg-rose/10 text-rose line-through',
                    state === 'none' && 'border-line text-muted-foreground hover:text-foreground')}>
                  {label}
                </button>
              </li>
            )
          })}
        </ul>
      )
    },
  }
}

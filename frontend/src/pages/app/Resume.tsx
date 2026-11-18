import { FileUp, RotateCw, Trash2, TriangleAlert } from 'lucide-react'
import { type DragEvent, type FormEvent, useId, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Notice, PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  MAX_RESUME_BYTES, useApplyResume, useDeleteResume, useReprocessResume, useResumes, useUploadResume,
} from '@/features/resume/api'
import { ago } from '@/lib/format'
import type { ParsedResume, Resume as ResumeT } from '@/lib/types'
import { cn } from '@/lib/utils'

const STATUS: Record<ResumeT['parsing_status'], string> = {
  pending: 'Waiting', processing: 'Reading', parsed: 'Ready to review', failed: 'Couldn’t read', reviewed: 'Added to profile',
}

export default function Resume() {
  const resumes = useResumes()
  const latest = resumes.data?.[0]
  return (
    <div className="max-w-3xl">
      <PageHeader title="Résumé">
        Upload a PDF. We pull out your skills, experience and education, you check every field, and only then is it added to your profile.
      </PageHeader>

      {resumes.isPending ? <p className="text-muted-foreground">Loading…</p> : (
        <>
          {latest && <Current resume={latest} />}
          <div className={cn(latest && 'mt-10')}>
            {latest && <h2 className="mb-3 font-semibold tracking-tight">Upload a different résumé</h2>}
            <Dropzone />
          </div>
          {(resumes.data?.length ?? 0) > 1 && <History items={resumes.data!.slice(1)} />}
        </>
      )}
    </div>
  )
}

function Dropzone() {
  const upload = useUploadResume()
  const inputId = useId()
  const [over, setOver] = useState(false)

  const take = (file: File | undefined) => {
    if (!file) return
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      toast.error('That isn’t a PDF. Export your résumé as PDF and try again.')
      return
    }
    if (file.size > MAX_RESUME_BYTES) {
      toast.error(`That file is ${(file.size / 1_048_576).toFixed(1)} MB. The limit is 5 MB.`)
      return
    }
    upload.mutate(file, {
      onSuccess: () => toast('Uploaded. Reading your résumé…'),
      onError: (e) => toast.error(e.message),
    })
  }
  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files[0]) }

  return (
    <div>
      <label htmlFor={inputId}
        onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)} onDrop={onDrop}
        className={cn('flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed px-6 py-10 text-center transition-colors',
          over ? 'border-signal bg-signal/5' : 'border-line hover:border-foreground/25 hover:bg-muted/30',
          upload.isPending && 'pointer-events-none opacity-60')}>
        <FileUp aria-hidden="true" className="size-6 text-muted-foreground" />
        <span className="font-semibold">{upload.isPending ? 'Uploading…' : 'Choose a PDF or drop it here'}</span>
        <span className="text-small text-muted-foreground">Up to 5 MB and 10 pages</span>
        <input id={inputId} type="file" accept="application/pdf,.pdf" className="sr-only" disabled={upload.isPending}
          onChange={(e) => { take(e.target.files?.[0]); e.target.value = '' }} />
      </label>
      <p className="mt-3 text-micro text-muted-foreground">
        The text of your PDF is sent to Google Gemini (free tier), where Google may use it to improve its models.
        Upload only your own résumé. The file itself stays on this server, and you can delete it any time.
      </p>
    </div>
  )
}

function Current({ resume }: { resume: ResumeT }) {
  const reprocess = useReprocessResume()
  const { parsing_status: status } = resume
  if (status === 'pending' || status === 'processing') {
    return (
      <section aria-live="polite" className="rounded-lg border border-line bg-card p-6">
        <p className="font-semibold"><span className="animate-pulse">Reading {resume.original_filename}…</span></p>
        <p className="mt-1 text-small text-muted-foreground">This usually takes 5 to 15 seconds. You can leave this page; it carries on.</p>
      </section>
    )
  }
  if (status === 'failed') {
    return (
      <Notice tone="error" title={`Couldn’t read ${resume.original_filename}`}
        action={<Button variant="outline" disabled={reprocess.isPending} onClick={() => reprocess.mutate(resume.id)}>
          <RotateCw aria-hidden="true" /> Try again
        </Button>}>
        {resume.parsing_error ?? 'Something went wrong while reading the file.'} If it’s a scanned image, export a text PDF instead.
      </Notice>
    )
  }
  if (status === 'reviewed') {
    return (
      <Notice title="Your résumé is on your profile"
        action={<Button asChild><Link to="/app/recommendations">See your matches</Link></Button>}>
        {resume.original_filename}, added {resume.reviewed_at ? ago(resume.reviewed_at) : ''}. Your matches now use these skills.
      </Notice>
    )
  }
  return resume.parsed_data ? <Review resume={resume} data={resume.parsed_data} /> : null
}

/** Every extracted field is editable; dictionary-only skills start unticked because they may be false positives. */
function Review({ resume, data }: { resume: ResumeT; data: ParsedResume }) {
  const apply = useApplyResume()
  const [fields, setFields] = useState({
    full_name: data.full_name ?? '', location: data.location ?? '',
    experience_years: data.experience_years?.toString() ?? '', summary: data.summary ?? '',
  })
  const [skills, setSkills] = useState(() => new Map(data.skills.map((s) => [s.name, !s.suggested])))
  const [extra, setExtra] = useState('')
  const [withEducation, setWithEducation] = useState(data.education.length > 0)
  const [withProjects, setWithProjects] = useState(data.projects.length > 0)
  const confirmed = data.skills.filter((s) => !s.suggested)
  const suggested = data.skills.filter((s) => s.suggested)
  const chosen = [...skills].filter(([, on]) => on).map(([name]) => name)

  const addExtra = () => {
    const names = extra.split(',').map((x) => x.trim()).filter(Boolean)
    if (!names.length) return
    setSkills((m) => { const n = new Map(m); names.forEach((x) => n.set(x, true)); return n })
    setExtra('')
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const years = fields.experience_years.trim() === '' ? null : Number(fields.experience_years)
    apply.mutate({
      id: resume.id,
      body: {
        // Empty fields are left out, so they never erase what's already on your profile.
        ...(fields.full_name.trim() ? { full_name: fields.full_name.trim() } : {}),
        ...(fields.location.trim() ? { location: fields.location.trim() } : {}),
        ...(years !== null && years >= 0 ? { experience_years: years } : {}),
        ...(fields.summary.trim() ? { profile_summary: fields.summary.trim() } : {}),
        skills: chosen.map((name) => ({ name })),
        education: withEducation ? data.education : null,
        projects: withProjects ? data.projects : null,
      },
    }, {
      onSuccess: () => toast('Added to your profile'),
      onError: (err) => toast.error(err.message),
    })
  }

  return (
    <form onSubmit={submit} aria-labelledby="review" className="rounded-lg border border-line bg-card p-6">
      <h2 id="review" className="text-h3 font-semibold tracking-tight">Check what we found</h2>
      <p className="mt-1 text-small text-muted-foreground">From {resume.original_filename}. Change anything that’s wrong; nothing is saved until you confirm.</p>

      {(data.warnings.length > 0 || data.text_truncated) && (
        <ul className="mt-5 space-y-1.5 rounded-md border border-rose/30 p-3 text-small">
          {data.text_truncated && <li className="flex gap-2"><TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-rose" />The PDF was long, so only the first part was read.</li>}
          {data.warnings.map((w) => <li key={w} className="flex gap-2"><TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-rose" />{w}</li>)}
        </ul>
      )}

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <Field label="Name" value={fields.full_name} onChange={(v) => setFields({ ...fields, full_name: v })} />
        <Field label="Location" value={fields.location} onChange={(v) => setFields({ ...fields, location: v })} />
        <div className="space-y-1.5">
          <Label htmlFor="years">Years of experience</Label>
          <Input id="years" type="number" min={0} max={60} step="any" className="tnum" value={fields.experience_years}
            onChange={(e) => setFields({ ...fields, experience_years: e.target.value })} />
          <p className="text-micro text-muted-foreground">Worked out from your job dates: {data.experience_years_method}</p>
        </div>
      </div>
      <div className="mt-4 space-y-1.5">
        <Label htmlFor="summary">Summary</Label>
        <Textarea id="summary" rows={3} value={fields.summary} onChange={(e) => setFields({ ...fields, summary: e.target.value })} />
      </div>

      <fieldset className="mt-8">
        <legend className="font-semibold tracking-tight">Skills <span className="tnum font-normal text-muted-foreground">({chosen.length} selected)</span></legend>
        <SkillChecks items={confirmed.map((s) => s.name)} extra={[...skills.keys()].filter((k) => !data.skills.some((s) => s.name === k))}
          state={skills} toggle={(n) => setSkills((m) => new Map(m).set(n, !m.get(n)))} />
        {suggested.length > 0 && (
          <div className="mt-5">
            <p className="text-small text-muted-foreground">Found by keyword match only. Tick these only if you really have them.</p>
            <SkillChecks items={suggested.map((s) => s.name)} extra={[]} state={skills} toggle={(n) => setSkills((m) => new Map(m).set(n, !m.get(n)))} />
          </div>
        )}
        <div className="mt-4 flex max-w-md gap-2">
          <Input aria-label="Add skills, comma-separated" placeholder="Add a missing skill" value={extra}
            onChange={(e) => setExtra(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addExtra() } }} />
          <Button type="button" variant="outline" onClick={addExtra}>Add</Button>
        </div>
      </fieldset>

      {data.work_experience.length > 0 && (
        <section className="mt-8" aria-labelledby="work">
          <h3 id="work" className="font-semibold tracking-tight">Work experience</h3>
          <ul className="mt-2 space-y-2">
            {data.work_experience.map((w, i) => (
              <li key={i} className="text-small">
                <span className="font-semibold">{w.title ?? 'Role'}</span>{w.company && `, ${w.company}`}
                <span className="text-muted-foreground"> ({w.start_date ?? '?'} to {w.is_current ? 'now' : w.end_date ?? '?'})</span>
                {!w.grounded && <span className="block text-rose">Couldn’t find this in the PDF text. Check it before relying on it.</span>}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-micro text-muted-foreground">Used to work out your years of experience. Not stored separately.</p>
        </section>
      )}

      {(data.education.length > 0 || data.projects.length > 0) && (
        <section className="mt-8 space-y-3" aria-label="Education and projects">
          {data.education.length > 0 && (
            <Toggle checked={withEducation} onChange={setWithEducation}
              label={`Add education (${data.education.map((e) => [e.degree, e.institution].filter(Boolean).join(', ')).join('; ')})`} />
          )}
          {data.projects.length > 0 && (
            <Toggle checked={withProjects} onChange={setWithProjects} label={`Add projects (${data.projects.map((p) => p.name).join(', ')})`} />
          )}
        </section>
      )}

      <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-line pt-5">
        <Button type="submit" disabled={apply.isPending || chosen.length === 0}>{apply.isPending ? 'Adding…' : 'Add to my profile'}</Button>
        <p className="text-small text-muted-foreground">Skills are added to the ones already on your profile; none are removed.</p>
      </div>
    </form>
  )
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const id = useId()
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex items-start gap-2.5 text-small">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-0.5 size-4 accent-[var(--signal)]" />
      <span>{label}</span>
    </label>
  )
}

function SkillChecks({ items, extra, state, toggle }: { items: string[]; extra: string[]; state: Map<string, boolean>; toggle: (n: string) => void }) {
  return (
    <ul className="mt-3 flex flex-wrap gap-1.5">
      {[...items, ...extra].map((name) => {
        const on = state.get(name) ?? false
        return (
          <li key={name}>
            <label className={cn('inline-flex cursor-pointer items-center gap-1.5 rounded-md border px-2.5 py-1 text-small transition-colors',
              on ? 'border-sage/50 bg-sage/10' : 'border-line text-muted-foreground hover:text-foreground')}>
              <input type="checkbox" checked={on} onChange={() => toggle(name)} className="size-3.5 accent-[var(--sage)]" />
              {name}
            </label>
          </li>
        )
      })}
    </ul>
  )
}

function History({ items }: { items: ResumeT[] }) {
  const del = useDeleteResume()
  return (
    <section className="mt-10" aria-labelledby="earlier">
      <h2 id="earlier" className="mb-3 text-small text-muted-foreground">Earlier uploads</h2>
      <ul className="divide-y divide-line rounded-lg border border-line">
        {items.map((r) => (
          <li key={r.id} className="flex items-center justify-between gap-3 px-4 py-3 text-small">
            <span className="min-w-0 truncate">{r.original_filename}</span>
            <span className="flex shrink-0 items-center gap-3 text-muted-foreground">
              {STATUS[r.parsing_status]}, {ago(r.created_at)}
              <Button variant="ghost" size="icon-xs" aria-label={`Delete ${r.original_filename}`}
                onClick={() => del.mutate(r.id, { onSuccess: () => toast('Deleted') })}>
                <Trash2 aria-hidden="true" />
              </Button>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

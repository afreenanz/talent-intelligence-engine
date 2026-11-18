import { Fragment, type ReactNode } from 'react'
import { Link } from 'react-router'

import { useJob } from '@/features/jobs/api'

/**
 * Renders the assistant's reply: paragraphs, numbered/bulleted lists, **bold**, and
 * "[job_id: <uuid>]" references as links to the job, and bare job ids as the job's title. Output is built as React elements,
 * never as HTML, so nothing the model writes can inject markup or scripts.
 */
const UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
const INLINE = new RegExp(`(\\*\\*[^*\\n]+\\*\\*|\\[job_id:\\s*(${UUID})\\]|\\b(${UUID})\\b)`, 'gi')
const ITEM = /^\s*(\d+[.)]|[-*•])\s+/

function inline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  let last = 0
  for (const m of text.matchAll(INLINE)) {
    if (m.index > last) out.push(text.slice(last, m.index))
    if (m[3]) {
      out.push(<JobName key={m.index} id={m[3]} />) // a bare id: show the job's title instead
    } else if (m[2]) {
      out.push(
        <Link key={m.index} to={`/app/jobs/${m[2]}`} className="whitespace-nowrap text-small text-signal underline-offset-2 hover:underline">
          View job
        </Link>,
      )
    } else {
      out.push(<strong key={m.index} className="font-semibold">{m[0].slice(2, -2)}</strong>)
    }
    last = m.index + m[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

export function Reply({ text }: { text: string }) {
  const blocks = text.trim().split(/\n\s*\n/)
  return (
    <div className="space-y-3">
      {blocks.map((block, i) => {
        const lines = block.split('\n').filter((l) => l.trim())
        if (lines.length && lines.every((l) => ITEM.test(l))) {
          const ordered = /^\s*\d/.test(lines[0])
          const List = ordered ? 'ol' : 'ul'
          return (
            <List key={i} className={ordered ? 'list-decimal space-y-1.5 pl-5' : 'list-disc space-y-1.5 pl-5'}>
              {lines.map((l, j) => <li key={j}>{inline(l.replace(ITEM, ''))}</li>)}
            </List>
          )
        }
        return (
          <p key={i}>
            {lines.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{inline(l)}</Fragment>)}
          </p>
        )
      })}
    </div>
  )
}

function JobName({ id }: { id: string }) {
  const { data } = useJob(id)
  return (
    <Link to={`/app/jobs/${id}`} className="font-semibold underline-offset-2 hover:underline">
      {data ? `${data.title} at ${data.company}` : 'this job'}
    </Link>
  )
}

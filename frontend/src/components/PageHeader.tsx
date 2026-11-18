import type { ReactNode } from 'react'

export function PageHeader({ title, children, actions }: { title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-h1 font-semibold tracking-[-0.03em]">{title}</h1>
        {children && <p className="mt-2 max-w-[62ch] text-muted-foreground">{children}</p>}
      </div>
      {actions}
    </header>
  )
}

/** Empty and error states give direction, not mood. */
export function Notice({ title, children, action, tone = 'neutral' }: {
  title: string
  children?: ReactNode
  action?: ReactNode
  tone?: 'neutral' | 'error'
}) {
  return (
    <div role={tone === 'error' ? 'alert' : undefined} className="rounded-lg border border-dashed border-line px-6 py-10">
      <h2 className="font-semibold tracking-tight">{title}</h2>
      {children && <p className="mt-1.5 max-w-[60ch] text-small text-muted-foreground">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

/** Honest placeholder: this page is planned, not faked. */
export default function NotBuiltYet({ title, milestone, about }: { title: string; milestone: string; about: string }) {
  return (
    <div className="max-w-2xl">
      <h1 className="text-h1 font-semibold tracking-[-0.03em]">{title}</h1>
      <p className="mt-3 max-w-[60ch] text-muted-foreground">{about}</p>
      <p className="mt-6 inline-block rounded-md border border-line px-3 py-1.5 text-small text-muted-foreground">
        Built in {milestone}. The API for it already exists.
      </p>
    </div>
  )
}

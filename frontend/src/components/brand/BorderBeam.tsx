/**
 * A single short beam of warm light travelling around a card's border at constant speed.
 *
 * Constant speed comes from SVG geometry, not a rotating conic gradient: four <path>s trace the
 * same rounded rectangle with pathLength="100", so stroke-dash values are percentages of the
 * perimeter and stroke-dashoffset moves at a fixed rate around straight edges and corners alike.
 * The path is rebuilt with a ResizeObserver whenever the card changes size.
 *
 * Use at most once per screen, on the thing that matters most (e.g. the top match).
 */
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

function roundedRectPath(w: number, h: number, r: number): string {
  const x = 0.5
  const y = 0.5
  const W = Math.max(0, w - 1)
  const H = Math.max(0, h - 1)
  const rr = Math.min(r, W / 2, H / 2)
  return [
    `M ${x + rr} ${y}`, `H ${x + W - rr}`, `A ${rr} ${rr} 0 0 1 ${x + W} ${y + rr}`,
    `V ${y + H - rr}`, `A ${rr} ${rr} 0 0 1 ${x + W - rr} ${y + H}`,
    `H ${x + rr}`, `A ${rr} ${rr} 0 0 1 ${x} ${y + H - rr}`,
    `V ${y + rr}`, `A ${rr} ${rr} 0 0 1 ${x + rr} ${y}`, 'Z',
  ].join(' ')
}

const LAYERS = [
  { cls: 'beam-bloom', stroke: 'var(--signal)', width: 6, opacity: 0.5, dash: '10 90', blur: true },
  { cls: 'beam-tail', stroke: 'var(--signal-deep)', width: 1, opacity: 0.35, dash: '22 78' },
  { cls: 'beam-near', stroke: 'var(--signal)', width: 1.25, opacity: 0.7, dash: '12 88' },
  { cls: 'beam-head', stroke: 'var(--signal-soft)', width: 1.5, opacity: 1, dash: '4 96', round: true },
] as const

export function BorderBeam({ children, className, radius = 14 }: {
  children: ReactNode
  className?: string
  radius?: number
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [d, setD] = useState('')
  const [id] = useState(() => `beam-blur-${Math.random().toString(36).slice(2, 8)}`)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const update = () => setD(roundedRectPath(el.offsetWidth + 2, el.offsetHeight + 2, radius - 0.5))
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [radius])

  return (
    <div ref={ref} className={cn('group/beam relative', className)} style={{ borderRadius: radius }}>
      <svg aria-hidden="true" className="beam pointer-events-none absolute -inset-px overflow-visible opacity-85 transition-opacity duration-200 group-hover/beam:opacity-100">
        <defs>
          <filter id={id} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="4" />
          </filter>
        </defs>
        {LAYERS.map((l) => (
          <path key={l.cls} className={l.cls} d={d} pathLength={100} fill="none" stroke={l.stroke}
            strokeWidth={l.width} opacity={l.opacity} strokeDasharray={l.dash}
            strokeLinecap={'round' in l ? 'round' : 'butt'}
            filter={'blur' in l ? `url(#${id})` : undefined} />
        ))}
      </svg>
      <div className="relative z-[1]">{children}</div>
    </div>
  )
}

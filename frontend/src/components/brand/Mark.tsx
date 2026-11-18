/** The product mark: a 4x4 dot grid rising toward one bright point (the best match on the terrain). */
export function Mark({ className = 'size-5' }: { className?: string }) {
  const dots = []
  for (let r = 0; r < 4; r++) {
    for (let c = 0; c < 4; c++) {
      const peak = r === 1 && c === 2
      dots.push(
        <circle key={`${r}-${c}`} cx={3 + c * 6} cy={3 + r * 6} r={peak ? 2.4 : 1.25}
          className={peak ? 'fill-signal' : 'fill-current'} opacity={peak ? 1 : 0.35 + (3 - r) * 0.15} />,
      )
    }
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className}>
      {dots}
    </svg>
  )
}

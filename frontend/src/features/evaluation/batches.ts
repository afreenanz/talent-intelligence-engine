import type { EvaluationRun } from '@/lib/types'

const WINDOW_MS = 10 * 60_000

/**
 * The most recent batch of runs for an experiment (and split): runs recorded within 10 minutes of
 * the newest one, one per configuration name (newest wins). Older batches stay in the database
 * as history; the page shows what the code produces today.
 */
export function latestBatch(runs: EvaluationRun[], experiment: string, split?: string): EvaluationRun[] {
  const mine = runs
    .filter((r) => r.experiment_name === experiment && (split === undefined || r.split === split))
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
  if (!mine.length) return []
  const newest = Date.parse(mine[0].created_at)
  const seen = new Set<string>()
  return mine.filter((r) => {
    if (newest - Date.parse(r.created_at) > WINDOW_MS) return false
    const name = configName(r)
    if (seen.has(name)) return false
    seen.add(name)
    return true
  }).reverse() // chronological = the order the experiment ran its configurations
}

export function configName(r: EvaluationRun): string {
  const c = r.configuration
  return String(c.name ?? c.condition ?? c.model ?? r.experiment_name)
}

export function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

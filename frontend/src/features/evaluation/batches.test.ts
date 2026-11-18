import type { EvaluationRun } from '@/lib/types'

import { latestBatch } from './batches'

const run = (name: string, at: string, split = 'test', exp = 'retrieval_comparison'): EvaluationRun => ({
  id: `${name}-${at}`, experiment_name: exp, dataset_version: 'v1', split, configuration: { name }, metrics: {}, git_commit: null, created_at: at,
})

it('keeps only the newest batch, one run per configuration, in run order', () => {
  const runs = [
    run('lexical', '2026-11-17T17:18:00Z'), run('dense', '2026-11-17T17:18:05Z'), // older batch
    run('lexical', '2026-11-17T17:20:51Z'), run('dense', '2026-11-17T17:20:59Z'),
    run('lexical', '2026-11-17T17:21:30Z', 'dev'), // other split
  ]
  const batch = latestBatch(runs, 'retrieval_comparison', 'test')
  expect(batch.map((r) => r.id)).toEqual(['lexical-2026-11-17T17:20:51Z', 'dense-2026-11-17T17:20:59Z'])
  expect(latestBatch(runs, 'missing')).toEqual([])
})

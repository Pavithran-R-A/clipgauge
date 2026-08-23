export type SetupQueueState = 'pending' | 'running' | 'complete' | 'partial_failure' | 'failed' | 'cancelled'

export interface SetupQueueSummary {
  state: SetupQueueState
  completed: number
  failed: number
  cancelled: boolean
}

export function summarizeSetupQueue(outcomes: Array<'success' | 'failed' | 'cancelled'>, pending: number): SetupQueueSummary {
  const completed = outcomes.filter((outcome) => outcome === 'success').length
  const failed = outcomes.filter((outcome) => outcome === 'failed').length
  const cancelled = outcomes.includes('cancelled')
  if (cancelled) return { state: 'cancelled', completed, failed, cancelled: true }
  if (pending > 0 || outcomes.length === 0) return { state: outcomes.length ? 'running' : 'pending', completed, failed, cancelled: false }
  if (failed === 0) return { state: 'complete', completed, failed, cancelled: false }
  return { state: completed ? 'partial_failure' : 'failed', completed, failed, cancelled: false }
}

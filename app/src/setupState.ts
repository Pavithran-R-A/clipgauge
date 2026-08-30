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

export function selectedLocalModel(inventory: unknown): string | undefined {
  if (!inventory || typeof inventory !== 'object') return undefined
  const localAI = (inventory as { local_ai?: unknown }).local_ai
  if (!localAI || typeof localAI !== 'object') return undefined
  const selected = (localAI as { selected_model_id?: unknown }).selected_model_id
  return typeof selected === 'string' && selected.startsWith('clipgauge-local/') ? selected : undefined
}

export function resolveSelectedLocalModel(inventory: unknown, preferred?: string | null): string | undefined {
  if (!inventory || typeof inventory !== 'object') return undefined
  const value = inventory as { models?: unknown }
  const models = Array.isArray(value.models) ? value.models : []
  const modelIds = models
    .filter((model): model is { asset_id?: unknown } => Boolean(model && typeof model === 'object'))
    .map((model) => model.asset_id)
    .filter((id): id is string => typeof id === 'string' && id.startsWith('clipgauge-local/'))
  const isAvailable = (id: string | undefined) => Boolean(id && (!modelIds.length || modelIds.includes(id)))
  if (isAvailable(preferred ?? undefined)) return preferred ?? undefined
  const persisted = selectedLocalModel(inventory)
  if (isAvailable(persisted)) return persisted
  return modelIds[0]
}

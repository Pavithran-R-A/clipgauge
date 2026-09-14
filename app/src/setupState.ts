export type SetupQueueState = 'pending' | 'running' | 'complete' | 'partial_failure' | 'failed' | 'cancelled'

export interface SetupQueueSummary {
  state: SetupQueueState
  completed: number
  failed: number
  cancelled: boolean
}

export function isLocalAiUnavailable(inventory: unknown): boolean {
  if (!inventory || typeof inventory !== 'object') return false
  const localAI = (inventory as { local_ai?: unknown }).local_ai
  if (!localAI || typeof localAI !== 'object') return false
  return (localAI as { state?: unknown }).state === 'unavailable'
}

export function shouldAdvanceSetupQueue(payload: { event?: string; ok?: boolean }): boolean {
  return payload.event === 'terminal' && payload.ok === true
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
  const selected = (localAI as { selected_model_id?: unknown; preferred_model_id?: unknown }).preferred_model_id
    ?? (localAI as { selected_model_id?: unknown }).selected_model_id
  return typeof selected === 'string' && selected.startsWith('clipgauge-local/') ? selected : undefined
}

function localModelRows(inventory: unknown): Array<Record<string, unknown>> {
  if (!inventory || typeof inventory !== 'object') return []
  const models = (inventory as { models?: unknown }).models
  return Array.isArray(models)
    ? models.filter((model): model is Record<string, unknown> => Boolean(model && typeof model === 'object' && !Array.isArray(model)))
    : []
}

function localModelId(value: unknown): value is string {
  return typeof value === 'string' && value.startsWith('clipgauge-local/')
}

function localAi(inventory: unknown): Record<string, unknown> {
  if (!inventory || typeof inventory !== 'object') return {}
  const value = (inventory as { local_ai?: unknown }).local_ai
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function listedModel(inventory: unknown, id: string): boolean {
  const rows = localModelRows(inventory)
  return rows.length === 0 || rows.some((row) => row.asset_id === id)
}

export function resolvePreferredLocalModel(inventory: unknown, preferred?: string | null): string | undefined {
  const candidate = preferred ?? localAi(inventory).preferred_model_id ?? selectedLocalModel(inventory)
  return localModelId(candidate) && listedModel(inventory, candidate) ? candidate : undefined
}

function isRunnableModel(row: Record<string, unknown>): boolean {
  const readiness = row.readiness
  const readinessReady = readiness && typeof readiness === 'object' && !Array.isArray(readiness)
    ? (readiness as { verified?: unknown; usable?: unknown })
    : {}
  return row.installed === true
    && row.lifecycle_state === 'VERIFIED'
    && readinessReady.verified === true
    && readinessReady.usable === true
}

export function resolveRunnableLocalModel(inventory: unknown): string | undefined {
  const preferred = resolvePreferredLocalModel(inventory)
  const runnable = localAi(inventory).runnable_model_id
  if (!localModelId(runnable)) return undefined
  if (preferred && runnable !== preferred) return undefined
  const candidate = runnable
  const row = localModelRows(inventory).find((model) => model.asset_id === candidate)
  return row && isRunnableModel(row) ? candidate : undefined
}

export function resolveSelectedLocalModel(inventory: unknown, preferred?: string | null): string | undefined {
  return resolvePreferredLocalModel(inventory, preferred)
}

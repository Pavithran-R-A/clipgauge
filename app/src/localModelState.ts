import type { LocalSetupInventory } from './types'
import { resolvePreferredLocalModel, resolveRunnableLocalModel } from './setupState'

export type LocalModelState = {
  inventory: LocalSetupInventory | null
  preferredModelId: string | null
  runnableModelId: string | null
  loading: boolean
  error: string | null
}

export type LocalModelOption = {
  id: string
  label: 'Lightweight' | 'Balanced'
  modelName: 'Qwen3 1.7B' | 'Qwen3 4B'
  status: 'Installed · Verified' | 'Download required' | 'Needs repair' | 'Unavailable'
  installed: boolean
  verified: boolean
  usable: boolean
  purpose: string
  row: Record<string, unknown> | null
}

export const LOCAL_MODEL_STORAGE_KEY = 'clipgauge.local-model.v1'
const LEGACY_LOCAL_MODEL_STORAGE_KEY = 'clipgauge.provider-model.clipgauge-local'

const MANAGED_LOCAL_MODELS = [
  { id: 'clipgauge-local/qwen3-1.7b-q8_0', label: 'Lightweight' as const, modelName: 'Qwen3 1.7B' as const, match: '1.7b', purpose: 'Lower-memory local scoring.' },
  { id: 'clipgauge-local/qwen3-4b-q4_k_m', label: 'Balanced' as const, modelName: 'Qwen3 4B' as const, match: '4b', purpose: 'Higher-quality local scoring.' },
]

export function canonicalLocalModelId(value: string | null | undefined): string | null {
  const normalized = value?.trim().toLowerCase()
  if (!normalized) return null
  if (normalized === MANAGED_LOCAL_MODELS[0].id || normalized.includes('1.7b') || normalized.includes('/light')) return MANAGED_LOCAL_MODELS[0].id
  if (normalized === MANAGED_LOCAL_MODELS[1].id || normalized.includes('4b') || normalized.includes('/balanced')) return MANAGED_LOCAL_MODELS[1].id
  return null
}

export function readSavedLocalModel(): string | null {
  if (typeof window === 'undefined') return null
  try {
    const current = canonicalLocalModelId(window.localStorage.getItem(LOCAL_MODEL_STORAGE_KEY))
    if (current) return current
    const legacy = canonicalLocalModelId(window.localStorage.getItem(LEGACY_LOCAL_MODEL_STORAGE_KEY))
    if (legacy) window.localStorage.setItem(LOCAL_MODEL_STORAGE_KEY, legacy)
    return legacy
  } catch {
    return null
  }
}

export function writeSavedLocalModel(modelId: string): void {
  const canonical = canonicalLocalModelId(modelId)
  if (!canonical || typeof window === 'undefined') return
  try { window.localStorage.setItem(LOCAL_MODEL_STORAGE_KEY, canonical) } catch { /* optional browser storage */ }
}

function rowsFor(inventory: LocalSetupInventory | null): Record<string, unknown>[] {
  return inventory?.models ?? []
}

function matchingRow(rows: Record<string, unknown>[], model: typeof MANAGED_LOCAL_MODELS[number]): Record<string, unknown> | null {
  return rows.find((row) => row.asset_id === model.id)
    ?? rows.find((row) => `${String(row.asset_id ?? '')} ${String(row.display_name ?? '')}`.toLowerCase().includes(model.match))
    ?? null
}

function readiness(row: Record<string, unknown> | null): { installed: boolean; verified: boolean; usable: boolean } {
  const rowReadiness = row?.readiness
  const verified = rowReadiness && typeof rowReadiness === 'object' && !Array.isArray(rowReadiness)
    ? (rowReadiness as { verified?: unknown }).verified === true
    : false
  const usable = rowReadiness && typeof rowReadiness === 'object' && !Array.isArray(rowReadiness)
    ? (rowReadiness as { usable?: unknown }).usable === true
    : false
  return { installed: row?.installed === true, verified, usable }
}

function statusFor(row: Record<string, unknown> | null, state: ReturnType<typeof readiness>): LocalModelOption['status'] {
  if (state.installed && row?.lifecycle_state === 'VERIFIED' && state.verified && state.usable) return 'Installed · Verified'
  if (row?.lifecycle_state === 'NEEDS_REPAIR' || Boolean((row?.readiness as { repair?: unknown } | undefined)?.repair)) return 'Needs repair'
  if (row?.lifecycle_state === 'DOWNLOAD_REQUIRED' || !state.installed) return 'Download required'
  return 'Unavailable'
}

export function localModelOptions(inventory: LocalSetupInventory | null): LocalModelOption[] {
  const rows = rowsFor(inventory)
  const hasModelCatalog = rows.length > 0
  return MANAGED_LOCAL_MODELS.map((model) => {
    const row = matchingRow(rows, model)
    const state = readiness(row)
    return {
      id: model.id,
      label: model.label,
      modelName: model.modelName,
      status: inventory && hasModelCatalog ? statusFor(row, state) : 'Unavailable',
      installed: state.installed,
      verified: state.verified,
      usable: state.usable,
      purpose: String(row?.purpose ?? model.purpose),
      row,
    }
  })
}

export function normalizeLocalModelState(inventory: LocalSetupInventory | null, savedPreferredModelId?: string | null): LocalModelState {
  const nativePreferredModelId = canonicalLocalModelId(inventory ? resolvePreferredLocalModel(inventory) : null)
  const nativeRunnableModelId = canonicalLocalModelId(inventory ? resolveRunnableLocalModel(inventory) : null)
  return {
    inventory,
    preferredModelId: nativePreferredModelId ?? canonicalLocalModelId(savedPreferredModelId),
    runnableModelId: nativeRunnableModelId,
    loading: false,
    error: null,
  }
}

export function localModelDisplayName(modelId: string | null | undefined): string {
  const value = String(modelId ?? '').toLowerCase()
  if (value.includes('1.7b')) return 'Lightweight · Qwen3 1.7B'
  if (value.includes('4b')) return 'Balanced · Qwen3 4B'
  return 'Choose a local model'
}

export function isExecutionModel(value: string | null | undefined): value is string {
  if (!value?.trim()) return false
  return !['choose in setup', 'selected local model', 'model required', 'choose a model'].includes(value.trim().toLowerCase())
}

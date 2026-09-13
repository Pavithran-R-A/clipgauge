import type { LocalSetupInventory } from './types'
import { isLocalSetupInventory } from './nativeValidation'

export const SETUP_INVENTORY_CACHE_KEY = 'clipgauge.setup.inventory.v1'
export const SETUP_INVENTORY_CACHE_SCHEMA_VERSION = 1
export const SETUP_INVENTORY_CACHE_APP_VERSION = '0.5.16'

type InventoryCacheRecord = {
  schema_version: number
  app_version: string
  platform: string
  runtime_manifest_digest: string
  last_verified_at: number | null
  value: LocalSetupInventory
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isInventoryCache(value: unknown): value is InventoryCacheRecord {
  return isRecord(value)
    && value.schema_version === SETUP_INVENTORY_CACHE_SCHEMA_VERSION
    && value.app_version === SETUP_INVENTORY_CACHE_APP_VERSION
    && isNonEmptyString(value.platform)
    && isNonEmptyString(value.runtime_manifest_digest)
    && (value.last_verified_at === null || (typeof value.last_verified_at === 'number' && Number.isFinite(value.last_verified_at)))
    && isLocalSetupInventory(value.value)
}

export function readCachedSetupInventory(): LocalSetupInventory | null {
  try {
    const raw = window.localStorage.getItem(SETUP_INVENTORY_CACHE_KEY)
    if (!raw) return null
    const value: unknown = JSON.parse(raw)
    if (!isInventoryCache(value)) return null
    return { ...value.value, last_verified_at: value.last_verified_at ?? value.value.last_verified_at }
  } catch {
    return null
  }
}

export function writeCachedSetupInventory(value: LocalSetupInventory) {
  try {
    const platform = value.platform?.trim()
    const runtimeManifestDigest = value.runtime_manifest_digest?.trim()
    if (!platform || !runtimeManifestDigest) return
    window.localStorage.setItem(SETUP_INVENTORY_CACHE_KEY, JSON.stringify({
      schema_version: SETUP_INVENTORY_CACHE_SCHEMA_VERSION,
      app_version: SETUP_INVENTORY_CACHE_APP_VERSION,
      platform,
      runtime_manifest_digest: runtimeManifestDigest,
      last_verified_at: value.last_verified_at ?? null,
      value,
    } satisfies InventoryCacheRecord))
  } catch { /* optional browser storage */ }
}

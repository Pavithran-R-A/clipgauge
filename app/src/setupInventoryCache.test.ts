import { beforeEach, describe, expect, it } from 'vitest'
import { isFreshSetupInventory, readCachedSetupInventory, writeCachedSetupInventory } from './setupInventoryCache'
import type { LocalSetupInventory } from './types'

const inventory = {
  state: 'ready',
  runtime: {},
  models: [],
  core_assets: [],
  storage: { required_bytes: 0, consent_required: false, assets: [] },
  catalog: []
} satisfies LocalSetupInventory

describe('setup inventory cache identity', () => {
  beforeEach(() => {
    const values = new Map<string, string>()
    Object.defineProperty(window, 'localStorage', { configurable: true, value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value) },
      removeItem: (key: string) => { values.delete(key) }
    } })
  })

  it('rejects an envelope without verified platform identity', () => {
    window.localStorage.setItem('clipgauge.setup.inventory.v1', JSON.stringify({
      schema_version: 1,
      app_version: '0.5.16',
      platform: '',
      runtime_manifest_digest: '',
      last_verified_at: 1_700_000_000,
      value: inventory
    }))

    expect(readCachedSetupInventory()).toBeNull()
  })

  it('does not persist an inventory without verified identity', () => {
    writeCachedSetupInventory(inventory)

    expect(window.localStorage.getItem('clipgauge.setup.inventory.v1')).toBeNull()
  })

  it('only treats recent verified inventory as fresh', () => {
    const now = 1_700_000_000_000

    expect(isFreshSetupInventory({ ...inventory, last_verified_at: (now - 60_000) / 1000 }, now)).toBe(true)
    expect(isFreshSetupInventory({ ...inventory, last_verified_at: (now - 15 * 60_000 - 1) / 1000 }, now)).toBe(false)
    expect(isFreshSetupInventory({ ...inventory, last_verified_at: (now + 60_000) / 1000 }, now)).toBe(false)
    expect(isFreshSetupInventory({ ...inventory, last_verified_at: null }, now)).toBe(false)
  })
})

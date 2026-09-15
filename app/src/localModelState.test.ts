import { beforeEach, describe, expect, it } from 'vitest'
import { localModelOptions, normalizeLocalModelState, readSavedLocalModel, writeSavedLocalModel } from './localModelState'

const inventory = (overrides: Record<string, unknown> = {}) => ({
  state: 'ready',
  platform: 'windows-x86_64',
  runtime_manifest_digest: 'test-manifest',
  local_ai: {
    state: 'ready',
    runtime_ready: true,
    model_ready: true,
    preferred_model_id: 'clipgauge-local/qwen3-1.7b-q8_0',
    runnable_model_id: 'clipgauge-local/qwen3-1.7b-q8_0',
    ...overrides,
  },
  runtime: {},
  models: [
    {
      asset_id: 'clipgauge-local/qwen3-1.7b-q8_0',
      installed: true,
      lifecycle_state: 'VERIFIED',
      readiness: { verified: true, usable: true },
    },
  ],
  core_assets: [],
  storage: {},
  catalog: [],
})

describe('canonical local model state', () => {
  beforeEach(() => window.localStorage.clear())

  it('keeps Lightweight and Balanced visible', () => {
    const options = localModelOptions(inventory() as never)

    expect(options.map((option) => option.id)).toEqual([
      'clipgauge-local/qwen3-1.7b-q8_0',
      'clipgauge-local/qwen3-4b-q4_k_m',
    ])
    expect(options[0]).toMatchObject({ label: 'Lightweight', modelName: 'Qwen3 1.7B', status: 'Installed · Verified' })
    expect(options[1]).toMatchObject({ label: 'Balanced', modelName: 'Qwen3 4B', status: 'Download required' })
  })

  it('atomically derives preferred and runnable model ids', () => {
    const state = normalizeLocalModelState(inventory() as never)

    expect(state.preferredModelId).toBe('clipgauge-local/qwen3-1.7b-q8_0')
    expect(state.runnableModelId).toBe('clipgauge-local/qwen3-1.7b-q8_0')
    expect(state.inventory).not.toBeNull()
  })

  it('migrates legacy presentation ids to canonical execution ids', () => {
    const legacy = inventory({
      preferred_model_id: 'clipgauge-local/balanced',
      runnable_model_id: 'clipgauge-local/balanced',
    })
    legacy.models.push({
      asset_id: 'clipgauge-local/balanced',
      installed: true,
      lifecycle_state: 'VERIFIED',
      readiness: { verified: true, usable: true },
    })
    expect(normalizeLocalModelState(legacy as never)).toMatchObject({
      preferredModelId: 'clipgauge-local/qwen3-4b-q4_k_m',
      runnableModelId: 'clipgauge-local/qwen3-4b-q4_k_m',
    })
  })

  it('marks both managed choices unavailable without inventory', () => {
    expect(localModelOptions(null).map((option) => option.status)).toEqual(['Unavailable', 'Unavailable'])
  })

  it('migrates the legacy saved choice across restarts', () => {
    window.localStorage.setItem('clipgauge.provider-model.clipgauge-local', 'clipgauge-local/balanced')
    expect(readSavedLocalModel()).toBe('clipgauge-local/qwen3-4b-q4_k_m')
    expect(window.localStorage.getItem('clipgauge.local-model.v1')).toBe('clipgauge-local/qwen3-4b-q4_k_m')

    writeSavedLocalModel('clipgauge-local/qwen3-1.7b-q8_0')
    expect(readSavedLocalModel()).toBe('clipgauge-local/qwen3-1.7b-q8_0')
  })
})

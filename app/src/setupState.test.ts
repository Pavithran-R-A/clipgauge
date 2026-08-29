import { describe, expect, it } from 'vitest'
import { resolveSelectedLocalModel, selectedLocalModel, summarizeSetupQueue } from './setupState'

describe('setup queue aggregation', () => {
  it('reports complete only when every operation succeeds', () => {
    expect(summarizeSetupQueue(['success', 'success'], 0).state).toBe('complete')
  })

  it('reports partial failure when a later operation fails', () => {
    expect(summarizeSetupQueue(['success', 'failed', 'success'], 0)).toMatchObject({ state: 'partial_failure', completed: 2, failed: 1 })
  })

  it('reports failed when the first operation fails', () => {
    expect(summarizeSetupQueue(['failed'], 0).state).toBe('failed')
  })

  it('reports cancellation independently of successful earlier operations', () => {
    expect(summarizeSetupQueue(['success', 'cancelled'], 0).state).toBe('cancelled')
  })

  it('keeps an active queue running until the final terminal event', () => {
    expect(summarizeSetupQueue(['success'], 1).state).toBe('running')
  })

  it('uses the persisted verified lightweight local model from inventory', () => {
    expect(selectedLocalModel({ local_ai: { selected_model_id: 'clipgauge-local/qwen3-1.7b-q8_0' } })).toBe('clipgauge-local/qwen3-1.7b-q8_0')
  })

  it('ignores malformed or non-local inventory model selections', () => {
    expect(selectedLocalModel({ local_ai: { selected_model_id: 'gemini-flash-latest' } })).toBeUndefined()
    expect(selectedLocalModel({ local_ai: null })).toBeUndefined()
  })

  it('keeps the explicitly chosen model when inventory returns a different server default', () => {
    const inventory = {
      local_ai: { selected_model_id: 'clipgauge-local/qwen3-4b-q4_k_m' },
      models: [
        { asset_id: 'clipgauge-local/qwen3-1.7b-q8_0' },
        { asset_id: 'clipgauge-local/qwen3-4b-q4_k_m' }
      ]
    }
    expect(resolveSelectedLocalModel(inventory, 'clipgauge-local/qwen3-1.7b-q8_0')).toBe('clipgauge-local/qwen3-1.7b-q8_0')
  })

  it('falls back to the persisted verified selection', () => {
    const inventory = {
      local_ai: { selected_model_id: 'clipgauge-local/qwen3-1.7b-q8_0' },
      models: [{ asset_id: 'clipgauge-local/qwen3-1.7b-q8_0' }]
    }
    expect(resolveSelectedLocalModel(inventory)).toBe('clipgauge-local/qwen3-1.7b-q8_0')
  })
})

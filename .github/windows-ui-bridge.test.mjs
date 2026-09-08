import assert from 'node:assert/strict'
import test from 'node:test'
import { getTauriBridgeFacts, hasTauriInvoke } from './windows-ui-bridge.mjs'

test('accepts the global Tauri core invoke bridge', () => {
  const facts = getTauriBridgeFacts({ __TAURI__: { core: { invoke() {} } } })
  assert.deepEqual(facts, {
    tauri_global: true,
    tauri_core: true,
    tauri_core_invoke: true,
    internals_global: false,
    internals_invoke: false,
  })
  assert.equal(hasTauriInvoke(facts), true)
})

test('accepts the internal Tauri invoke bridge', () => {
  const facts = getTauriBridgeFacts({ __TAURI_INTERNALS__: { invoke() {} } })
  assert.equal(facts.tauri_global, false)
  assert.equal(facts.internals_global, true)
  assert.equal(facts.internals_invoke, true)
  assert.equal(hasTauriInvoke(facts), true)
})

test('rejects an unavailable bridge', () => {
  const facts = getTauriBridgeFacts({ __TAURI__: { core: {} } })
  assert.equal(hasTauriInvoke(facts), false)
})

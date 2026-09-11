import { describe, expect, it } from 'vitest'
import { isInstagramStatus, isJobSummaryList, isLocalSetupInventory, isPlaybackUrl, isPreflightResult, isPrivacySummary, isProviderModelsResult, isProviderTestResult, isSetupState, isStorageCleanupPreview, isStorageCleanupResult, isYouTubeReadiness } from './nativeValidation'

describe('native response validation', () => {
  it('accepts the setup state contract', () => {
    expect(isSetupState({ onboarded: true, has_gemini_key: false, provider_keys: { groq: true } })).toBe(true)
    expect(isSetupState({ onboarded: 'yes', has_gemini_key: false })).toBe(false)
  })

  it('rejects malformed health response shapes', () => {
    expect(isPreflightResult({ state: 'ready', selected_llm: 'local', checks: [] })).toBe(true)
    expect(isPreflightResult({ state: 'ready', selected_llm: 'local', checks: [null] })).toBe(false)
    expect(isYouTubeReadiness({ state: 'READY', ready: true, reason: 'ok', actions: ['Test'], checks: [] })).toBe(true)
    expect(isYouTubeReadiness({ state: 'READY', ready: true, reason: 'ok', actions: [null], checks: [] })).toBe(false)
  })

  it('validates optional setup inventory cache identity fields', () => {
    const inventory = { state: 'ready', platform: 'windows-x86_64', runtime_manifest_digest: 'manifest-a', runtime: {}, models: [], core_assets: [], storage: {}, catalog: [] }
    expect(isLocalSetupInventory(inventory)).toBe(true)
    expect(isLocalSetupInventory({ ...inventory, platform: 7 })).toBe(false)
    expect(isLocalSetupInventory({ ...inventory, runtime_manifest_digest: null })).toBe(false)
  })

  it('rejects malformed Instagram status values', () => {
    expect(isInstagramStatus({ connected: false })).toBe(true)
    expect(isInstagramStatus({ connected: 'false' })).toBe(false)
  })

  it('rejects malformed provider connection results', () => {
    expect(isProviderTestResult({ state: 'PASS', models: [{ id: 'model', compatibility: 'FULL' }] })).toBe(true)
    expect(isProviderTestResult({ state: null })).toBe(false)
    expect(isProviderTestResult({ state: 'PASS', models: [{ id: 'model' }] })).toBe(false)
  })

  it('rejects malformed provider model-list envelopes', () => {
    expect(isProviderModelsResult({ state: 'PASS', provider: 'groq', models: [] })).toBe(true)
    expect(isProviderModelsResult({ state: 'CONNECTED', models: [] })).toBe(false)
    expect(isProviderModelsResult({ state: 'PASS', models: 'not-an-array' })).toBe(false)
  })

  it('rejects malformed saved-session listings', () => {
    expect(isJobSummaryList([{ id: 'job', title: null, ingested: true, rendered: false }])).toBe(true)
    expect(isJobSummaryList([{ id: 'job', title: null, ingested: true, rendered: false, outcome: null }])).toBe(true)
    expect(isJobSummaryList([{ id: 'job', title: 'Saved', ingested: 'yes', rendered: false }])).toBe(false)
  })

  it('rejects malformed privacy summaries', () => {
    expect(isPrivacySummary({ local_first: true, telemetry: 'off', instagram: 'optional', source: 'fixture', llm: { mode: 'local', device: ['disk'], network: [], provider: 'local' } })).toBe(true)
    expect(isPrivacySummary({ local_first: true, telemetry: 'off', instagram: 'optional', source: 'fixture', llm: null })).toBe(false)
  })

  it('rejects malformed storage cleanup responses', () => {
    const preview = { target: 'safe-cache', bytes: 10, paths: ['cache.tmp'], requires_confirmation: true }
    expect(isStorageCleanupPreview(preview)).toBe(true)
    expect(isStorageCleanupResult({ ...preview, removed: ['cache.tmp'] })).toBe(true)
    expect(isStorageCleanupPreview({ ...preview, paths: 'cache.tmp' })).toBe(false)
    expect(isStorageCleanupResult({ ...preview, removed: [null] })).toBe(false)
  })

  it('rejects empty playback URLs', () => {
    expect(isPlaybackUrl('http://127.0.0.1/media/token')).toBe(true)
    expect(isPlaybackUrl('')).toBe(false)
    expect(isPlaybackUrl(null)).toBe(false)
  })
})

import { describe, expect, it } from 'vitest'
import { evaluateProviderReadiness, resolveProviderExecution } from './providerContract'

describe('provider execution contract', () => {
  it.each([
    ['clipgauge-local', 'private', 'clipgauge-local/qwen3-4b-q4_k_m', 'local'],
    ['ollama', 'private', 'llama3.2:3b', 'local'],
    ['lmstudio', 'private', 'qwen2.5-7b-instruct', 'local'],
    ['groq', 'balanced', 'openai/gpt-oss-20b', 'cloud'],
    ['groq', 'best', 'openai/gpt-oss-20b', 'cloud'],
    ['openrouter', 'balanced', 'openrouter/free', 'cloud'],
    ['custom', 'best', 'my-model', 'cloud'],
  ] as const)('keeps actual provider and model for %s + %s', (provider, qualityMode, model, locality) => {
    expect(resolveProviderExecution(provider, qualityMode, model)).toEqual({ provider, model, locality, qualityMode })
  })

  it('protects private mode from cloud substitution', () => {
    expect(() => resolveProviderExecution('groq', 'private', 'openai/gpt-oss-20b')).toThrow(
      'private mode requires a local provider',
    )
  })

  it('does not treat a cloud credential as private local readiness', () => {
    const result = evaluateProviderReadiness({
      provider: 'groq',
      locality: 'cloud',
      model: 'openai/gpt-oss-20b',
      credentialReady: true,
      modelAvailable: false,
      modelCompatible: false,
    })

    expect(result.can_private).toBe(false)
    expect(result.can_hybrid).toBe(false)
    expect(result.can_best).toBe(false)
    expect(result.blocking_reasons).toEqual(expect.arrayContaining(['Choose a compatible model']))
  })

  it('requires an endpoint for Cloudflare and Custom readiness', () => {
    expect(evaluateProviderReadiness({
      provider: 'cloudflare',
      locality: 'cloud',
      model: '@cf/meta/llama-3.1-8b-instruct',
      credentialReady: true,
      endpointReady: false,
      modelAvailable: true,
      modelCompatible: true,
    }).blocking_reasons).toContain('Enter endpoint')

    expect(evaluateProviderReadiness({
      provider: 'custom',
      locality: 'cloud',
      model: '',
      credentialReady: true,
      endpointReady: true,
      modelAvailable: false,
      modelCompatible: false,
    }).blocking_reasons).toContain('Choose a model')
  })
})

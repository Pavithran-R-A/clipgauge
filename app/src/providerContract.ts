export type QualityMode = 'private' | 'balanced' | 'best'
export type ProviderLocality = 'local' | 'cloud'

export const LOCAL_PROVIDER_IDS = ['clipgauge-local', 'ollama', 'lmstudio'] as const
export const CLOUD_PROVIDER_IDS = [
  'openrouter',
  'gemini',
  'groq',
  'cloudflare',
  'huggingface',
  'cerebras',
  'custom',
] as const

export interface ProviderExecution {
  provider: string
  model: string | undefined
  locality: ProviderLocality
  qualityMode: QualityMode
}

export interface ProviderReadinessInput {
  provider: string
  locality?: ProviderLocality
  model?: string
  credentialReady?: boolean
  endpointReady?: boolean
  modelAvailable?: boolean
  modelCompatible?: boolean
  runtimeReady?: boolean
  localModelReady?: boolean
  serviceReady?: boolean
}

export interface ProviderReadiness {
  provider: string
  locality: ProviderLocality
  configured: boolean
  credential_ready: boolean
  endpoint_ready: boolean
  model_ready: boolean
  model_available: boolean
  model_compatible: boolean
  can_private: boolean
  can_hybrid: boolean
  can_best: boolean
  blocking_reasons: string[]
  warnings: string[]
}

export function providerLocality(provider: string): ProviderLocality {
  return (LOCAL_PROVIDER_IDS as readonly string[]).includes(provider) ? 'local' : 'cloud'
}

export function isCloudProvider(provider: string): boolean {
  return (CLOUD_PROVIDER_IDS as readonly string[]).includes(provider)
}

export function resolveProviderExecution(provider: string, qualityMode: QualityMode, model?: string): ProviderExecution {
  const locality = providerLocality(provider)
  if (qualityMode === 'private' && locality !== 'local') {
    throw new Error('private mode requires a local provider; choose a local provider')
  }
  if (qualityMode !== 'private' && locality !== 'cloud') {
    throw new Error('balanced and best mode require a cloud provider; choose a cloud provider')
  }
  return { provider, model, locality, qualityMode }
}

export function evaluateProviderReadiness(input: ProviderReadinessInput): ProviderReadiness {
  const locality = input.locality ?? providerLocality(input.provider)
  const isCloudflareOrCustom = input.provider === 'cloudflare' || input.provider === 'custom'
  const credentialReady = locality === 'local' || input.credentialReady === true
  const endpointReady = input.endpointReady ?? (!isCloudflareOrCustom || locality === 'local')
  const modelReady = Boolean(input.model?.trim())
  const modelAvailable = input.modelAvailable ?? modelReady
  const modelCompatible = input.modelCompatible ?? true
  const runtimeReady = input.runtimeReady ?? true
  const localModelReady = input.localModelReady ?? true
  const serviceReady = input.serviceReady ?? true
  const blockingReasons: string[] = []

  if (!credentialReady) blockingReasons.push('Save credential')
  if (!endpointReady) blockingReasons.push('Enter endpoint')
  if (!modelReady) blockingReasons.push('Choose a model')
  else if (!modelAvailable || !modelCompatible) blockingReasons.push('Choose a compatible model')
  if (locality === 'local' && !localModelReady) blockingReasons.push('Choose a ready local model')
  if (locality === 'local' && !runtimeReady) blockingReasons.push('Install or repair the local runtime')
  if (locality === 'local' && !serviceReady) {
    blockingReasons.push(input.provider === 'ollama' ? 'Test/start Ollama' : input.provider === 'lmstudio' ? 'Test/start LM Studio' : 'Repair ClipGauge Local')
  }

  const configured = credentialReady && endpointReady && modelReady && modelAvailable && modelCompatible && runtimeReady && localModelReady && serviceReady
  return {
    provider: input.provider,
    locality,
    configured,
    credential_ready: credentialReady,
    endpoint_ready: endpointReady,
    model_ready: modelReady,
    model_available: modelAvailable,
    model_compatible: modelCompatible,
    can_private: locality === 'local' && configured,
    can_hybrid: locality === 'cloud' && configured,
    can_best: locality === 'cloud' && configured,
    blocking_reasons: blockingReasons,
    warnings: [],
  }
}

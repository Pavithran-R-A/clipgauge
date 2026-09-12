import { useEffect, useMemo, useRef, useState } from 'react'
import { confirm } from '@tauri-apps/plugin-dialog'
import { Check, ChevronRight, CircleAlert, Cloud, Cpu, ExternalLink, KeyRound, Network, RotateCcw, Save, ShieldCheck, WifiOff } from 'lucide-react'
import { api } from '../api'
import type { LocalSetupInventory, ProviderModel, ProviderTestResult, SetupState } from '../types'
import { selectedLocalModel } from '../setupState'
import { readCachedSetupInventory, writeCachedSetupInventory } from '../setupInventoryCache'
import { isProviderInventory, isProviderModelsResult, isProviderTestResult, isSetupState } from '../nativeValidation'
import { friendlyErrorMessage } from '../errorMessaging'

interface Props {
  selectedProvider: string
  onSelectProvider: (provider: string) => void
  onBack: () => void
  onOpenSetup?: () => void
}

type ProviderDefinition = {
  id: string
  name: string
  group: 'Built in' | 'Free-friendly cloud' | 'Cloud providers' | 'Local apps' | 'Advanced'
  description: string
  detail: string
  locality: 'local' | 'cloud'
  model: string
  endpoint?: string
  badge?: string
  credential?: boolean
}

const PROVIDERS: ProviderDefinition[] = [
  { id: 'clipgauge-local', name: 'ClipGauge Local', group: 'Built in', description: 'Runs scoring on this computer.', detail: 'No API key. Your video stays on this computer while the local engine is ready.', locality: 'local', model: '', endpoint: 'http://127.0.0.1:8080/v1', badge: 'Recommended for privacy' },
  { id: 'openrouter', name: 'OpenRouter Free', group: 'Free-friendly cloud', description: 'Use available free cloud models.', detail: 'Internet required. Availability and limits depend on the current free route.', locality: 'cloud', model: 'openrouter/free', badge: 'Free route available', credential: true },
  { id: 'gemini', name: 'Gemini', group: 'Cloud providers', description: 'Google cloud models for scoring.', detail: 'A Google AI Studio key is required. Credentials are stored in your operating-system vault.', locality: 'cloud', model: 'gemini-flash-latest', credential: true },
  { id: 'groq', name: 'Groq', group: 'Cloud providers', description: 'Fast cloud inference from Groq.', detail: 'Internet required. Add a Groq API key to use this provider.', locality: 'cloud', model: 'openai/gpt-oss-20b', credential: true },
  { id: 'cloudflare', name: 'Cloudflare Workers AI', group: 'Cloud providers', description: 'Cloud inference through Cloudflare.', detail: 'Requires your Cloudflare account credentials and a supported model route.', locality: 'cloud', model: '@cf/meta/llama-3.1-8b-instruct', credential: true },
  { id: 'huggingface', name: 'Hugging Face', group: 'Cloud providers', description: 'Choose from hosted Hugging Face models.', detail: 'Internet required. You provide a Hugging Face token when needed.', locality: 'cloud', model: 'Qwen/Qwen3-32B', endpoint: 'https://router.huggingface.co/v1', credential: true },
  { id: 'cerebras', name: 'Cerebras', group: 'Cloud providers', description: 'Fast hosted models from Cerebras.', detail: 'Internet required. Add a Cerebras API key to use this provider.', locality: 'cloud', model: 'gpt-oss-120b', credential: true },
  { id: 'ollama', name: 'Ollama', group: 'Local apps', description: 'Use models already running in Ollama.', detail: 'Runs on this computer. Install and start Ollama separately, then choose a local model.', locality: 'local', model: 'auto', endpoint: 'http://127.0.0.1:11434' },
  { id: 'lmstudio', name: 'LM Studio', group: 'Local apps', description: 'Use a model already running in LM Studio.', detail: 'Runs on this computer. Start the local server in LM Studio before testing the connection.', locality: 'local', model: 'auto', endpoint: 'http://127.0.0.1:1234/v1' },
  { id: 'custom', name: 'Custom OpenAI-compatible', group: 'Advanced', description: 'Connect a compatible endpoint you control.', detail: 'For advanced users who need a custom URL, model, and authentication method.', locality: 'cloud', model: '', credential: true }
]

const GROUPS: ProviderDefinition['group'][] = ['Built in', 'Free-friendly cloud', 'Cloud providers', 'Local apps', 'Advanced']
const MODEL_LIST_TTL_MS = 10 * 60 * 1000

type SavedSetting = { value: string | null; available: boolean }

function readSavedModel(providerId: string): SavedSetting {
  try {
    return { value: window.localStorage.getItem(`clipgauge.provider-model.${providerId}`), available: true }
  } catch {
    return { value: null, available: false }
  }
}

function writeSavedModel(providerId: string, model: string): boolean {
  try {
    window.localStorage.setItem(`clipgauge.provider-model.${providerId}`, model)
    return true
  } catch {
    return false
  }
}

function readSavedEndpoint(providerId: string): SavedSetting {
  try {
    return { value: window.localStorage.getItem(`clipgauge.provider-endpoint.${providerId}`), available: true }
  } catch {
    return { value: null, available: false }
  }
}

function writeSavedEndpoint(providerId: string, endpoint: string): boolean {
  try {
    window.localStorage.setItem(`clipgauge.provider-endpoint.${providerId}`, endpoint)
    return true
  } catch {
    return false
  }
}

function modelLabel(model: string) {
  return model === 'openrouter/free' ? 'Auto Free' : model
}

function capabilityLabel(value: unknown) {
  if (value === true) return 'Supported'
  if (value === false) return 'Not supported'
  return 'Unknown'
}

function contextLabel(value: unknown) {
  if (typeof value !== 'number' || value <= 0) return 'Not published'
  return `${String(Math.trunc(value)).replace(/\B(?=(\d{3})+(?!\d))/g, ',')} tokens`
}

function priceLabel(price: Record<string, unknown> | undefined) {
  if (!price || Object.keys(price).length === 0) return 'Not published'
  return Object.entries(price).map(([key, value]) => `${key}: ${String(value)}`).join(' · ')
}

function typedFailureLabel(code: string | undefined): string | null {
  switch (code) {
    case 'STRUCTURED_OUTPUT_INVALID': return 'Structured output issue'
    case 'CONTEXT_TOO_LARGE': return 'Request too large'
    case 'VISION_UNSUPPORTED': return 'Vision unsupported'
    case 'PROVIDER_RESPONSE_INVALID': return 'Invalid provider response'
    case 'INTERNAL_PROVIDER_ERROR': return 'Provider error'
    default: return null
  }
}

function isModelCompatibility(value: unknown): value is ProviderModel['compatibility'] {
  return value === 'FULL' || value === 'TEXT-ONLY' || value === 'NO STRUCTURED OUTPUT' || value === 'UNSUPPORTED'
}

function normalizeProviderModels(value: unknown): ProviderModel[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((model) => {
    if (typeof model === 'string' && model.trim()) return [{ id: model, compatibility: 'TEXT-ONLY' as const }]
    if (!model || typeof model !== 'object' || Array.isArray(model)) return []
    const candidate = model as Record<string, unknown>
    if (typeof candidate.id !== 'string' || !candidate.id.trim() || !isModelCompatibility(candidate.compatibility)) return []
    return [{ ...candidate, id: candidate.id, compatibility: candidate.compatibility } as unknown as ProviderModel]
  })
}

function statusFor(provider: ProviderDefinition, setup: SetupState | null, test: ProviderTestResult | null, localReady: boolean, testing = false): { label: string; tone: 'ready' | 'neutral' | 'warning' | 'error' } {
  if (testing) return { label: 'Testing', tone: 'warning' }
  if (test?.state === 'PASS') return { label: 'Connected', tone: 'ready' }
  if (test?.code === 'RATE_LIMITED' || test?.code === 'QUOTA_EXHAUSTED') return { label: 'Rate limited', tone: 'warning' }
  if (test?.code === 'BILLING_REQUIRED') return { label: 'Billing required', tone: 'warning' }
  if (test?.code === 'MODEL_NOT_FOUND' || test?.code === 'MODEL_UNSUPPORTED') return { label: 'Model unsupported', tone: 'error' }
  if (test?.code === 'PROVIDER_UNAVAILABLE' || test?.code === 'TIMEOUT' || test?.code === 'NETWORK_FAILED') return { label: 'Unavailable', tone: 'error' }
  if (test?.code === 'AUTH_INVALID') return { label: 'Credential rejected', tone: 'error' }
  const typedFailure = typedFailureLabel(test?.code)
  if (typedFailure) return { label: typedFailure, tone: 'error' }
  if (test?.state === 'FAIL') return { label: 'Connection failed', tone: 'error' }
  if (provider.id === 'clipgauge-local') return localReady ? { label: 'Ready', tone: 'ready' } : { label: 'Setup required', tone: 'warning' }
  if (provider.locality === 'local') return { label: 'Not detected', tone: 'neutral' }
  const saved = provider.id === 'gemini' ? setup?.has_gemini_key : Boolean(setup?.provider_keys?.[provider.id] ?? setup?.provider_keys?.[`preset-${provider.id}`])
  return saved ? { label: 'Credential saved', tone: 'neutral' } : { label: 'Not configured', tone: 'neutral' }
}

export default function ProviderCenter({ selectedProvider, onSelectProvider, onBack, onOpenSetup }: Props) {
  const [setup, setSetup] = useState<SetupState | null>(null)
  const [inventory, setInventory] = useState<LocalSetupInventory | null>(() => readCachedSetupInventory())
  const [activeId, setActiveId] = useState(selectedProvider)
  const [credential, setCredential] = useState('')
  const [saved, setSaved] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null)
  const [customModel, setCustomModel] = useState('')
  const [customEndpoint, setCustomEndpoint] = useState('')
  const [models, setModels] = useState<Record<string, ProviderModel[]>>({})
  const [modelsLoading, setModelsLoading] = useState(false)
  const [modelsMessage, setModelsMessage] = useState<string | null>(null)
  const [storageMessage, setStorageMessage] = useState<string | null>(null)
  const [selectedModels, setSelectedModels] = useState<Record<string, string>>({})
  const [modelsFetchedAt, setModelsFetchedAt] = useState<Record<string, number>>({})
  const modelRequestRef = useRef(0)
  const connectionRequestRef = useRef(0)
  const credentialRequestRef = useRef(0)
  const selectedProviderPropRef = useRef(selectedProvider)

  useEffect(() => {
    let active = true
    api.setupState().then((value) => { if (active) setSetup(isSetupState(value) ? value : null) }).catch(() => { if (active) setSetup(null) })
    api.setupInventory().then((value) => {
      if (!active || !isProviderInventory(value)) return
      setInventory(value as LocalSetupInventory)
      writeCachedSetupInventory(value as LocalSetupInventory)
    }).catch(() => undefined)
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (selectedProviderPropRef.current === selectedProvider) return
    selectedProviderPropRef.current = selectedProvider
    modelRequestRef.current += 1
    connectionRequestRef.current += 1
    credentialRequestRef.current += 1
    setActiveId(selectedProvider)
    setCredential('')
    setSaved(false)
    setTestResult(null)
    setTesting(false)
    setModelsMessage(null)
    setStorageMessage(null)
    setModelsLoading(false)
  }, [selectedProvider])

  useEffect(() => {
    const stored = readSavedModel(activeId)
    const endpoint = readSavedEndpoint(activeId)
    if (!stored.available || !endpoint.available) {
      setStorageMessage('Saved provider settings could not be read. Restore browser storage before restarting.')
    }
    if (activeId === 'custom' || activeId === 'cloudflare') {
      if (stored.value && activeId === 'custom') setCustomModel(stored.value)
      setCustomEndpoint(endpoint.value ?? '')
    } else if (stored.value) setSelectedModels((current) => ({ ...current, [activeId]: stored.value as string }))
  }, [activeId])

  const active = useMemo(() => PROVIDERS.find((provider) => provider.id === activeId) ?? PROVIDERS[0], [activeId])
  const localReady = Boolean(inventory?.local_ai?.runtime_ready && inventory?.local_ai?.model_ready)
  const localModelId = selectedLocalModel(inventory)
  const status = statusFor(active, setup, testResult, localReady, testing)
  const savedFromSetup = active.id === 'gemini' ? Boolean(setup?.has_gemini_key) : Boolean(setup?.provider_keys?.[active.id] ?? setup?.provider_keys?.[`preset-${active.id}`])
  const hasSavedCredential = active.credential && (saved || savedFromSetup)
  const selectedModel = active.id === 'custom' ? customModel : active.id === 'clipgauge-local' ? localModelId ?? '' : selectedModels[active.id] ?? active.model
  const discoveredModels = models[active.id] ?? []
  const modelListExpired = Boolean(modelsFetchedAt[active.id] && Date.now() - modelsFetchedAt[active.id] > MODEL_LIST_TTL_MS)
  const providerManagedAuto = active.id === 'openrouter' && selectedModel === 'openrouter/free'
  const selectedModelUnavailable = discoveredModels.length > 0 && !modelListExpired && !providerManagedAuto && !discoveredModels.some((model) => model.id === selectedModel)
  const selectedModelDescriptor = discoveredModels.find((model) => model.id === selectedModel)
  const selectedModelBlocked = selectedModelDescriptor?.compatibility === 'UNSUPPORTED' || selectedModelDescriptor?.compatibility === 'NO STRUCTURED OUTPUT' || selectedModelDescriptor?.available === false
  const endpointMissing = active.id === 'cloudflare' && !customEndpoint.trim()


  function selectProvider(id: string) {
    modelRequestRef.current += 1
    connectionRequestRef.current += 1
    credentialRequestRef.current += 1
    setActiveId(id)
    onSelectProvider(id)
    setCredential('')
    setSaved(false)
    setTestResult(null)
    setTesting(false)
    setModelsMessage(null)
    setStorageMessage(null)
    setModelsLoading(false)
  }

  function selectModel(model: string) {
    setSelectedModels((current) => ({ ...current, [active.id]: model }))
    setStorageMessage(writeSavedModel(active.id, model) ? null : 'Model selection could not be saved. Restore browser storage before restarting.')
    setTestResult(null)
  }

  async function refreshModels() {
    const requestId = ++modelRequestRef.current
    const providerId = active.id
    setModelsLoading(true)
    setModelsMessage(null)
    try {
      const result = await api.listProviderModels(providerId, selectedModel || undefined, providerId === 'custom' || providerId === 'cloudflare' ? customEndpoint : active.endpoint, active.credential ? 'bearer' : 'none')
      if (requestId !== modelRequestRef.current || providerId !== active.id) return
      if (!isProviderModelsResult(result)) throw new Error('Provider returned an invalid model list. Retry the refresh.')
      const next = normalizeProviderModels(result.models)
      setModels((current) => ({ ...current, [providerId]: next }))
      setModelsFetchedAt((current) => ({ ...current, [providerId]: Date.now() }))
      setModelsMessage(result.message ?? (next.length ? 'Models refreshed.' : 'No usable model list returned. Manual model entry remains available.'))
    } catch (error) {
      if (requestId !== modelRequestRef.current || providerId !== active.id) return
      setModelsMessage(friendlyErrorMessage(error, 'Model list unavailable. Retry the refresh.'))
    } finally {
      if (requestId === modelRequestRef.current && providerId === active.id) setModelsLoading(false)
    }
  }

  async function saveCredential() {
    const provider = active
    const providerId = provider.id
    const requestId = ++credentialRequestRef.current
    if (!credential.trim() || !provider.credential) return
    try {
      const stored = providerId === 'gemini'
        ? await api.saveGeminiKey(credential.trim())
        : await api.saveProviderKey(`preset-${providerId}`, credential.trim())
      if (stored !== true) throw new Error('The credential was not saved. Retry and check the operating-system vault.')
      if (requestId !== credentialRequestRef.current || providerId !== active.id) return
      setCredential('')
      setSaved(true)
      setTestResult(null)
      setSetup((current) => current ? { ...current, provider_keys: { ...(current.provider_keys ?? {}), [providerId]: providerId === 'gemini' ? Boolean(current.provider_keys?.[providerId]) : true }, has_gemini_key: providerId === 'gemini' ? true : current.has_gemini_key } : current)
    } catch (error) {
      if (requestId === credentialRequestRef.current && providerId === active.id) setTestResult({ state: 'FAIL', provider: providerId, message: friendlyErrorMessage(error, 'The credential could not be saved. Retry the action.') })
    }
  }

  async function removeCredential() {
    const provider = active
    const providerId = provider.id
    const requestId = ++credentialRequestRef.current
    if (!provider.credential || !hasSavedCredential) return
    try {
      if (!(await confirm(`Remove the saved ${active.name} credential from this computer? This removes only ClipGauge’s saved credential and does not revoke the provider key.`))) return
      if (requestId !== credentialRequestRef.current || providerId !== active.id) return
      const removed = providerId === 'gemini'
        ? await api.removeGeminiKey()
        : await api.removeProviderKey(`preset-${providerId}`)
      if (removed !== true) throw new Error('The credential could not be removed. Check the operating-system vault and retry.')
      if (requestId !== credentialRequestRef.current || providerId !== active.id) return
      setSaved(false)
      setCredential('')
      setTestResult(null)
      setSetup((current) => current ? { ...current, has_gemini_key: providerId === 'gemini' ? false : current.has_gemini_key, provider_keys: { ...(current.provider_keys ?? {}), [providerId]: false, [`preset-${providerId}`]: false } } : current)
    } catch (error) {
      if (requestId === credentialRequestRef.current && providerId === active.id) setTestResult({ state: 'FAIL', provider: providerId, message: friendlyErrorMessage(error, 'The credential could not be removed. Retry the action.') })
    }
  }

  async function testConnection() {
    const requestId = ++connectionRequestRef.current
    const providerId = active.id
    setTesting(true)
    setTestResult(null)
    try {
      const model = selectedModel
      const endpoint = active.id === 'custom' || active.id === 'cloudflare' ? customEndpoint : active.endpoint
      const result = await api.testConnection(active.id, model || undefined, endpoint || undefined, active.credential ? 'bearer' : 'none')
      if (requestId !== connectionRequestRef.current || providerId !== active.id) return
      if (!isProviderTestResult(result)) throw new Error('Provider returned an invalid connection result. Refresh models and retry.')
      if (Array.isArray(result.models) && result.models.length) {
        const next = normalizeProviderModels(result.models)
        setModels((current) => ({ ...current, [active.id]: next }))
        setModelsFetchedAt((current) => ({ ...current, [active.id]: Date.now() }))
      }
      setTestResult(result)
    } catch (error) {
      if (requestId === connectionRequestRef.current && providerId === active.id) setTestResult({ state: 'FAIL', provider: active.id, message: friendlyErrorMessage(error, 'Connection failed. Retry the selected model.') })
    } finally {
      if (requestId === connectionRequestRef.current && providerId === active.id) setTesting(false)
    }
  }

  return (
    <div className="page-frame providers-page">
      <header className="page-header">
        <div><p className="section-eyebrow">AI Providers</p><h1>Choose where scoring runs.</h1><p className="page-lede">Start local, use a free cloud route, or connect a provider you already trust. You can change this for each new video.</p></div>
        <button type="button" className="button button-quiet" onClick={onBack}>Back to Create</button>
      </header>
      <div className="providers-layout">
        <section className="provider-list" aria-label="Available AI providers">
          {GROUPS.map((group) => <div className="provider-group" key={group}>
            <div className="provider-group-heading"><span>{group}</span>{group === 'Built in' && <span className="group-note">No account needed</span>}</div>
            {PROVIDERS.filter((provider) => provider.group === group).map((provider) => {
              const providerStatus = statusFor(provider, setup, provider.id === activeId ? testResult : null, localReady, provider.id === activeId && testing)
              const Icon = provider.locality === 'local' ? Cpu : Cloud
              return <button type="button" className={`provider-card ${activeId === provider.id ? 'is-selected' : ''}`} key={provider.id} onClick={() => selectProvider(provider.id)} aria-pressed={activeId === provider.id}>
                <span className="provider-icon"><Icon size={18} aria-hidden="true" /></span>
                <span className="provider-card-copy"><strong>{provider.name}</strong><small>{provider.description}</small></span>
                <span className={`provider-status tone-${providerStatus.tone}`}><span className="status-dot" aria-hidden="true" />{providerStatus.label}</span>
                <ChevronRight size={16} aria-hidden="true" className="provider-chevron" />
              </button>
            })}
          </div>)}
        </section>
        <aside className="provider-detail" aria-labelledby="provider-detail-title">
          <div className="detail-topline"><span className={`status-pill tone-${status.tone}`}><span className="status-dot" aria-hidden="true" />{status.label}</span>{active.badge && <span className="soft-badge">{active.badge}</span>}</div>
          <p className="section-eyebrow">Selected provider</p>
          <h2 id="provider-detail-title">{active.name}</h2>
          <p className="detail-description">{hasSavedCredential ? 'API key saved in your operating-system credential vault.' : active.id === 'openrouter' ? 'Auto Free chooses among currently available compatible free models. Results may vary between runs.' : active.detail}</p>
          <div className="provider-facts">
            <div><span>Where it runs</span><strong>{active.locality === 'local' ? 'On this computer' : 'Over the internet'}</strong></div>
            <div><span>Privacy</span><strong>{active.locality === 'local' ? 'Video stays local' : 'You choose when to send a video'}</strong></div>
          </div>
          {active.credential && active.id !== 'custom' && <div className="field-stack"><label htmlFor="provider-credential"><KeyRound size={15} aria-hidden="true" /> API key</label><div className="input-with-action"><input id="provider-credential" type="password" value={credential} onChange={(event) => setCredential(event.target.value)} placeholder="Stored in your OS vault" autoComplete="off" /><button type="button" className="button button-secondary" onClick={saveCredential} disabled={!credential.trim()}><Save size={15} aria-hidden="true" />{saved ? 'Saved' : 'Save'}</button>{hasSavedCredential && <button type="button" className="button button-quiet" onClick={removeCredential}>Remove</button>}</div><p className="field-help">A saved key is not the same as a working connection. Use Test connection below.</p></div>}
          {active.id !== 'custom' && <div className="field-stack"><label htmlFor="provider-model">Model</label><select id="provider-model" aria-label="Model" value={selectedModel} onChange={(event) => selectModel(event.target.value)}><option value={selectedModel}>{selectedModel ? `${modelLabel(selectedModel)}${selectedModelDescriptor ? ` — ${selectedModelDescriptor.compatibility}` : ''}` : 'Choose a model'}</option>{discoveredModels.filter((model) => model.id !== selectedModel).map((model) => <option value={model.id} key={model.id} disabled={model.compatibility === 'UNSUPPORTED' || model.compatibility === 'NO STRUCTURED OUTPUT' || model.available === false}>{modelLabel(model.id)} — {model.compatibility}</option>)}</select><div className="detail-actions model-actions"><button type="button" className="button button-secondary" onClick={() => void refreshModels()} disabled={modelsLoading}>{modelsLoading ? 'Refreshing models…' : 'Refresh models'}</button>{modelListExpired && <span className="field-help" role="alert">Model list expired. Refresh before testing this provider.</span>}{providerManagedAuto && !selectedModelDescriptor && <span className="field-help" role="status">Auto Free selects the current compatible route during connection and scoring.</span>}{selectedModelUnavailable && <span className="field-help" role="alert">Selected model unavailable. Choose a listed model explicitly.</span>}{selectedModelBlocked && <span className="field-help" role="alert">Selected model cannot safely score. Choose a compatible listed model.</span>}</div>{modelsMessage && <p className="field-help" role="status">{modelsMessage}</p>}</div>}
          {selectedModelDescriptor && <section className="model-contract" aria-labelledby="model-contract-title"><div className="model-contract-heading"><h3 id="model-contract-title">Model capability contract</h3>{selectedModelDescriptor.deprecated && <span className="soft-badge">Deprecated</span>}</div><div className="contract-grid"><div><span>Compatibility</span><strong>{selectedModelDescriptor.compatibility}</strong></div><div><span>Availability</span><strong>{selectedModelDescriptor.available === false ? 'Unavailable' : selectedModelDescriptor.available === true ? 'Available' : 'Unknown'}</strong></div><div><span>Text input</span><strong>{capabilityLabel(selectedModelDescriptor.capabilities?.text)}</strong></div><div><span>Vision / image input</span><strong>{capabilityLabel(selectedModelDescriptor.capabilities?.vision)}</strong></div><div><span>Structured JSON</span><strong>{capabilityLabel(selectedModelDescriptor.capabilities?.structured_json)}</strong></div><div><span>JSON Schema</span><strong>{capabilityLabel(selectedModelDescriptor.capabilities?.json_schema)}</strong></div><div><span>Context window</span><strong>{contextLabel(selectedModelDescriptor.capabilities?.context_window)}</strong></div><div><span>Runs</span><strong>{selectedModelDescriptor.local ? 'Locally' : 'In the cloud'}</strong></div><div><span>Provider pricing</span><strong>{priceLabel(selectedModelDescriptor.price)}</strong></div></div>{selectedModelDescriptor.capabilities?.vision === false && <p className="field-help" role="alert">Visual scoring will use deterministic/local fallback for this model.</p>}</section>}
          {active.id === 'custom' && <div className="custom-fields"><div className="field-stack"><label htmlFor="custom-endpoint"><Network size={15} aria-hidden="true" /> Endpoint</label><input id="custom-endpoint" value={customEndpoint} onChange={(event) => { setCustomEndpoint(event.target.value); setStorageMessage(writeSavedEndpoint('custom', event.target.value) ? null : 'Endpoint could not be saved. Restore browser storage before restarting.') }} placeholder="https://your-endpoint.example/v1" /></div><div className="field-stack"><label htmlFor="custom-model">Model</label><input id="custom-model" value={customModel} onChange={(event) => { setCustomModel(event.target.value); setStorageMessage(writeSavedModel('custom', event.target.value) ? null : 'Model selection could not be saved. Restore browser storage before restarting.') }} placeholder="Model name" /></div><div className="field-stack"><label htmlFor="custom-credential">Credential</label><input id="custom-credential" type="password" value={credential} onChange={(event) => setCredential(event.target.value)} placeholder="Stored in your OS vault" autoComplete="off" /><button type="button" className="button button-secondary" onClick={saveCredential} disabled={!credential.trim()}><Save size={15} aria-hidden="true" />Save credential</button>{hasSavedCredential && <button type="button" className="button button-quiet" onClick={removeCredential}>Remove credential</button>}</div></div>}
          {active.id === 'cloudflare' && <div className="field-stack"><label htmlFor="cloudflare-endpoint"><Network size={15} aria-hidden="true" /> Endpoint</label><input id="cloudflare-endpoint" value={customEndpoint} onChange={(event) => { setCustomEndpoint(event.target.value); setStorageMessage(writeSavedEndpoint('cloudflare', event.target.value) ? null : 'Endpoint could not be saved. Restore browser storage before restarting.') }} placeholder="https://api.cloudflare.com/client/v4/accounts/..." /><p className="field-help">Use an OpenAI-compatible Cloudflare route for this account.</p>{endpointMissing && <p className="field-help" role="alert">Enter a Cloudflare endpoint before testing this provider.</p>}</div>}
          <div className="detail-actions">{active.id === 'clipgauge-local' && !localReady ? <button type="button" className="button button-primary" onClick={() => { if (onOpenSetup) onOpenSetup(); else onBack() }}>Set up local AI<ChevronRight size={16} aria-hidden="true" /></button> : <button type="button" className="button button-primary" onClick={testConnection} disabled={testing || endpointMissing || modelListExpired || selectedModelUnavailable || selectedModelBlocked}>{testing ? 'Testing…' : 'Test connection'}<ChevronRight size={16} aria-hidden="true" /></button>}<button type="button" className="button button-secondary" onClick={() => { onSelectProvider(active.id); onBack() }}>Use for next clip</button></div>
          {testResult && <div className={`result-callout result-${testResult.state.toLowerCase()}`} role="status"><span className="result-icon">{testResult.state === 'PASS' ? <Check size={16} aria-hidden="true" /> : testResult.state === 'FAIL' ? <CircleAlert size={16} aria-hidden="true" /> : <WifiOff size={16} aria-hidden="true" />}</span><span><strong>{testResult.state === 'PASS' ? 'Connection ready' : testResult.state === 'FAIL' ? 'Connection needs attention' : 'Connection has limits'}</strong><small>{testResult.message ?? 'The provider returned no additional details.'}</small></span></div>}
          {storageMessage && <p className="field-help" role="alert">{storageMessage}</p>}
          <details className="advanced-disclosure"><summary><RotateCcw size={15} aria-hidden="true" /> Advanced settings</summary><div className="technical-grid"><span>Model ID</span><code>{active.id === 'custom' ? customModel || 'not set' : active.id === 'clipgauge-local' ? localModelId || 'selected model unavailable' : selectedModel || 'auto'}</code><span>Endpoint</span><code>{active.id === 'custom' ? customEndpoint || 'not set' : active.endpoint || 'provider-managed'}</code><span>Auth</span><code>{active.credential ? 'credential in OS vault' : 'none'}</code></div><p>These values are for troubleshooting and advanced provider configuration. Normal creator actions use the friendly provider name above.</p></details>
          <div className="privacy-note"><ShieldCheck size={16} aria-hidden="true" /><span><strong>Credential privacy</strong><small>Keys are saved in the operating-system vault and are not written into project files.</small></span></div>
          {active.id === 'openrouter' && <a className="text-link" href="https://openrouter.ai/" target="_blank" rel="noreferrer">Learn about OpenRouter <ExternalLink size={14} aria-hidden="true" /></a>}
        </aside>
      </div>
    </div>
  )
}

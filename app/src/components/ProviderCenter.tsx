import { useEffect, useMemo, useState } from 'react'
import { Check, ChevronRight, CircleAlert, Cloud, Cpu, ExternalLink, KeyRound, Network, RotateCcw, Save, ShieldCheck, WifiOff } from 'lucide-react'
import { api } from '../api'
import type { ProviderTestResult, SetupState } from '../types'

interface Props {
  selectedProvider: string
  onSelectProvider: (provider: string) => void
  onBack: () => void
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
  { id: 'clipgauge-local', name: 'ClipGauge Local', group: 'Built in', description: 'Runs scoring on this computer.', detail: 'No API key. Your video stays on this computer while the local engine is ready.', locality: 'local', model: 'clipgauge-local/qwen3-4b-q4_k_m', endpoint: 'http://127.0.0.1:8080/v1', badge: 'Recommended for privacy' },
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

function statusFor(provider: ProviderDefinition, setup: SetupState | null, test: ProviderTestResult | null): { label: string; tone: 'ready' | 'neutral' | 'warning' | 'error' } {
  if (test?.state === 'PASS') return { label: 'Connected', tone: 'ready' }
  if (test?.state === 'FAIL') return { label: 'Unavailable', tone: 'error' }
  if (provider.id === 'clipgauge-local') return { label: 'Ready when setup is complete', tone: 'ready' }
  if (provider.locality === 'local') return { label: 'Not detected', tone: 'neutral' }
  const saved = provider.id === 'gemini' ? setup?.has_gemini_key : setup?.provider_keys?.[`preset-${provider.id}`]
  return saved ? { label: 'Ready with limitations', tone: 'warning' } : { label: 'Not configured', tone: 'neutral' }
}

export default function ProviderCenter({ selectedProvider, onSelectProvider, onBack }: Props) {
  const [setup, setSetup] = useState<SetupState | null>(null)
  const [activeId, setActiveId] = useState(selectedProvider)
  const [credential, setCredential] = useState('')
  const [saved, setSaved] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null)
  const [customModel, setCustomModel] = useState('')
  const [customEndpoint, setCustomEndpoint] = useState('')

  useEffect(() => {
    api.setupState().then((value) => setSetup(value)).catch(() => setSetup(null))
  }, [])

  const active = useMemo(() => PROVIDERS.find((provider) => provider.id === activeId) ?? PROVIDERS[0], [activeId])
  const status = statusFor(active, setup, testResult)

  function selectProvider(id: string) {
    setActiveId(id)
    onSelectProvider(id)
    setCredential('')
    setSaved(false)
    setTestResult(null)
  }

  async function saveCredential() {
    if (!credential.trim() || !active.credential) return
    try {
      await api.saveProviderKey(`preset-${active.id}`, credential.trim())
      setCredential('')
      setSaved(true)
      setSetup((current) => current ? { ...current, provider_keys: { ...(current.provider_keys ?? {}), [`preset-${active.id}`]: true }, has_gemini_key: active.id === 'gemini' ? true : current.has_gemini_key } : current)
    } catch (error) {
      setTestResult({ state: 'FAIL', provider: active.id, message: String(error) })
    }
  }

  async function testConnection() {
    setTesting(true)
    setTestResult(null)
    try {
      const model = active.id === 'custom' ? customModel : active.model
      const endpoint = active.id === 'custom' ? customEndpoint : active.endpoint
      setTestResult(await api.testConnection(active.id, model || undefined, endpoint || undefined, active.credential ? 'bearer' : 'none'))
    } catch (error) {
      setTestResult({ state: 'FAIL', provider: active.id, message: String(error) })
    } finally {
      setTesting(false)
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
              const providerStatus = statusFor(provider, setup, provider.id === activeId ? testResult : null)
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
          <p className="detail-description">{active.detail}</p>
          <div className="provider-facts">
            <div><span>Where it runs</span><strong>{active.locality === 'local' ? 'On this computer' : 'Over the internet'}</strong></div>
            <div><span>Privacy</span><strong>{active.locality === 'local' ? 'Video stays local' : 'You choose when to send a video'}</strong></div>
          </div>
          {active.credential && active.id !== 'custom' && <div className="field-stack"><label htmlFor="provider-credential"><KeyRound size={15} aria-hidden="true" /> API key</label><div className="input-with-action"><input id="provider-credential" type="password" value={credential} onChange={(event) => setCredential(event.target.value)} placeholder="Stored in your OS vault" autoComplete="off" /><button type="button" className="button button-secondary" onClick={saveCredential} disabled={!credential.trim()}><Save size={15} aria-hidden="true" />{saved ? 'Saved' : 'Save'}</button></div><p className="field-help">A saved key is not the same as a working connection. Use Test connection below.</p></div>}
          {active.id === 'custom' && <div className="custom-fields"><div className="field-stack"><label htmlFor="custom-endpoint"><Network size={15} aria-hidden="true" /> Endpoint</label><input id="custom-endpoint" value={customEndpoint} onChange={(event) => setCustomEndpoint(event.target.value)} placeholder="https://your-endpoint.example/v1" /></div><div className="field-stack"><label htmlFor="custom-model">Model</label><input id="custom-model" value={customModel} onChange={(event) => setCustomModel(event.target.value)} placeholder="Model name" /></div><div className="field-stack"><label htmlFor="custom-credential">Credential</label><input id="custom-credential" type="password" value={credential} onChange={(event) => setCredential(event.target.value)} placeholder="Stored in your OS vault" autoComplete="off" /><button type="button" className="button button-secondary" onClick={saveCredential} disabled={!credential.trim()}><Save size={15} aria-hidden="true" />Save credential</button></div></div>}
          <div className="detail-actions"><button type="button" className="button button-primary" onClick={testConnection} disabled={testing}>{testing ? 'Testing…' : 'Test connection'}<ChevronRight size={16} aria-hidden="true" /></button><button type="button" className="button button-secondary" onClick={() => { onSelectProvider(active.id); onBack() }}>Use for next clip</button></div>
          {testResult && <div className={`result-callout result-${testResult.state.toLowerCase()}`} role="status"><span className="result-icon">{testResult.state === 'PASS' ? <Check size={16} aria-hidden="true" /> : testResult.state === 'FAIL' ? <CircleAlert size={16} aria-hidden="true" /> : <WifiOff size={16} aria-hidden="true" />}</span><span><strong>{testResult.state === 'PASS' ? 'Connection ready' : testResult.state === 'FAIL' ? 'Connection needs attention' : 'Connection has limits'}</strong><small>{testResult.message ?? 'The provider returned no additional details.'}</small></span></div>}
          <details className="advanced-disclosure"><summary><RotateCcw size={15} aria-hidden="true" /> Advanced settings</summary><div className="technical-grid"><span>Model ID</span><code>{active.id === 'custom' ? customModel || 'not set' : active.model || 'auto'}</code><span>Endpoint</span><code>{active.id === 'custom' ? customEndpoint || 'not set' : active.endpoint || 'provider-managed'}</code><span>Auth</span><code>{active.credential ? 'credential in OS vault' : 'none'}</code></div><p>These values are for troubleshooting and advanced provider configuration. Normal creator actions use the friendly provider name above.</p></details>
          <div className="privacy-note"><ShieldCheck size={16} aria-hidden="true" /><span><strong>Credential privacy</strong><small>Keys are saved in the operating-system vault and are not written into project files.</small></span></div>
          {active.id === 'openrouter' && <a className="text-link" href="https://openrouter.ai/" target="_blank" rel="noreferrer">Learn about OpenRouter <ExternalLink size={14} aria-hidden="true" /></a>}
        </aside>
      </div>
    </div>
  )
}

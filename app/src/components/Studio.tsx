import { useEffect, useState } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import { api } from '../api'
import type { JobSummary, PrivacySummary, ProviderTestResult, StageProgress } from '../types'
import KeyModal from './KeyModal'

const STAGE_ORDER = [
  'ingest', 'asr', 'diarize', 'events', 'candidates', 'score', 'camera', 'render'
]

const STAGE_LABELS: Record<string, string> = {
  ingest: 'Preparing video',
  asr: 'Transcribing speech',
  diarize: 'Identifying speakers',
  events: 'Understanding audio',
  candidates: 'Finding strong moments',
  score: 'Scoring clips',
  camera: 'Smart reframing',
  render: 'Creating clips'
}

const CAPTION_PRESETS = ['classic', 'beast', 'hormozi', 'minimal', 'karaoke-pop']
const PROVIDER_DEFAULTS: Record<string, { model: string; endpoint?: string; locality: string }> = {
  gemini: { model: 'gemini-flash-latest', locality: 'cloud' },
  ollama: { model: 'auto', endpoint: 'http://127.0.0.1:11434', locality: 'local' },
  lmstudio: { model: 'auto', endpoint: 'http://127.0.0.1:1234/v1', locality: 'local' },
  openrouter: { model: 'openrouter/free', locality: 'cloud' },
  groq: { model: 'openai/gpt-oss-20b', locality: 'cloud' },
  cloudflare: { model: '@cf/meta/llama-3.1-8b-instruct', locality: 'cloud' },
  huggingface: { model: 'Qwen/Qwen3-32B', locality: 'cloud' },
  cerebras: { model: 'gpt-oss-120b', locality: 'cloud' },
  custom: { model: '', locality: 'cloud' }
}

interface Props {
  jobs: JobSummary[]
  running: boolean
  cancelling: boolean
  startedAt: number | null
  stages: Record<string, StageProgress>
  error: string | null
  notice: string | null
  onRun: (source: string, provider: string, captions: string, model?: string, endpoint?: string, auth?: string, secretHeader?: string) => void
  onCancel: () => void
  onOpenLoop: () => void
  onOpenAbout: () => void
  onOpenJob: (id: string) => void
  onResume: (id: string) => void
}

export default function Studio({ jobs, running, cancelling, startedAt, stages, error, notice, onRun, onCancel, onOpenLoop, onOpenAbout, onOpenJob, onResume }: Props) {
  const [source, setSource] = useState('')
  const [provider, setProvider] = useState('gemini')
  const [model, setModel] = useState(PROVIDER_DEFAULTS.gemini.model)
  const [endpoint, setEndpoint] = useState(PROVIDER_DEFAULTS.gemini.endpoint ?? '')
  const [providerKey, setProviderKey] = useState('')
  const [auth, setAuth] = useState(provider === 'custom' ? 'none' : 'bearer')
  const [secretHeader, setSecretHeader] = useState('x-api-key')
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null)
  const [captions, setCaptions] = useState('classic')
  const [showKey, setShowKey] = useState(false)
  const [privacy, setPrivacy] = useState<PrivacySummary | null>(null)
  const [supportMessage, setSupportMessage] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!startedAt) return
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [startedAt])

  const elapsed = startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : 0
  const elapsedLabel = `${String(Math.floor(elapsed / 60)).padStart(2, '0')}:${String(elapsed % 60).padStart(2, '0')}`

  async function showPrivacy() {
    try {
      setPrivacy(await api.privacySummary(provider, model || undefined, endpoint || undefined))
    } catch (error) {
      setSupportMessage(`Privacy summary unavailable: ${String(error)}`)
    }
  }

  function chooseProvider(next: string) {
    setProvider(next)
    const defaults = PROVIDER_DEFAULTS[next] ?? PROVIDER_DEFAULTS.custom
    setModel(defaults.model)
    setEndpoint(defaults.endpoint ?? '')
    setAuth(next === 'custom' ? 'none' : 'bearer')
    setSecretHeader('x-api-key')
    setProviderKey('')
    setTestResult(null)
  }

  async function testProvider() {
    setTestResult(null)
    try {
      setTestResult(await api.testConnection(provider, model || undefined, endpoint || undefined, auth, auth === 'custom_secret_header' ? secretHeader : undefined))
    } catch (error) {
      setTestResult({ state: 'FAIL', provider, message: String(error) })
    }
  }

  async function saveProviderKey() {
    if (!providerKey.trim() || provider === 'ollama') return
    try {
      await api.saveProviderKey(`preset-${provider}`, providerKey.trim())
      setProviderKey('')
      setSupportMessage(`Saved ${provider} credential in the operating-system vault.`)
    } catch (error) {
      setSupportMessage(`Could not save provider credential: ${String(error)}`)
    }
  }

  async function makeSupportBundle() {
    setSupportMessage('Generating a redacted support bundle…')
    try {
      const path = await api.generateSupportBundle()
      setSupportMessage(`Support bundle saved locally: ${path}`)
    } catch (error) {
      setSupportMessage(`Support bundle failed: ${String(error)}`)
    }
  }

  async function chooseFile() {
    const selected = await open({
      multiple: false,
      directory: false,
      filters: [{ name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi'] }]
    })
    if (typeof selected === 'string') setSource(selected)
  }

  function dropFile(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault()
    if (running) return
    const file = event.dataTransfer.files[0] as (File & { path?: string }) | undefined
    if (file?.path) setSource(file.path)
  }

  return (
    <div className="studio">
      <div className="grain" />
      {showKey && <KeyModal onClose={() => setShowKey(false)} />}
      {privacy && (
        <div className="modal-scrim" onClick={() => setPrivacy(null)}>
          <div className="modal privacy-modal" role="dialog" aria-modal="true" aria-labelledby="privacy-title" onClick={(event) => event.stopPropagation()}>
            <header className="modal-head">
              <p id="privacy-title" className="audit-kicker">PRIVACY ACTIVITY</p>
              <button className="btn-ghost" onClick={() => setPrivacy(null)}>close</button>
            </header>
            <p className="ig-intro">ClipGauge is local-first, but this mode still performs the network operations listed below. Telemetry is {privacy.telemetry}.</p>
            <p className="audit-label">LEAVES THIS DEVICE</p>
            <ul className="privacy-list">{privacy.llm.network.map((item) => <li key={item}>{item}</li>)}</ul>
            <p className="audit-label">STAYS LOCAL</p>
            <ul className="privacy-list">{privacy.llm.device.map((item) => <li key={item}>{item}</li>)}</ul>
            <p className="ig-message">{privacy.llm.provider}</p>
            <p className="ig-message">{privacy.instagram}</p>
          </div>
        </div>
      )}
      <aside className="rail">
        <header className="rail-brand">
          <span className="rail-logo">ClipGauge</span>
          <span className="rail-sub">local AI video clipper</span>
        </header>
        <div className="rail-jobs">
          <p className="rail-label">SESSIONS</p>
          {jobs.length === 0 && <p className="rail-empty">nothing yet</p>}
          {jobs.map((job) => (
            <button
              key={job.id}
              className={`rail-job ${job.rendered ? '' : 'partial'}`}
              onClick={() => (job.rendered ? onOpenJob(job.id) : onResume(job.id))}
              disabled={running}
              title={job.rendered ? 'open results' : 'resume from checkpoint'}
            >
              <span className={`led ${job.rendered ? 'led-on' : 'led-half'}`} />
              <span className="rail-job-title">{job.title ?? job.id}</span>
              <span className="rail-job-hint">
                {job.rendered ? 'open' : job.resume_safe === false ? 'inspect' : `resume${job.last_stage ? ` · ${job.last_stage}` : ''}`}
              </span>
            </button>
          ))}
        </div>
        <footer className="rail-foot">
                      <button className="btn-ghost" onClick={() => setShowKey(true)}>
            ◈ provider settings
          </button>

          <button className="btn-ghost" onClick={onOpenLoop}>
            ⟳ instagram loop
          </button>
          <button className="btn-ghost" onClick={showPrivacy}>
            privacy activity
          </button>
          <button className="btn-ghost" onClick={makeSupportBundle}>
            support bundle
          </button>
          <button className="btn-ghost" onClick={onOpenAbout}>
            about / licenses
          </button>
        </footer>
      </aside>

      <main className="stage-area">
        <section className="input-block">
          <h1 className="input-heading">
            FEED IT<span className="amber"> AN HOUR.</span>
          </h1>
          <div
            className="input-row source-drop"
            onDragOver={(event) => event.preventDefault()}
            onDrop={dropFile}
            aria-label="Video source drop area"
          >
            <input
              value={source}
              onChange={(e) => setSource(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && source.trim() && !running && onRun(source.trim(), provider, captions, model || undefined, endpoint || undefined, auth, auth === 'custom_secret_header' ? secretHeader : undefined)}
              placeholder="YouTube URL or a path to a video file"
              disabled={running}
            />
            <button
              className="btn-secondary"
              onClick={chooseFile}
              disabled={running}
              aria-label="Choose a local video file"
            >
              CHOOSE FILE
            </button>
            <button
              className="btn-primary"
              onClick={() => onRun(source.trim(), provider, captions, model || undefined, endpoint || undefined, auth, auth === 'custom_secret_header' ? secretHeader : undefined)}
              disabled={running || !source.trim()}
            >
              {running ? 'WORKING' : 'CUT IT'}
            </button>
            {running && (
              <button
                className="btn-ghost"
                onClick={onCancel}
                disabled={cancelling}
                aria-label="Cancel the active job"
              >
                {cancelling ? 'CANCELLING' : 'CANCEL'}
              </button>
            )}
          </div>
          <div className="run-options">
            <div className="opt-group provider-group">
              <span className="opt-label">provider</span>
              {Object.keys(PROVIDER_DEFAULTS).map((kind) => (
                <button
                  key={kind}
                  className={`opt ${provider === kind ? 'opt-on' : ''}`}
                  onClick={() => chooseProvider(kind)}
                  disabled={running}
                  aria-pressed={provider === kind}
                >
                  {kind}
                </button>
              ))}
            </div>
            <div className="provider-config" aria-label="Provider configuration">
              <label className="field-label" htmlFor="provider-model">model</label>
              <input id="provider-model" value={model} onChange={(event) => setModel(event.target.value)} disabled={running} placeholder="model identifier" />
              {(provider === 'custom' || provider === 'cloudflare') && (
                <>
                  <label className="field-label" htmlFor="provider-endpoint">endpoint</label>
                  <input id="provider-endpoint" value={endpoint} onChange={(event) => setEndpoint(event.target.value)} disabled={running} placeholder="https://…/v1" />
                </>
              )}
              {provider === 'custom' && (
                <>
                  <label className="field-label" htmlFor="provider-auth">auth</label>
                  <select id="provider-auth" value={auth} onChange={(event) => setAuth(event.target.value)} disabled={running}>
                    <option value="none">no auth</option>
                    <option value="bearer">bearer</option>
                    <option value="api_key_header">x-api-key</option>
                    <option value="custom_secret_header">custom header</option>
                  </select>
                  {auth === 'custom_secret_header' && <input value={secretHeader} onChange={(event) => setSecretHeader(event.target.value)} disabled={running} placeholder="secret header name" aria-label="Custom secret header name" />}
                </>
              )}
              {provider !== 'ollama' && auth !== 'none' && (
                <>
                  <label className="field-label" htmlFor="provider-key">credential</label>
                  <input id="provider-key" type="password" value={providerKey} onChange={(event) => setProviderKey(event.target.value)} disabled={running} placeholder="stored in OS vault; optional until Test Connection" autoComplete="off" />
                  <button className="btn-secondary" onClick={saveProviderKey} disabled={running || !providerKey.trim()}>SAVE CREDENTIAL</button>
                </>
              )}
              <button className="btn-secondary" onClick={testProvider} disabled={running}>TEST CONNECTION</button>
              {testResult && <p className={`provider-test provider-test-${testResult.state.toLowerCase()}`} role="status">{testResult.state}: {testResult.message ?? `${testResult.provider ?? provider} / ${testResult.model ?? model}`}</p>}
            </div>
            <div className="opt-group">
              <span className="opt-label">captions</span>
              {CAPTION_PRESETS.map((preset) => (
                <button
                  key={preset}
                  className={`opt ${captions === preset ? 'opt-on' : ''}`}
                  onClick={() => setCaptions(preset)}
                  disabled={running}
                >
                  {preset}
                </button>
              ))}
            </div>
          </div>
        </section>

        {(running || Object.keys(stages).length > 0) && (
          <section className="deck" aria-label="Pipeline progress" aria-live="polite">
            {STAGE_ORDER.filter((s) => stages[s] || running).map((name, i) => {
              const st = stages[name]
              const state = !st ? 'idle' : st.fraction >= 1 ? 'done' : 'live'
              const label = st?.displayStage ?? STAGE_LABELS[name] ?? name.replace('_', ' ')
              const eta = st?.etaSeconds != null ? ` · ETA ${Math.max(0, Math.round(st.etaSeconds))}s` : ''
              const accelerator = st?.accelerator ? ` · ${st.accelerator}` : ''
              return (
                <div className={`deck-row ${state}`} key={name} style={{ animationDelay: `${i * 40}ms` }}>
                  <span className="deck-name mono">{label}</span>
                  <div
                    className="deck-bar"
                    role="progressbar"
                    aria-label={`${STAGE_LABELS[name] ?? name} stage progress`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={st && !st.indeterminate && st.fraction >= 0 ? Math.round(Math.min(1, st.fraction) * 100) : undefined}
                  >
                    <div
                      className={`deck-fill ${st && (st.indeterminate || st.fraction < 0) ? 'indeterminate' : ''}`}
                      style={st && !st.indeterminate && st.fraction >= 0 ? { width: `${Math.min(100, st.fraction * 100)}%` } : undefined}
                    />
                  </div>
                  <span className="deck-msg">{st?.operation ?? st?.message ?? ''}{eta}{accelerator}</span>
                </div>
              )
            })}
            <p className="elapsed mono" aria-label={`Elapsed time ${elapsedLabel}`}>
              ELAPSED {elapsedLabel}{stages.render?.message ? ` · ${stages.render.message}` : ''}
            </p>
          </section>
        )}

        {notice && (
          <section className="status-block" role="status">
            <span className="led led-half" />
            {notice}
          </section>
        )}
        {supportMessage && (
          <section className="status-block" role="status">
            <span className="led led-half" />
            {supportMessage}
          </section>
        )}
        {error && (
          <section className="error-block" role="alert">
            <span className="led led-err" />
            {error}
          </section>
        )}
      </main>
    </div>
  )
}

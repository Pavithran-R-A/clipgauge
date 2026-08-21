import { useEffect, useState } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import { listen } from '@tauri-apps/api/event'
import { api } from '../api'
import type { JobSummary, LocalSetupInventory, ManagedAssetRow, PrivacySummary, ProviderTestResult, SetupProgressEvent, StageProgress } from '../types'
import KeyModal from './KeyModal'
import clipgaugeMark from '../assets/clipgauge-mark.svg'

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
const CAPTION_LABELS: Record<string, string> = { classic: 'Clean', beast: 'Bold Pop', hormozi: 'Punch', minimal: 'Minimal', 'karaoke-pop': 'Karaoke' }
const PROVIDER_DEFAULTS: Record<string, { model: string; endpoint?: string; locality: string }> = {
  'clipgauge-local': { model: 'clipgauge-local/qwen3-4b-q4_k_m', endpoint: 'http://127.0.0.1:8080/v1', locality: 'local' },
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
  const [provider, setProvider] = useState('clipgauge-local')
  const [model, setModel] = useState(PROVIDER_DEFAULTS['clipgauge-local'].model)
  const [endpoint, setEndpoint] = useState(PROVIDER_DEFAULTS['clipgauge-local'].endpoint ?? '')
  const [providerKey, setProviderKey] = useState('')
  const [advancedMode, setAdvancedMode] = useState(false)
  const [auth, setAuth] = useState('none')
  const [secretHeader, setSecretHeader] = useState('x-api-key')
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null)
  const [captions, setCaptions] = useState('classic')
  const [showKey, setShowKey] = useState(false)
  const [showSetup, setShowSetup] = useState(false)
  const [setupInventory, setSetupInventory] = useState<LocalSetupInventory | null>(null)
  const [setupBusy, setSetupBusy] = useState(false)
  const [setupOperationId, setSetupOperationId] = useState<string | null>(null)
  const [setupProgress, setSetupProgress] = useState<SetupProgressEvent | null>(null)
  const [privacy, setPrivacy] = useState<PrivacySummary | null>(null)
  const [supportMessage, setSupportMessage] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    let unlisten: (() => void) | undefined
    void listen<SetupProgressEvent>('setup-event', ({ payload }) => {
      setSetupProgress(payload)
      if (payload.event === 'terminal') {
        setSetupBusy(false)
        setSetupOperationId(null)
        if (payload.ok) setSupportMessage(payload.message ?? 'Setup completed.')
        else setSupportMessage(payload.message ?? 'Setup needs attention.')
        void api.setupInventory().then((value) => setSetupInventory(value as unknown as LocalSetupInventory)).catch(() => undefined)
      }
    }).then((stop) => { unlisten = stop })
    return () => { unlisten?.() }
  }, [])

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

  async function openSetup() {
    setShowSetup(true)
    try {
      setSetupInventory((await api.setupInventory()) as unknown as LocalSetupInventory)
    } catch (error) {
      setSupportMessage(`Setup inventory unavailable: ${String(error)}`)
    }
  }

  async function runSetupAction(action: () => Promise<Record<string, unknown>>, success: string) {
    setSetupBusy(true)
    try {
      await action()
      setSupportMessage(success)
      setSetupInventory((await api.setupInventory()) as unknown as LocalSetupInventory)
    } catch (error) {
      setSupportMessage(`Setup needs attention: ${String(error)}`)
    } finally {
      setSetupBusy(false)
    }
  }

  async function startSetupAction(args: string[], success: string) {
    setSetupBusy(true)
    setSetupProgress({ operation: 'Preparing verified setup…', message: 'Preparing verified setup…', state: 'STARTING' })
    try {
      const operationId = await api.startSetup(args)
      setSetupOperationId(operationId)
      setSupportMessage(success)
    } catch (error) {
      setSetupBusy(false)
      setSupportMessage(`Setup could not start: ${String(error)}`)
    }
  }

  async function cancelSetupAction() {
    if (!setupOperationId) return
    try {
      await api.cancelSetup(setupOperationId)
      setSupportMessage('Cancelling setup; verified files remain reusable.')
    } catch (error) {
      setSupportMessage(`Could not cancel setup: ${String(error)}`)
    }
  }

  function chooseProvider(next: string) {
    setProvider(next)
    const defaults = PROVIDER_DEFAULTS[next] ?? PROVIDER_DEFAULTS.custom
    setModel(defaults.model)
    setEndpoint(defaults.endpoint ?? '')
    setAuth(next === 'custom' || defaults.locality === 'local' ? 'none' : 'bearer')
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
    if (!providerKey.trim() || ['ollama', 'lmstudio', 'clipgauge-local'].includes(provider)) return
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

  const managedAssets: ManagedAssetRow[] = setupInventory?.managed_assets ?? []
  const hasAsset = (prefix: string) => managedAssets.some((asset) => asset.asset_id.startsWith(prefix) && asset.installed)
  const asrReady = hasAsset('model:asr:') && hasAsset('model:alignment:') && hasAsset('data:nltk:')
  const youtubeReady = hasAsset('runtime:node:') && hasAsset('youtube:bgutil-provider:')
  const analysisReady = ['model:laughter:', 'model:panns:', 'model:campplus:', 'model:ultraface:', 'model:lr-asd:'].every(hasAsset)
  const ffmpegAsset = managedAssets.find((asset) => asset.asset_id.startsWith('runtime:ffmpeg:'))

  return (
    <div className="studio">
      <div className="grain" />
      {showKey && <KeyModal onClose={() => setShowKey(false)} />}
      {showSetup && (
        <div className="modal-scrim" onClick={() => setShowSetup(false)}>
          <div className="modal setup-modal" role="dialog" aria-modal="true" aria-labelledby="setup-title" onClick={(event) => event.stopPropagation()}>
            <header className="modal-head">
              <div><p id="setup-title" className="audit-kicker">SETUP CENTER</p><p className="ig-intro">Verified local AI, one controlled download at a time.</p></div>
              <button className="btn-ghost" onClick={() => setShowSetup(false)}>close</button>
            </header>
            <div className="setup-panel">
              <div className="setup-panel-row"><strong>ClipGauge Local runtime</strong><span className={`chip ${setupInventory?.runtime?.installed ? 'chip-green' : 'chip-amber'}`}>{setupInventory?.runtime?.installed ? 'VERIFIED' : 'NOT INSTALLED'}</span></div>
              <p className="ig-message">llama.cpp runs on loopback only. The archive is pinned and SHA-256 checked before extraction.</p>
              {!setupInventory?.runtime?.installed && <button className="btn-secondary" disabled={setupBusy} onClick={() => runSetupAction(api.installLocalRuntime, 'ClipGauge Local runtime installed and verified.')}>{setupBusy ? 'WORKING…' : 'INSTALL RUNTIME'}</button>}
            </div>
            <div className="setup-panel">
              <div className="setup-panel-row"><strong>Core components</strong><span className="mono setup-size">verified manifest</span></div>
              {setupInventory?.core_assets?.map((asset) => (
                <div className="setup-asset" key={String(asset.asset_id)}>
                  <div><strong>{asset.display_name ?? asset.asset_id}</strong><span>{asset.purpose ?? 'ClipGauge component'}</span></div>
                  <span className={`chip ${asset.installed ? 'chip-green' : 'chip-amber'}`}>{asset.installed ? 'READY' : String(asset.integrity ?? 'SETUP')}</span>
                </div>
              ))}
            </div>
            <div className="setup-panel">
              <div className="setup-panel-row"><strong>Managed components</strong><span className="mono setup-size">{managedAssets.length} verified assets</span></div>
              <p className="ig-message">Every large download is listed, consented as a group, resumable, cancellable, and SHA-256 checked before use.</p>
              <div className="setup-asset"><div><strong>Video engine</strong><span>Caption-capable FFmpeg for decoding and rendering</span></div>{ffmpegAsset?.installed ? <span className="chip chip-green">READY</span> : <button className="btn-secondary" disabled={setupBusy} onClick={() => startSetupAction(['install-ffmpeg'], 'Video engine installation started.')}>{setupBusy ? 'WORKING…' : 'DOWNLOAD'}</button>}</div>
              <div className="setup-asset"><div><strong>Speech recognition</strong><span>Verified faster-whisper, English alignment, and sentence data</span></div>{asrReady ? <span className="chip chip-green">READY</span> : <button className="btn-secondary" disabled={setupBusy} onClick={() => startSetupAction(['install-group', '--group', 'core:asr'], 'Speech recognition download started.')}>{setupBusy ? 'WORKING…' : 'DOWNLOAD'}</button>}</div>
              <div className="setup-asset"><div><strong>Clip analysis</strong><span>Speaker, laughter, audio-event, and smart-camera assets</span></div>{analysisReady ? <span className="chip chip-green">READY</span> : <button className="btn-secondary" disabled={setupBusy} onClick={() => startSetupAction(['install-group', '--group', 'core:analysis'], 'Analysis components download started.')}>{setupBusy ? 'WORKING…' : 'DOWNLOAD'}</button>}</div>
              <div className="setup-asset"><div><strong>YouTube compatibility</strong><span>yt-dlp, portable Node.js, and loopback PO-token provider</span></div>{youtubeReady ? <span className="chip chip-green">READY</span> : <button className="btn-secondary" disabled={setupBusy} onClick={() => startSetupAction(['install-group', '--group', 'core:youtube'], 'YouTube compatibility setup started.')}>{setupBusy ? 'WORKING…' : 'DOWNLOAD'}</button>}</div>
              {setupBusy && <div className="setup-progress" role="status"><div className="setup-panel-row"><strong>{setupProgress?.display_name ?? setupProgress?.operation ?? 'Preparing setup…'}</strong><button className="btn-ghost" disabled={!setupOperationId} onClick={cancelSetupAction}>cancel</button></div><p className="ig-message">{setupProgress?.message ?? 'Preparing verified assets…'}{setupProgress?.eta_seconds != null ? ` · about ${Math.ceil(setupProgress.eta_seconds)}s left` : ''}</p>{setupProgress?.bytes_total ? <div className="progress-track"><div className="progress-fill" style={{ width: `${Math.max(0, Math.min(100, (setupProgress.bytes_done ?? 0) / setupProgress.bytes_total * 100))}%` }} /></div> : <div className="progress-track"><div className="progress-fill progress-indeterminate" /> </div>}</div>}
              <details className="setup-details"><summary>Show verified asset details</summary>{managedAssets.map((asset) => <div className="setup-asset" key={asset.asset_id}><div><strong>{asset.display_name}</strong><span>{asset.purpose} · {asset.license}</span></div><span className={`chip ${asset.installed ? 'chip-green' : 'chip-amber'}`}>{asset.installed ? 'VERIFIED' : asset.status ?? 'SETUP'}</span></div>)}</details>
            </div>
            <div className="setup-panel">
              <div className="setup-panel-row"><strong>Local models</strong><span className="mono setup-size">{setupInventory?.storage?.required_bytes ? `${(setupInventory.storage.required_bytes / 1024 ** 3).toFixed(1)} GB required` : 'size check pending'}</span></div>
              {setupInventory?.models?.map((asset) => (
                <div className="setup-asset" key={String(asset.asset_id)}>
                  <div><strong>{asset.display_name ?? asset.asset_id}</strong><span className="mono">{asset.license ?? 'license in source manifest'}</span></div>
                  {asset.installed ? <span className="chip chip-green">VERIFIED</span> : <button className="btn-secondary" disabled={setupBusy} onClick={() => runSetupAction(() => api.downloadLocalModel(String(asset.asset_id)), 'Local model downloaded and verified.')}>{setupBusy ? 'WORKING…' : 'DOWNLOAD'}</button>}
                </div>
              ))}
            </div>
            <p className="ob-fine">Catalog entries show the upstream license and provenance. Catalog-only models remain unavailable until their exact downloadable artifact is approved.</p>
          </div>
        </div>
      )}
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
            <div className="rail-brand-line"><img className="rail-mark" src={clipgaugeMark} alt="" /><span className="rail-logo">ClipGauge</span></div>
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
          <button className="btn-ghost" onClick={openSetup}>
            ▣ setup center
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
            Create clips
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
              Choose video
            </button>
            <button
              className="btn-primary"
              onClick={() => onRun(source.trim(), provider, captions, model || undefined, endpoint || undefined, auth, auth === 'custom_secret_header' ? secretHeader : undefined)}
              disabled={running || !source.trim()}
            >
              {running ? 'Working…' : 'Create clips'}
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
              {(advancedMode ? Object.keys(PROVIDER_DEFAULTS) : ['clipgauge-local', 'ollama', 'lmstudio', 'gemini']).map((kind) => (
                <button
                  key={kind}
                  className={`opt ${provider === kind ? 'opt-on' : ''}`}
                  onClick={() => chooseProvider(kind)}
                  disabled={running}
                  aria-pressed={provider === kind}
                >
                  {kind === 'clipgauge-local' ? 'ClipGauge Local' : kind}
                </button>
              ))}
            </div>
            {advancedMode ? <div className="provider-config" aria-label="Advanced provider configuration">
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
              {!['ollama', 'lmstudio', 'clipgauge-local'].includes(provider) && auth !== 'none' && (
                <>
                  <label className="field-label" htmlFor="provider-key">credential</label>
                  <input id="provider-key" type="password" value={providerKey} onChange={(event) => setProviderKey(event.target.value)} disabled={running} placeholder="stored in OS vault; optional until Test Connection" autoComplete="off" />
                  <button className="btn-secondary" onClick={saveProviderKey} disabled={running || !providerKey.trim()}>SAVE CREDENTIAL</button>
                </>
              )}
              <button className="btn-secondary" onClick={testProvider} disabled={running}>TEST CONNECTION</button>
              {testResult && <p className={`provider-test provider-test-${testResult.state.toLowerCase()}`} role="status">{testResult.state}: {testResult.message ?? `${testResult.provider ?? provider} / ${testResult.model ?? model}`}</p>}
            </div> : <div className="provider-simple" aria-label="Simple provider mode"><p className="ig-message">{provider === 'clipgauge-local' ? 'Private scoring runs on this computer.' : provider === 'ollama' || provider === 'lmstudio' ? 'Local scoring uses your selected desktop runner.' : 'Cloud scoring uses a credential you provide.'}</p><button className="btn-ghost" onClick={() => setAdvancedMode(true)} disabled={running}>Advanced provider setup</button></div>}
            <div className="opt-group">
              <span className="opt-label">captions</span>
              {CAPTION_PRESETS.map((preset) => (
                <button
                  key={preset}
                  className={`opt ${captions === preset ? 'opt-on' : ''}`}
                  onClick={() => setCaptions(preset)}
                  disabled={running}
                >
                  {CAPTION_LABELS[preset] ?? preset}
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

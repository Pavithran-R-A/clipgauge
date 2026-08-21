import { useEffect, useMemo, useState } from 'react'
import { listen } from '@tauri-apps/api/event'
import { api } from '../api'
import type { LocalSetupInventory, SetupProgressEvent } from '../types'
import { formatBytes, formatDuration, formatRate, meaningfulEta, progressPercent } from '../setupFormatting'

interface Props {
  onDone: () => void
}

const BALANCED_MODEL = 'clipgauge-local/qwen3-4b-q4_k_m'

export default function Onboarding({ onDone }: Props) {
  const [step, setStep] = useState(0)
  const [inventory, setInventory] = useState<LocalSetupInventory | null>(null)
  const [busy, setBusy] = useState(false)
  const [setupMessage, setSetupMessage] = useState<string | null>(null)
  const [setupOperationId, setSetupOperationId] = useState<string | null>(null)
  const [lastSetupArgs, setLastSetupArgs] = useState<string[] | null>(null)
  const [setupProgress, setSetupProgress] = useState<SetupProgressEvent | null>(null)
  const [downloadConsent, setDownloadConsent] = useState(false)

  const refreshInventory = () => {
    api.setupInventory()
      .then((value) => setInventory(value as unknown as LocalSetupInventory))
      .catch(() => setInventory(null))
  }

  useEffect(() => {
    refreshInventory()
    let unlisten: (() => void) | undefined
    void listen<SetupProgressEvent>('setup-event', ({ payload }) => {
      setSetupProgress(payload)
      if (payload.event === 'terminal') {
        setBusy(false)
        setSetupOperationId(null)
        setSetupMessage(payload.ok ? (payload.message ?? 'Setup completed and verified.') : (payload.message ?? 'Setup needs attention; retry the selected action.'))
        refreshInventory()
      }
    }).then((stop) => { unlisten = stop })
    return () => { unlisten?.() }
  }, [])

  const runtimeReady = Boolean(inventory?.runtime?.installed)
  const balancedModel = useMemo(
    () => inventory?.models.find((model) => model.asset_id === BALANCED_MODEL),
    [inventory]
  )
  const modelReady = Boolean(balancedModel?.installed)
  const storageEstimate = inventory?.storage?.required_bytes
  const setupPercent = progressPercent(setupProgress)
  const setupEta = meaningfulEta(setupProgress)
  const setupRate = formatRate(setupProgress?.bytes_per_second)

  const installRuntime = async () => {
    if (!downloadConsent) {
      setSetupMessage('Please approve the one-time managed download plan first.')
      return
    }
    setLastSetupArgs(['install-runtime'])
    setBusy(true)
    setSetupProgress({ operation: 'Preparing runtime setup…', message: 'Preparing verified runtime download…', state: 'STARTING', elapsed_seconds: 0, one_time_download: true })
    try {
      setSetupOperationId(await api.startSetup(['install-runtime']))
      setSetupMessage('Runtime setup started; verified progress is shown below.')
    } catch (error) {
      setBusy(false)
      setSetupMessage(`Runtime setup could not start: ${String(error)}`)
    }
  }

  const downloadModel = async () => {
    if (!downloadConsent) {
      setSetupMessage('Please approve the one-time managed download plan first.')
      return
    }
    setLastSetupArgs(['download-model', BALANCED_MODEL])
    setBusy(true)
    setSetupProgress({ operation: 'Preparing balanced model setup…', message: 'Preparing verified model download…', state: 'STARTING', elapsed_seconds: 0, one_time_download: true })
    try {
      setSetupOperationId(await api.startSetup(['download-model', BALANCED_MODEL]))
      setSetupMessage('Balanced model setup started; verified progress is shown below.')
    } catch (error) {
      setBusy(false)
      setSetupMessage(`Model setup could not start: ${String(error)}`)
    }
  }

  return (
    <div className="onboarding">
      <div className="grain" />
      {step === 0 && (
        <section className="ob-step" key="s0">
          <p className="ob-kicker">ClipGauge / the editing bay</p>
          <h1 className="ob-title">TURN LONG VIDEO<br />INTO <span className="amber">MOMENTS</span>.</h1>
          <p className="ob-body">ClipGauge listens for the parts people replay: a sharp line, a laugh, a turn in the story. It shows its work, keeps checkpoints, and lets you choose where intelligence runs.</p>
          <button className="btn-primary" onClick={() => setStep(1)}>Set up the bay</button>
        </section>
      )}
      {step === 1 && (
        <section className="ob-step" key="s1">
          <p className="ob-kicker">01 / choose your first run</p>
          <h2 className="ob-h2">Start local, bring a key, or bring your own endpoint.</h2>
          <div className="ob-cards">
            <div className={`ob-card ${runtimeReady && modelReady ? 'done' : ''}`}>
              <div className="ob-card-head">
                <h3>ClipGauge Local <span className={`led ${runtimeReady && modelReady ? 'led-on' : 'led-half'}`} /></h3>
                <span className="chip chip-amber">PRIVATE BY DEFAULT</span>
              </div>
              <p>{runtimeReady && modelReady ? 'Ready on this computer. Transcript scoring stays on the loopback runtime.' : 'A managed llama.cpp runtime and a curated Qwen model run on this computer. No paid API key is required.'}</p>
              <div className="setup-status mono">
                <span>{runtimeReady ? 'runtime verified' : 'runtime not installed'}</span>
                <span>{modelReady ? 'balanced model verified' : 'balanced model not installed'}</span>
              </div>
              <div className="ob-consent-inline"><label><input type="checkbox" checked={downloadConsent} onChange={(event) => setDownloadConsent(event.target.checked)} /> I approve ClipGauge downloading the listed one-time assets to this computer after each explicit action.</label></div>
              <div className="ob-actions">
                {!runtimeReady && <button className="btn-secondary" disabled={busy || !downloadConsent} onClick={installRuntime}>{busy ? 'Working…' : 'Install runtime'}</button>}
                {runtimeReady && !modelReady && <button className="btn-secondary" disabled={busy || !downloadConsent} onClick={downloadModel}>{busy ? 'Working…' : `Download balanced model (${formatBytes(balancedModel?.size_bytes)})`}</button>}
              </div>
              <p className="ob-fine">The runtime is loopback-only and the model is SHA-256 verified before use.</p>
            </div>
            <div className="ob-card">
              <h3>Curated cloud / bring a key</h3>
              <p>Gemini, OpenRouter, Groq, Cloudflare Workers AI, Hugging Face, and Cerebras can be configured in Studio. Credentials stay in the operating-system vault.</p>
            </div>
            <div className="ob-card">
              <h3>Custom compatible endpoint</h3>
              <p>Configure an OpenAI-compatible URL, model, and credential header. Remote HTTP is rejected; loopback HTTP is reserved for local services.</p>
            </div>
          </div>
          {setupMessage && <p className="ob-notice" role="status">{setupMessage}</p>}
          {setupProgress && <div className="setup-progress onboarding-progress" role="status" aria-live="polite"><div className="setup-panel-row"><strong>{setupProgress.display_name ?? setupProgress.operation ?? 'Setup'}</strong><button className="btn-ghost" disabled={!setupOperationId} onClick={() => setupOperationId && api.cancelSetup(setupOperationId).then(() => setSetupMessage('Cancelling setup; verified files remain reusable.')).catch((error) => setSetupMessage(`Could not cancel setup: ${String(error)}`))}>cancel</button></div><p className="ig-message">{setupProgress.message ?? 'Downloading…'}</p><div className="setup-progress-facts"><span>{setupProgress.bytes_total ? `${formatBytes(setupProgress.bytes_done ?? 0)} / ${formatBytes(setupProgress.bytes_total)}` : 'Downloading…'}</span>{setupPercent != null && <span>{setupPercent}%</span>}{setupRate && <span>{setupRate}</span>}{setupEta && <span>{setupEta} remaining</span>}<span>elapsed {formatDuration(setupProgress.elapsed_seconds)}</span>{setupProgress.one_time_download && <span>One-time download</span>}</div>{setupProgress.bytes_total && setupPercent != null ? <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={setupPercent}><div className="progress-fill" style={{ width: `${setupPercent}%` }} /></div> : <div className="progress-track" role="progressbar" aria-label="Download in progress"><div className="progress-fill progress-indeterminate" /></div>}{!busy && setupProgress.event !== 'terminal' && lastSetupArgs && <button className="btn-secondary" onClick={() => { setBusy(true); setSetupProgress({ operation: 'Retrying verified setup…', message: 'Retrying the selected managed operation…', state: 'STARTING', elapsed_seconds: 0, one_time_download: true }); api.startSetup(lastSetupArgs).then(setSetupOperationId).catch((error) => { setBusy(false); setSetupMessage(`Retry could not start: ${String(error)}`) }) }}>RETRY</button>}</div>}
          <p className="ob-fine">You can switch providers per run. Existing jobs retain their provider snapshot when resumed. The consent checkbox above is required before any managed download begins.</p>
          <button className="btn-primary" onClick={() => setStep(2)}>Continue</button>
        </section>
      )}
      {step === 2 && (
        <section className="ob-step" key="s2">
          <p className="ob-kicker">02 / your data, your call</p>
          <h2 className="ob-h2">A first run may download a few gigabytes.</h2>
          <p className="ob-body">ClipGauge keeps speech, audio, and local-AI models under <span className="mono">~/.clipgauge</span>. It asks before large downloads, verifies every managed asset, and keeps job checkpoints so an interrupted run can resume.</p>
          <div className="ob-consent">
            <span className="ob-consent-label mono">ESTIMATED REQUIRED STORAGE</span>
            <strong>{formatBytes(storageEstimate)}</strong>
            <span>Provider credentials remain in the operating-system vault. ClipGauge has no telemetry account.</span>
          </div>
          <button className="btn-primary" onClick={onDone}>Open the studio</button>
        </section>
      )}
    </div>
  )
}

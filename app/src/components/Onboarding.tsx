import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { LocalSetupInventory } from '../types'

interface Props {
  onDone: () => void
}

const BALANCED_MODEL = 'clipgauge-local/qwen3-4b-q4_k_m'

function formatBytes(value: number | undefined): string {
  if (!value || value <= 0) return 'unknown size'
  const units = ['B', 'MB', 'GB', 'TB']
  let amount = value
  let index = 0
  while (amount >= 1024 && index < units.length - 1) {
    amount /= 1024
    index += 1
  }
  return `${amount >= 10 || index === 0 ? Math.round(amount) : amount.toFixed(1)} ${units[index]}`
}

export default function Onboarding({ onDone }: Props) {
  const [step, setStep] = useState(0)
  const [inventory, setInventory] = useState<LocalSetupInventory | null>(null)
  const [busy, setBusy] = useState(false)
  const [setupMessage, setSetupMessage] = useState<string | null>(null)
  const [downloadConsent, setDownloadConsent] = useState(false)

  const refreshInventory = () => {
    api.setupInventory()
      .then((value) => setInventory(value as unknown as LocalSetupInventory))
      .catch(() => setInventory(null))
  }

  useEffect(() => {
    refreshInventory()
  }, [])

  const runtimeReady = Boolean(inventory?.runtime?.installed)
  const balancedModel = useMemo(
    () => inventory?.models.find((model) => model.asset_id === BALANCED_MODEL),
    [inventory]
  )
  const modelReady = Boolean(balancedModel?.installed)
  const storageEstimate = inventory?.storage?.required_bytes

  const installRuntime = async () => {
    if (!downloadConsent) {
      setSetupMessage('Please approve the one-time managed download plan first.')
      return
    }
    setBusy(true)
    setSetupMessage('Installing the verified local runtime…')
    try {
      await api.installLocalRuntime()
      setSetupMessage('ClipGauge Local runtime installed and verified.')
      refreshInventory()
    } catch (error) {
      setSetupMessage(`Runtime setup needs attention: ${String(error)}`)
    } finally {
      setBusy(false)
    }
  }

  const downloadModel = async () => {
    if (!downloadConsent) {
      setSetupMessage('Please approve the one-time managed download plan first.')
      return
    }
    setBusy(true)
    setSetupMessage('Downloading the balanced local model. You can leave this running and come back.')
    try {
      await api.downloadLocalModel(BALANCED_MODEL)
      setSetupMessage('Balanced model downloaded and verified.')
      refreshInventory()
    } catch (error) {
      setSetupMessage(`Model setup needs attention: ${String(error)}`)
    } finally {
      setBusy(false)
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

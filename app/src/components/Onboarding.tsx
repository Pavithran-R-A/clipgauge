import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Check, Cloud, Cpu, Download, LockKeyhole, ShieldCheck, Square } from 'lucide-react'
import { listen } from '@tauri-apps/api/event'
import { api } from '../api'
import type { LocalSetupInventory, SetupProgressEvent } from '../types'
import { formatBytes, formatDuration, formatRate, meaningfulEta, progressPercent } from '../setupFormatting'
import { summarizeSetupQueue, type SetupQueueSummary } from '../setupState'

interface Props { onDone: () => void }

export default function Onboarding({ onDone }: Props) {
  const [step, setStep] = useState(0)
  const [inventory, setInventory] = useState<LocalSetupInventory | null>(null)
  const [approved, setApproved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [operationId, setOperationId] = useState<string | null>(null)
  const [progress, setProgress] = useState<SetupProgressEvent | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [, setQueueSummary] = useState<SetupQueueSummary>({ state: 'pending', completed: 0, failed: 0, cancelled: false })
  const queueRef = useRef<string[][]>([])
  const outcomesRef = useRef<Array<'success' | 'failed' | 'cancelled'>>([])

  const refresh = () => api.setupInventory().then((value) => setInventory(value as unknown as LocalSetupInventory)).catch(() => setInventory(null))

  useEffect(() => {
    refresh()
    let stop: (() => void) | undefined
    void listen<SetupProgressEvent>('setup-event', ({ payload }) => {
      setProgress(payload)
      if (payload.event === 'terminal') {
        setOperationId(null)
        outcomesRef.current.push(payload.code === 'CANCELLED' ? 'cancelled' : payload.ok ? 'success' : 'failed')
        const next = queueRef.current.shift()
        if (next) void begin(next, 'Moving to the next local component.')
        else {
          setBusy(false)
          setStartedAt(null)
          const summary = summarizeSetupQueue(outcomesRef.current, 0)
          setQueueSummary(summary)
          setProgress(null)
          setMessage(summary.state === 'complete' ? 'Your local setup is ready.' : summary.state === 'cancelled' ? 'Setup cancelled. Verified assets remain available.' : summary.state === 'partial_failure' ? 'Setup needs attention. One or more components failed; retry from Setup & Storage.' : payload.message ?? 'Setup needs attention. Retry from Setup & Storage.')
          void refresh()
        }
      }
    }).then((unlisten) => { stop = unlisten })
    return () => stop?.()
  }, [])

  useEffect(() => {
    if (!startedAt) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [startedAt])

  const runtimeReady = Boolean(inventory?.runtime?.installed)
  const balanced = inventory?.models?.find((model) => String(model.display_name ?? '').toLowerCase().includes('balanced')) ?? inventory?.models?.[0]
  const modelReady = Boolean(balanced?.installed)
  const remaining = [!runtimeReady, !modelReady].filter(Boolean).length
  const percent = progressPercent(progress)
  const eta = meaningfulEta(progress)
  const elapsed = progress?.elapsed_seconds ?? (startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : 0)

  async function begin(args: string[], text: string) {
    setBusy(true)
    setStartedAt((value) => value ?? Date.now())
    setProgress({ event: 'progress', operation: 'Preparing setup…', message: 'Checking the approved local downloads…', state: 'STARTING', elapsed_seconds: 0, one_time_download: true })
    setMessage(text)
    try { setOperationId(await api.startSetup(args)) } catch (error) { setBusy(false); setStartedAt(null); setProgress(null); setQueueSummary({ state: 'failed', completed: 0, failed: 1, cancelled: false }); setMessage(`Setup could not start: ${String(error)}`) }
  }

  async function installLocal() {
    if (!approved) { setMessage('Approve the one-time download plan first.'); return }
    const args: string[][] = []
    if (!runtimeReady) args.push(['install-runtime'])
    if (!modelReady && balanced?.asset_id) args.push(['download-model', String(balanced.asset_id)])
    if (!args.length) { setMessage('ClipGauge Local is already ready.'); return }
    outcomesRef.current = []
    queueRef.current = args.slice(1)
    setQueueSummary({ state: 'running', completed: 0, failed: 0, cancelled: false })
    await begin(args[0], 'Installing the local components ClipGauge needs.')
  }

  return <div className="onboarding-page"><div className="onboarding-ornament" aria-hidden="true" /><header className="onboarding-brand"><span className="brand-mark" aria-hidden="true"><span /></span><strong>ClipGauge</strong><span>First run</span></header>{step === 0 && <main className="onboarding-hero"><div className="hero-copy"><p className="section-eyebrow">Make moments worth sharing</p><h1>Turn long videos into clips people remember.</h1><p className="page-lede">ClipGauge finds the parts with energy, reframes them for vertical video, and gives you captions you can tune before you export.</p><button type="button" className="button button-primary" onClick={() => setStep(1)}>Set up ClipGauge <ArrowRight size={17} aria-hidden="true" /></button></div><div className="hero-preview"><div className="preview-window"><div className="preview-window-top"><span /><span /><span /></div><div className="preview-video"><span className="preview-caption">make your<br /><b>next moment</b></span><span className="preview-play"><ArrowRight size={18} aria-hidden="true" /></span></div></div></div></main>}{step === 1 && <main className="onboarding-step"><div className="step-heading"><p className="section-eyebrow">Step 1 of 2</p><h1>Start with a private setup.</h1><p className="page-lede">ClipGauge Local runs scoring on this computer. There is no account and no paid API key required.</p></div><section className="onboarding-options"><article className={`onboarding-option ${runtimeReady && modelReady ? 'is-ready' : ''}`}><div className="option-icon"><Cpu size={21} aria-hidden="true" /></div><div className="option-copy"><div className="option-title"><h2>ClipGauge Local</h2><span className="status-pill tone-ready"><span className="status-dot" aria-hidden="true" />{runtimeReady && modelReady ? 'Ready' : 'Recommended'}</span></div><p>Private scoring on this computer. Downloaded components are verified and reused for future videos.</p><div className="option-facts"><span><Check size={14} aria-hidden="true" /> No API key</span><span><Check size={14} aria-hidden="true" /> Works offline after setup</span></div></div></article><article className="onboarding-option subdued"><div className="option-icon"><Cloud size={21} aria-hidden="true" /></div><div className="option-copy"><h2>Use another AI later</h2><p>You can connect OpenRouter Free, Gemini, Groq, Ollama, LM Studio, or another provider from AI Providers.</p></div></article></section><div className="onboarding-consent"><label><input type="checkbox" checked={approved} onChange={(event) => setApproved(event.target.checked)} /><span><strong>Approve the local download plan</strong><small>ClipGauge will download only the components shown here, one time, to this computer.</small></span></label><div className="consent-total"><span>Remaining components</span><strong>{remaining ? `${remaining} to install` : 'Already ready'}</strong></div></div>{(remaining > 0 || busy) && <button type="button" className="button button-primary" onClick={installLocal} disabled={busy || !approved}><Download size={17} aria-hidden="true" />{busy ? 'Installing…' : 'Install required components'}</button>}{message && <p className="inline-message" role="status">{message}</p>}{progress && <section className="download-tray onboarding-tray" aria-live="polite"><div className="download-tray-head"><div><p className="section-eyebrow">Setup progress</p><h2>{progress.display_name ?? progress.operation ?? 'Preparing setup'}</h2></div><button type="button" className="button button-secondary" onClick={() => operationId && api.cancelSetup(operationId)} disabled={!operationId}><Square size={13} aria-hidden="true" /> Cancel</button></div><p className="download-message">{progress.message ?? 'Preparing verified components…'}</p><div className="progress-facts"><span>{progress.bytes_total ? `${formatBytes(progress.bytes_done ?? 0)} / ${formatBytes(progress.bytes_total)}` : 'Calculating size…'}</span>{percent != null && <span>{percent}%</span>}{formatRate(progress.bytes_per_second) && <span>{formatRate(progress.bytes_per_second)}</span>}{eta && <span>{eta} remaining</span>}<span>{formatDuration(elapsed)} elapsed</span></div><div className="progress-track" role="progressbar" aria-label="Setup download progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent ?? undefined}><div className={`progress-fill ${percent == null ? 'is-indeterminate' : ''}`} style={percent != null ? { width: `${percent}%` } : undefined} /></div></section>}<div className="onboarding-next"><span><LockKeyhole size={15} aria-hidden="true" /> You can change AI providers any time.</span><button type="button" className="text-button" onClick={() => setStep(2)}>Continue <ArrowRight size={15} aria-hidden="true" /></button></div></main>}{step === 2 && <main className="onboarding-step final-step"><div className="final-icon"><ShieldCheck size={30} aria-hidden="true" /></div><p className="section-eyebrow">Step 2 of 2</p><h1>You’re ready to create.</h1><p className="page-lede">Your videos and job files stay on this computer unless you choose a cloud provider or a public video link.</p><div className="final-facts"><div><span>Local model</span><strong>{modelReady ? 'Installed and ready' : 'Can be installed from Setup & Storage'}</strong></div><div><span>Storage location</span><strong className="technical-text">~/.clipgauge</strong></div></div><button type="button" className="button button-primary" onClick={onDone}>Open Create <ArrowRight size={17} aria-hidden="true" /></button></main>}</div>
}

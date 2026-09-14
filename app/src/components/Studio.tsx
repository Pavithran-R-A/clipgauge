import { useEffect, useRef, useState } from 'react'
import { FileVideo, FolderOpen, Info, LockKeyhole, Play, Settings2, Sparkles, X } from 'lucide-react'
import { open } from '@tauri-apps/plugin-dialog'
import type { JobSummary, StageProgress } from '../types'
import { creatorHeadline, YOUTUBE_HELPER_COPY, type CreatorRunState } from '../creatorState'
import { friendlyErrorMessage } from '../errorMessaging'
import { evaluateProviderReadiness, resolveProviderExecution, type QualityMode } from '../providerContract'

const STAGE_ORDER = ['ingest', 'asr', 'diarize', 'events', 'candidates', 'score', 'camera', 'render']
const STAGE_LABELS: Record<string, string> = {
  ingest: 'Preparing video',
  asr: 'Transcribing speech',
  diarize: 'Identifying speakers',
  events: 'Understanding audio',
  candidates: 'Finding strong moments',
  score: 'Scoring clips',
  camera: 'Smart reframing',
  render: 'Creating clips',
}
const AI_OPTIONS = [
  { id: 'clipgauge-local', name: 'ClipGauge Local', description: 'Lightweight or Balanced. No cloud.', tone: 'teal' },
  { id: 'openrouter', name: 'OpenRouter Free', description: 'A free cloud route when available.', tone: 'blue' },
  { id: 'other', name: 'Other providers', description: 'Gemini, Groq, Ollama, and more.', tone: 'neutral' },
]
const DEFAULT_PROVIDER_MODELS: Record<string, string> = {
  'clipgauge-local': 'clipgauge-local/qwen3-4b-q4_k_m',
  openrouter: 'openrouter/free',
  gemini: 'gemini-flash-latest',
  groq: 'openai/gpt-oss-20b',
  cloudflare: '@cf/meta/llama-3.1-8b-instruct',
  huggingface: 'Qwen/Qwen3-32B',
  cerebras: 'gpt-oss-120b',
  ollama: 'auto',
  lmstudio: 'auto',
}
const CAPTION_OPTIONS = [
  { id: 'classic', name: 'Clean', description: 'Readable and balanced.' },
  { id: 'beast', name: 'Bold Pop', description: 'High-energy emphasis.' },
  { id: 'hormozi', name: 'Punch', description: 'Strong words, strong rhythm.' },
  { id: 'minimal', name: 'Minimal', description: 'Quiet and focused.' },
]
const QUALITY_OPTIONS = [
  { id: 'private', name: 'Private / Local', description: 'Use your selected local provider. No cloud.' },
  { id: 'balanced', name: 'Balanced / Hybrid', description: 'Local discovery plus your configured cloud provider.' },
  { id: 'best', name: 'Best Quality', description: 'Your configured cloud provider and model.' },
] as const
const OUTPUT_OPTIONS = [
  { id: 'best', name: 'Best only', description: 'Show the top exceptional finalists.' },
  { id: 'recommended', name: 'Recommended', description: 'Show several strong, diverse finalists.' },
  { id: 'more', name: 'More options', description: 'Keep borderline moments available for review.' },
] as const

interface Props {
  jobs: JobSummary[]
  running: boolean
  runState: CreatorRunState
  cancelling: boolean
  startedAt: number | null
  elapsedSeconds?: number | null
  stages: Record<string, StageProgress>
  error: string | null
  errorCode: string | null
  notice: string | null
  onRun: (source: string, provider: string, captions: string, model?: string, endpoint?: string, auth?: string, secretHeader?: string, browserSession?: string, qualityMode?: string, outputPreference?: string) => void
  localModelId?: string
  providerModel?: string
  providerModelAvailable?: boolean
  providerModelCompatible?: boolean
  providerServiceReady?: boolean
  cloudConfigured?: boolean
  providerEndpoint?: string
  onCancel: () => void
  onContinueCpu: () => void
  onRepairGpu?: () => void
  gpuRepairing?: boolean
  onNavigate: (section: 'providers' | 'setup' | 'privacy') => void
  selectedProvider: string
  onSelectProvider: (provider: string) => void
  onOpenJob: (id: string) => void
  onResume: (id: string) => void
  resultsLoadFailed?: boolean
  onRetryResults?: () => void
}

function displayFileName(source: string) {
  return source.split(/[\\/]/).pop() || source
}

function formatElapsed(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}

function readProviderModel(provider: string, localModelId?: string) {
  if (provider === 'clipgauge-local' && localModelId) return localModelId
  try {
    return window.localStorage.getItem(`clipgauge.provider-model.${provider}`) ?? DEFAULT_PROVIDER_MODELS[provider] ?? 'model required'
  } catch {
    return DEFAULT_PROVIDER_MODELS[provider] ?? 'model required'
  }
}

function providerName(provider: string) {
  const names: Record<string, string> = {
    'clipgauge-local': 'ClipGauge Local',
    openrouter: 'OpenRouter Free',
    gemini: 'Gemini',
    groq: 'Groq',
    cloudflare: 'Cloudflare Workers AI',
    huggingface: 'Hugging Face',
    cerebras: 'Cerebras',
    ollama: 'Ollama',
    lmstudio: 'LM Studio',
    custom: 'Custom OpenAI-compatible',
  }
  return names[provider] ?? provider
}

export default function Studio({ running, runState, cancelling, startedAt, elapsedSeconds, stages, error, errorCode, notice, resultsLoadFailed = false, onRetryResults, onRun, localModelId, providerModel, providerModelAvailable, providerModelCompatible, providerServiceReady, cloudConfigured = true, providerEndpoint, onContinueCpu, onRepairGpu, gpuRepairing, onCancel, onNavigate, selectedProvider, onSelectProvider }: Props) {
  const [source, setSource] = useState('')
  const [sourceDraft, setSourceDraft] = useState('')
  const [captions, setCaptions] = useState('classic')
  const [qualityMode, setQualityMode] = useState<(typeof QUALITY_OPTIONS)[number]['id']>('private')
  const [outputPreference, setOutputPreference] = useState<(typeof OUTPUT_OPTIONS)[number]['id']>('recommended')
  const [fileError, setFileError] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const mountedRef = useRef(true)
  const provider = selectedProvider

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  useEffect(() => {
    if (!startedAt) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [startedAt])

  const elapsed = startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : elapsedSeconds ?? 0
  const selectedAI = AI_OPTIONS.find((option) => option.id === provider) ?? { id: 'other', name: providerName(provider), description: 'Selected provider for scoring.', tone: 'neutral' }
  const selectedCaption = CAPTION_OPTIONS.find((option) => option.id === captions) ?? CAPTION_OPTIONS[0]
  const selectedModel = providerModel ?? readProviderModel(provider, localModelId)
  const readiness = evaluateProviderReadiness({ provider, model: selectedModel, credentialReady: cloudConfigured, endpointReady: providerEndpoint ? true : undefined, modelAvailable: providerModelAvailable, modelCompatible: providerModelCompatible, serviceReady: providerServiceReady })
  const cloudAvailable = readiness.locality === 'cloud' && readiness.configured
  const modeAllowed = qualityMode === 'private' ? readiness.can_private : qualityMode === 'balanced' ? readiness.can_hybrid : readiness.can_best
  const modeBlocked = !modeAllowed
  const execution = modeAllowed ? resolveProviderExecution(provider, qualityMode as QualityMode, selectedModel) : null
  const hasProgress = running || Object.keys(stages).length > 0 || runState !== 'IDLE' || Boolean(error)

  async function chooseFile() {
    setFileError(null)
    try {
      const selected = await open({ multiple: false, directory: false, filters: [{ name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi'] }] })
      if (!mountedRef.current) return
      if (typeof selected === 'string') {
        setSource(selected)
        setSourceDraft('')
      }
    } catch (error) {
      if (mountedRef.current) setFileError(friendlyErrorMessage(error, 'The video picker could not open. Retry the action.'))
    }
  }

  function dropFile(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault()
    if (!running) {
      const file = event.dataTransfer.files[0] as (File & { path?: string }) | undefined
      if (file?.path) { setFileError(null); setSource(file.path); setSourceDraft('') }
    }
  }

  function chooseAI(id: string) {
    if (id === 'other') {
      onNavigate('providers')
      return
    }
    onSelectProvider(id)
  }

  return (
    <div className="workspace-page create-page">
      {errorCode === 'ASR_GPU_FALLBACK_REQUIRES_APPROVAL' && <section className="cpu-recovery card-surface" aria-live="polite"><div><strong>Choose how speech should continue</strong><p>GPU speech acceleration failed. Repair it here, or approve a slower CPU run for this video.</p></div><div className="detail-actions"><button type="button" className="button button-secondary" onClick={onRepairGpu} disabled={gpuRepairing}>{gpuRepairing ? 'Repairing GPU acceleration...' : 'Repair GPU acceleration'}</button><button type="button" className="button button-secondary" onClick={onContinueCpu}>Continue in slower CPU mode</button></div></section>}
      <header className="page-header create-header"><div><p className="section-eyebrow">Create</p><h1>Create clips</h1><p className="page-lede">Turn a long video into vertical clips worth sharing.</p></div><div className="header-actions"><button type="button" className="button button-secondary" onClick={() => onNavigate('privacy')}><LockKeyhole size={16} aria-hidden="true" /> Privacy</button><button type="button" className="button button-secondary" onClick={() => onNavigate('setup')}><Settings2 size={16} aria-hidden="true" /> Setup</button></div></header>
      <div className="create-layout">
        <div className="create-main-column">
          <section className="add-video card-surface" aria-labelledby="add-video-heading">
            <div className="section-heading"><div><p className="section-eyebrow">Step 1</p><h2 id="add-video-heading">Add a video</h2><p className="section-caption">Choose a local file or paste a public YouTube link.</p></div><span className="step-count">1 of 3</span></div>
            <div className={`drop-zone ${source ? 'has-file' : ''}`} onDragOver={(event) => event.preventDefault()} onDrop={dropFile}>
              {source ? <div className="selected-file"><span className="selected-file-icon"><FileVideo size={25} aria-hidden="true" /></span><span className="selected-file-copy"><strong>{displayFileName(source)}</strong><small>{source.startsWith('http') ? 'YouTube link' : 'Local video selected'}</small></span><button type="button" className="button button-quiet" onClick={() => { setSource(''); setSourceDraft('') }} disabled={running}><X size={15} aria-hidden="true" /> Change</button></div> : <div className="drop-zone-empty"><span className="drop-icon"><FolderOpen size={24} aria-hidden="true" /></span><strong>Drop a video here</strong><span>or choose a file from your computer</span><button type="button" className="button button-secondary" onClick={chooseFile} disabled={running}><FolderOpen size={16} aria-hidden="true" /> Choose video</button></div>}
            </div>
            {fileError && <p className="error-message" role="alert">{fileError}</p>}
            <div className="link-input"><label htmlFor="source-link">Video link</label><input id="source-link" value={sourceDraft} onChange={(event) => { setFileError(null); setSourceDraft(event.target.value); setSource(event.target.value) }} placeholder="Paste a YouTube link" disabled={running || Boolean(source && !source.startsWith('http') && !sourceDraft)} /><span className="input-hint">{YOUTUBE_HELPER_COPY}</span></div>
          </section>
          <section className="choice-section" aria-labelledby="ai-heading"><div className="section-heading"><div><p className="section-eyebrow">Step 2</p><h2 id="ai-heading">Choose AI</h2><p className="section-caption">Pick where ClipGauge scores the strongest moments.</p></div><span className="step-count">2 of 3</span></div><div className="choice-card-grid">{AI_OPTIONS.map((option) => { const selected = option.id === 'other' ? provider !== 'clipgauge-local' && provider !== 'openrouter' : provider === option.id; return <button type="button" key={option.id} className={`choice-card choice-${option.tone} ${selected ? 'is-selected' : ''}`} onClick={() => chooseAI(option.id)} aria-pressed={selected}><span className="choice-card-icon"><Sparkles size={17} aria-hidden="true" /></span><span><strong>{option.name}</strong><small>{option.description}</small></span>{selected && <span className="choice-selected">Selected</span>}</button> })}</div><button type="button" className="text-button" onClick={() => onNavigate('providers')}>Manage AI providers <span aria-hidden="true">-&gt;</span></button></section>
          <section className="choice-section" aria-labelledby="caption-heading"><div className="section-heading"><div><p className="section-eyebrow">Step 3</p><h2 id="caption-heading">Choose caption style</h2><p className="section-caption">You can change this later in Review.</p></div><span className="step-count">3 of 3</span></div><div className="caption-choice-grid">{CAPTION_OPTIONS.map((option) => <button type="button" key={option.id} className={`caption-choice ${captions === option.id ? 'is-selected' : ''}`} onClick={() => setCaptions(option.id)} aria-pressed={captions === option.id}><span className={`caption-preview caption-${option.id}`}>Aa</span><span><strong>{option.name}</strong><small>{option.description}</small></span></button>)}</div></section>
          <section className="choice-section" aria-labelledby="quality-heading"><div className="section-heading"><div><p className="section-eyebrow">Scoring preference</p><h2 id="quality-heading">Choose scoring mode</h2><p className="section-caption">Cloud scoring never starts without your explicit mode choice.</p></div></div><div className="choice-card-grid">{QUALITY_OPTIONS.map((option) => { const disabled = option.id === 'private' ? readiness.locality === 'cloud' : readiness.locality === 'local' || !cloudAvailable; return <button type="button" key={option.id} className={`choice-card choice-neutral ${qualityMode === option.id ? 'is-selected' : ''}`} onClick={() => { if (!disabled) setQualityMode(option.id) }} aria-pressed={qualityMode === option.id} disabled={disabled} aria-disabled={disabled}><span className="choice-card-icon"><LockKeyhole size={17} aria-hidden="true" /></span><span><strong>{option.name}</strong><small>{option.description}</small></span>{qualityMode === option.id && <span className="choice-selected">Selected</span>}</button> })}</div>{qualityMode === 'private' && readiness.locality === 'local' && <p className="field-help" role="status">{providerName(provider)} scores here using {selectedModel}. No cloud provider receives candidate data.</p>}{qualityMode === 'private' && readiness.locality === 'cloud' && <p className="field-help" role="alert">Private mode requires a local provider. Choose ClipGauge Local, Ollama, or LM Studio.</p>}{!cloudAvailable && readiness.locality === 'local' && <p className="field-help" role="note">Configure a cloud provider and model in AI Providers before choosing Hybrid or Best Quality.</p>}{qualityMode !== 'private' && !cloudAvailable && readiness.locality === 'cloud' && <p className="field-help" role="note">{readiness.blocking_reasons.join('. ') || 'Configure a capable cloud provider and model'} before choosing {qualityMode === 'balanced' ? 'Balanced' : 'Best Quality'}.</p>}{qualityMode !== 'private' && !modeBlocked && <p className="field-help" role="note">What leaves this computer: candidate transcript, candidate metadata, and sampled images when visual scoring is supported. The full source file stays on this computer.</p>}</section>
          <section className="choice-section" aria-labelledby="output-heading"><div className="section-heading"><div><p className="section-eyebrow">Review preference</p><h2 id="output-heading">Choose how many options</h2><p className="section-caption">You can review more moments before exporting.</p></div></div><div className="choice-card-grid">{OUTPUT_OPTIONS.map((option) => <button type="button" key={option.id} className={outputPreference === option.id ? 'choice-card choice-neutral is-selected' : 'choice-card choice-neutral'} onClick={() => setOutputPreference(option.id)} aria-pressed={outputPreference === option.id}><span className="choice-card-icon"><Sparkles size={17} aria-hidden="true" /></span><span><strong>{option.name}</strong><small>{option.description}</small></span>{outputPreference === option.id && <span className="choice-selected">Selected</span>}</button>)}</div></section>
          <div className="create-action-row"><button type="button" className="button button-primary create-button" onClick={() => source.trim() && execution && onRun(source.trim(), execution.provider, captions, execution.model, undefined, undefined, undefined, undefined, execution.qualityMode, outputPreference)} disabled={running || !source.trim() || modeBlocked}><Play size={17} fill="currentColor" aria-hidden="true" />{running ? 'Creating clips...' : 'Create clips'}</button>{running && <button type="button" className="button button-quiet" onClick={onCancel} disabled={cancelling}>{cancelling ? 'Cancelling...' : 'Cancel'}</button>}<span className="action-note"><LockKeyhole size={14} aria-hidden="true" /> {providerName(provider)} - {selectedModel} ({readiness.locality})</span></div>
        </div>
        <aside className="create-side-column"><section className="side-note card-surface"><div className="side-note-icon"><Info size={18} aria-hidden="true" /></div><div><strong>What happens next?</strong><p>ClipGauge finds strong moments, reframes them for vertical video, and adds captions. You will get a review screen with every clip and its reasons.</p></div></section><section className="selected-summary card-surface"><p className="section-eyebrow">Your choices</p><div className="summary-row"><span>AI</span><strong>{selectedAI.name}</strong></div><div className="summary-row"><span>Mode</span><strong>{QUALITY_OPTIONS.find((option) => option.id === qualityMode)?.name}</strong></div><div className="summary-row"><span>Provider / model</span><strong>{providerName(provider)} - {selectedModel} ({readiness.locality})</strong></div><div className="summary-row"><span>Captions</span><strong>{selectedCaption.name}</strong></div><div className="summary-row"><span>Output</span><strong>Vertical 9:16</strong></div></section></aside>
      </div>
      {hasProgress && <section className="processing-panel card-surface" aria-live="polite"><div className="processing-header"><div><p className="section-eyebrow">Creating your clips</p><h2>{creatorHeadline(runState)}</h2></div><span className="elapsed-pill">{formatElapsed(elapsed)} elapsed</span></div><div className="processing-timeline" data-testid="processing-timeline">{STAGE_ORDER.map((stage) => { const current = stages[stage]; const done = Boolean(current && current.fraction >= 1); const active = Boolean(current && !done) || (!current && running && stage === STAGE_ORDER.find((item) => !stages[item])); return <div className={`timeline-step ${done ? 'is-done' : ''} ${active ? 'is-active' : ''}`} key={stage}><span className="timeline-dot" aria-hidden="true">{done ? 'check' : active ? 'dot' : ''}</span><span>{current?.displayStage ?? STAGE_LABELS[stage]}</span>{active && current?.operation && <small>{current.operation}</small>}</div> })}</div>{notice && <p className="inline-message" role="status">{notice}</p>}{error && <p className="error-message" role="alert">{error}</p>}{resultsLoadFailed && <button type="button" className="button button-secondary" onClick={onRetryResults}>Retry Review loading</button>}<details className="technical-disclosure"><summary>Show technical details</summary><div className="technical-progress-list">{Object.entries(stages).map(([name, stage]) => <div key={name}><span>{name}</span><span>{stage.message}</span></div>)}</div></details></section>}
    </div>
  )
}

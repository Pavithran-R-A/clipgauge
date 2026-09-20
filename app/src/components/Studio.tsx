import { useEffect, useRef, useState } from 'react'
import { FileVideo, FolderOpen, LockKeyhole, Play, Settings2, X } from 'lucide-react'
import { open } from '@tauri-apps/plugin-dialog'
import type { JobSummary, StageProgress } from '../types'
import { creatorHeadline, YOUTUBE_HELPER_COPY, type CreatorRunState } from '../creatorState'
import { friendlyErrorMessage } from '../errorMessaging'
import { evaluateProviderReadiness, resolveProviderExecution, type QualityMode } from '../providerContract'
import { createDisabledReason, executionSelection } from '../scoringState'
import { localModelDisplayName } from '../localModelState'

const STAGE_ORDER = ['ingest', 'asr', 'diarize', 'events', 'candidates', 'score', 'enrich', 'collections', 'camera', 'render']
const STAGE_LABELS: Record<string, string> = {
  ingest: 'Preparing video',
  asr: 'Transcribing speech',
  diarize: 'Identifying speakers',
  events: 'Understanding audio',
  candidates: 'Finding strong moments',
  score: 'Scoring clips',
  enrich: 'Writing clip titles',
  collections: 'Grouping a series',
  camera: 'Smart reframing',
  render: 'Creating clips',
}
const AI_OPTIONS = [
  { id: 'clipgauge-local', name: 'ClipGauge Local', description: 'Lightweight or Balanced. No cloud.', tone: 'teal' },
  { id: 'openrouter', name: 'OpenRouter Free', description: 'A free cloud route when available.', tone: 'blue' },
  { id: 'other', name: 'Other providers', description: 'Gemini, Groq, Ollama, and more.', tone: 'neutral' },
]
const DEFAULT_PROVIDER_MODELS: Record<string, string> = {
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
  { id: 'balanced', name: 'Hybrid', description: 'Local discovery plus your configured cloud provider.' },
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
  cpuResumeAvailable?: boolean
  notice: string | null
  onRun: (source: string, provider: string, captions: string, model?: string, endpoint?: string, auth?: string, secretHeader?: string, browserSession?: string, qualityMode?: string, outputPreference?: string, subtitlePath?: string, category?: string) => void
  localModelId?: string
  localModelReady?: boolean
  localModelLoading?: boolean
  localModelError?: string | null
  selectedLocalProvider?: string
  selectedCloudProvider?: string | null
  selectedCloudModel?: string | null
  cloudModelAvailable?: boolean
  cloudModelCompatible?: boolean
  cloudServiceReady?: boolean
  qualityMode?: QualityMode
  onQualityModeChange?: (mode: QualityMode) => void
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
  const safeSeconds = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0
  const minutes = Math.floor(safeSeconds / 60)
  return `${minutes}:${String(safeSeconds % 60).padStart(2, '0')}`
}

function readProviderModel(provider: string, localModelId?: string): string | undefined {
  if (provider === 'clipgauge-local' && localModelId) return localModelId
  try {
    return window.localStorage.getItem(`clipgauge.provider-model.${provider}`) ?? DEFAULT_PROVIDER_MODELS[provider]
  } catch {
    return DEFAULT_PROVIDER_MODELS[provider]
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

function displayModelName(provider: string, model?: string) {
  if (provider === 'clipgauge-local') {
    return localModelDisplayName(model)
  }
  if (!model) return 'Choose a model'
  if (model === 'openrouter/free') return 'Auto Free route'
  return model
}

export default function Studio({ running, runState, cancelling, startedAt, elapsedSeconds, stages, error, errorCode, cpuResumeAvailable = false, notice, resultsLoadFailed = false, onRetryResults, onRun, localModelId, localModelReady, localModelLoading = false, localModelError, selectedLocalProvider, selectedCloudProvider, selectedCloudModel, cloudModelAvailable, cloudModelCompatible, cloudServiceReady, qualityMode: controlledQualityMode, onQualityModeChange, providerModel, providerModelAvailable, providerModelCompatible, providerServiceReady, cloudConfigured = true, providerEndpoint, onContinueCpu, onRepairGpu, gpuRepairing, onCancel, onNavigate, selectedProvider, onSelectProvider }: Props) {
  const [source, setSource] = useState('')
  const [sourceDraft, setSourceDraft] = useState('')
  const [subtitlePath, setSubtitlePath] = useState<string | null>(null)
  const [category, setCategory] = useState('auto')
  const [captions, setCaptions] = useState('classic')
  const [internalQualityMode, setInternalQualityMode] = useState<QualityMode>('private')
  const [qualityModeOverride, setQualityModeOverride] = useState<QualityMode | null>(null)
  const [outputPreference, setOutputPreference] = useState<(typeof OUTPUT_OPTIONS)[number]['id']>('recommended')
  const [fileError, setFileError] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const mountedRef = useRef(true)
  const qualityMode = qualityModeOverride ?? controlledQualityMode ?? internalQualityMode
  const localProvider = selectedLocalProvider ?? (selectedProvider === 'ollama' || selectedProvider === 'lmstudio' || selectedProvider === 'clipgauge-local' ? selectedProvider : 'clipgauge-local')
  const cloudProvider = selectedCloudProvider ?? (selectedProvider && selectedProvider !== 'clipgauge-local' && selectedProvider !== 'ollama' && selectedProvider !== 'lmstudio' ? selectedProvider : 'openrouter')

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  useEffect(() => { setQualityModeOverride(null) }, [controlledQualityMode])

  useEffect(() => {
    if (!startedAt) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [startedAt])

  const elapsed = startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : elapsedSeconds ?? 0
  const provider = qualityMode === 'private' ? localProvider : cloudProvider
  const localModel = localProvider === 'clipgauge-local'
    ? localModelId ?? (localProvider === selectedProvider ? providerModel ?? readProviderModel(localProvider) : readProviderModel(localProvider))
    : (localProvider === selectedProvider ? providerModel ?? readProviderModel(localProvider) : readProviderModel(localProvider))
  const cloudModel = selectedCloudModel ?? (cloudProvider === selectedProvider ? providerModel ?? readProviderModel(cloudProvider) : readProviderModel(cloudProvider))
  const selectedModel = qualityMode === 'private' ? localModel : cloudModel
  const selectedModelLabel = displayModelName(provider, selectedModel)
  const localReadiness = evaluateProviderReadiness({ provider: localProvider, model: localModel, localModelReady: localModelLoading || Boolean(localModelError) ? false : localModelReady ?? (providerModelAvailable ?? Boolean(localModel)), serviceReady: providerServiceReady ?? true, runtimeReady: providerServiceReady ?? true })
  const cloudReadiness = evaluateProviderReadiness({ provider: cloudProvider, model: cloudModel, credentialReady: cloudConfigured, endpointReady: providerEndpoint ? true : undefined, modelAvailable: cloudModelAvailable ?? (cloudProvider === selectedProvider ? providerModelAvailable : undefined), modelCompatible: cloudModelCompatible ?? (cloudProvider === selectedProvider ? providerModelCompatible : undefined), serviceReady: cloudServiceReady ?? (cloudProvider === selectedProvider ? providerServiceReady : undefined) })
  const roleSelection = executionSelection({ selectedLocalProvider: localProvider, selectedLocalModel: localModel ?? null, selectedCloudProvider: cloudProvider, selectedCloudModel: cloudModel ?? null, qualityMode })
  const disabledReason = createDisabledReason({ source, qualityMode, localModelId: localModel, localModelReady: localReadiness.configured, localModelLoading, localModelError, cloudProvider, cloudModelId: roleSelection.model, cloudReady: cloudReadiness.configured, running })
  const modeBlocked = Boolean(disabledReason)
  const execution = !modeBlocked && roleSelection.provider && roleSelection.model ? resolveProviderExecution(roleSelection.provider, qualityMode, roleSelection.model) : null
  const hasProgress = running || Object.keys(stages).length > 0 || runState !== 'IDLE' || Boolean(error)
  const selectedModeDescription = qualityMode === 'private'
    ? `${providerName(localProvider)} · ${displayModelName(localProvider, localModel)}. No cloud provider receives candidate data.`
    : qualityMode === 'balanced'
      ? `${providerName(localProvider)} discovers candidates. ${providerName(cloudProvider)} scores them.`
      : `${providerName(cloudProvider)} scores the strongest candidates.`

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

  async function chooseSubtitle() {
    setFileError(null)
    try {
      const selected = await open({ multiple: false, directory: false, filters: [{ name: 'Subtitles', extensions: ['srt', 'vtt'] }] })
      if (!mountedRef.current) return
      if (typeof selected === 'string') setSubtitlePath(selected)
    } catch (error) {
      if (mountedRef.current) setFileError(friendlyErrorMessage(error, 'The subtitle picker could not open. Retry the action.'))
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
    if (id === localProvider) selectQualityMode('private')
    if (id === 'openrouter') selectQualityMode('balanced')
  }

  function selectQualityMode(mode: QualityMode) {
    setQualityModeOverride(mode)
    setInternalQualityMode(mode)
    onQualityModeChange?.(mode)
  }

  return (
    <div className="workspace-page create-page">
      {(errorCode === 'ASR_GPU_FALLBACK_REQUIRES_APPROVAL' || cpuResumeAvailable) && <section className="cpu-recovery card-surface" aria-live="polite"><div><strong>Choose how speech should continue</strong><p>GPU speech acceleration stopped. Repair it here, or approve slower CPU recovery.</p></div><div className="detail-actions"><button type="button" className="button button-secondary" onClick={onRepairGpu} disabled={gpuRepairing}>{gpuRepairing ? 'Repairing GPU acceleration...' : 'Repair GPU acceleration'}</button><button type="button" className="button button-secondary" onClick={onContinueCpu}>Continue in slower CPU mode</button></div></section>}
      <header className="page-header create-header"><div><p className="section-eyebrow">Create</p><h1>Create clips</h1><p className="page-lede">Turn a long video into vertical clips worth sharing.</p></div><div className="header-actions"><button type="button" className="button button-secondary" onClick={() => onNavigate('privacy')}><LockKeyhole size={16} aria-hidden="true" /> Privacy</button><button type="button" className="button button-secondary" onClick={() => onNavigate('setup')}><Settings2 size={16} aria-hidden="true" /> Setup</button></div></header>
      <div className="create-layout">
        <div className="create-main-column">
          <section className="add-video card-surface" aria-labelledby="add-video-heading">
            <div className="section-heading"><div><p className="section-eyebrow">Step 1</p><h2 id="add-video-heading">Add a video</h2><p className="section-caption">Choose a local file or paste a YouTube or Bilibili link.</p></div><span className="step-count">1 of 3</span></div>
            <div className={`drop-zone ${source ? 'has-file' : ''}`} onDragOver={(event) => event.preventDefault()} onDrop={dropFile}>
              {source ? <div className="selected-file"><span className="selected-file-icon"><FileVideo size={25} aria-hidden="true" /></span><span className="selected-file-copy"><strong>{displayFileName(source)}</strong><small>{source.startsWith('http') ? (source.toLowerCase().includes('bilibili') || source.toLowerCase().includes('b23.tv') ? 'Bilibili link' : 'YouTube link') : 'Local video selected'}</small></span><button type="button" className="button button-quiet" onClick={() => { setSource(''); setSourceDraft('') }} disabled={running}><X size={15} aria-hidden="true" /> Change</button></div> : <div className="drop-zone-empty"><span className="drop-icon"><FolderOpen size={24} aria-hidden="true" /></span><strong>Drop a video here</strong><span>or choose a file from your computer</span><button type="button" className="button button-secondary" onClick={chooseFile} disabled={running}><FolderOpen size={16} aria-hidden="true" /> Choose video</button></div>}
            </div>
            {fileError && <p className="error-message" role="alert">{fileError}</p>}
            <div className="link-input"><label htmlFor="source-link">Video link</label><input id="source-link" value={sourceDraft} onChange={(event) => { setFileError(null); setSourceDraft(event.target.value); setSource(event.target.value) }} placeholder="Paste a YouTube or Bilibili link" disabled={running || Boolean(source && !source.startsWith('http') && !sourceDraft)} /><span className="input-hint">{YOUTUBE_HELPER_COPY}</span></div>
            <div className="detail-actions"><button type="button" className="button button-secondary" onClick={() => void chooseSubtitle()} disabled={running}>Choose subtitle (.srt or .vtt)</button>{subtitlePath && <span className="field-help" role="status">Subtitle selected: {displayFileName(subtitlePath)}</span>}</div>
          </section>
          <section className="choice-section" aria-labelledby="ai-heading"><div className="section-heading"><div><p className="section-eyebrow">Step 2</p><h2 id="ai-heading">Choose AI</h2><p className="section-caption">Pick where ClipGauge scores the strongest moments.</p></div><span className="step-count">2 of 3</span></div><div className="choice-card-grid">{AI_OPTIONS.map((option) => { const selected = option.id === 'other' ? provider !== 'clipgauge-local' && provider !== 'openrouter' : provider === option.id; return <button type="button" key={option.id} className={`choice-card choice-${option.tone} ${selected ? 'is-selected' : ''}`} onClick={() => chooseAI(option.id)} aria-pressed={selected}><span><strong>{option.name}</strong><small>{option.description}</small></span>{selected && <span className="choice-selected">Selected</span>}</button> })}</div><button type="button" className="text-button" onClick={() => onNavigate('providers')}>Manage AI providers <span aria-hidden="true">-&gt;</span></button></section>
          <section className="choice-section" aria-labelledby="caption-heading"><div className="section-heading"><div><p className="section-eyebrow">Step 3</p><h2 id="caption-heading">Choose caption style</h2><p className="section-caption">You can change this later in Review.</p></div><span className="step-count">3 of 3</span></div><div className="caption-choice-grid">{CAPTION_OPTIONS.map((option) => <button type="button" key={option.id} className={`caption-choice ${captions === option.id ? 'is-selected' : ''}`} onClick={() => setCaptions(option.id)} aria-pressed={captions === option.id}><span className={`caption-preview caption-${option.id}`}>Aa</span><span><strong>{option.name}</strong><small>{option.description}</small></span></button>)}</div></section>
          <section className="choice-section" aria-labelledby="quality-heading"><div className="section-heading"><div><p className="section-eyebrow">Scoring</p><h2 id="quality-heading">Mode</h2><p className="section-caption">{selectedModeDescription}</p></div></div><div className="choice-card-grid" role="radiogroup" aria-label="Scoring mode">{QUALITY_OPTIONS.map((option) => <button type="button" role="radio" key={option.id} className={`choice-card choice-neutral ${qualityMode === option.id ? 'is-selected' : ''}`} onClick={() => selectQualityMode(option.id)} aria-checked={qualityMode === option.id}><span className="choice-card-icon"><LockKeyhole size={17} aria-hidden="true" /></span><span><strong>{option.name}</strong><small>{option.description}</small></span>{qualityMode === option.id && <span className="choice-selected">Selected</span>}</button>)}</div>{localModelLoading && <p className="field-help" role="status">Checking local model readiness…</p>}{localModelError && <p className="field-help" role="alert">{localModelError}</p>}{qualityMode === 'private' && localReadiness.configured && <p className="field-help" role="status">{providerName(localProvider)} scores locally using {displayModelName(localProvider, localModel)}. No cloud provider receives candidate data.</p>}{qualityMode === 'balanced' && !cloudReadiness.configured && <p className="field-help" role="status">Choose a cloud provider for Hybrid scoring. <button type="button" className="text-button" onClick={() => onNavigate('providers')}>Choose provider</button></p>}{qualityMode === 'best' && !cloudReadiness.configured && <p className="field-help" role="status">Choose a configured cloud provider for Best Quality. <button type="button" className="text-button" onClick={() => onNavigate('providers')}>Choose provider</button></p>}{qualityMode !== 'private' && cloudReadiness.configured && <p className="field-help" role="note">What leaves this computer: candidate transcript, metadata, and sampled images. The full source file stays local.</p>}</section>
          <section className="choice-section" aria-labelledby="category-heading"><div className="section-heading"><div><p className="section-eyebrow">Optional guidance</p><h2 id="category-heading">Content type</h2><p className="section-caption">Guides interpretation without changing measured evidence.</p></div></div><label className="field-label" htmlFor="content-category">Content category</label><select id="content-category" value={category} onChange={(event) => setCategory(event.target.value)} disabled={running}><option value="auto">Auto</option><option value="knowledge">Knowledge</option><option value="business">Business</option><option value="opinion">Opinion</option><option value="experience">Experience</option><option value="speech">Speech / interview</option><option value="content_review">Content review</option><option value="entertainment">Entertainment</option></select></section>
          <section className="choice-section" aria-labelledby="output-heading"><div className="section-heading"><div><p className="section-eyebrow">Review preference</p><h2 id="output-heading">Choose how many options</h2><p className="section-caption">You can review more moments before exporting.</p></div></div><div className="choice-card-grid">{OUTPUT_OPTIONS.map((option) => <button type="button" key={option.id} className={outputPreference === option.id ? 'choice-card choice-neutral is-selected' : 'choice-card choice-neutral'} onClick={() => setOutputPreference(option.id)} aria-pressed={outputPreference === option.id}><span><strong>{option.name}</strong><small>{option.description}</small></span>{outputPreference === option.id && <span className="choice-selected">Selected</span>}</button>)}</div></section>
          <div className="create-action-row"><button type="button" className="button button-primary create-button" onClick={() => source.trim() && execution && onRun(source.trim(), execution.provider, captions, execution.model, undefined, undefined, undefined, undefined, execution.qualityMode, outputPreference, subtitlePath ?? undefined, category)} disabled={Boolean(disabledReason)} aria-describedby={disabledReason ? 'create-disabled-reason' : undefined}><Play size={17} fill="currentColor" aria-hidden="true" />{running ? 'Creating clips...' : 'Create clips'}</button>{running && <button type="button" className="button button-quiet" onClick={onCancel} disabled={cancelling}>{cancelling ? 'Cancelling...' : 'Cancel'}</button>}<span className="action-note"><LockKeyhole size={14} aria-hidden="true" /> {providerName(provider)} · {selectedModelLabel}</span>{disabledReason && !running && <span id="create-disabled-reason" className="field-help" role="alert">{disabledReason}</span>}</div>
        </div>
      </div>
      {hasProgress && <section className="processing-panel card-surface" aria-live="polite"><div className="processing-header"><div><p className="section-eyebrow">Creating your clips</p><h2>{creatorHeadline(runState)}</h2></div><span className="elapsed-pill">{formatElapsed(elapsed)} elapsed</span></div><div className="processing-timeline" data-testid="processing-timeline">{STAGE_ORDER.map((stage) => { const current = stages[stage]; const done = Boolean(current && current.fraction >= 1); const active = Boolean(current && !done) || (!current && running && stage === STAGE_ORDER.find((item) => !stages[item])); return <div className={`timeline-step ${done ? 'is-done' : ''} ${active ? 'is-active' : ''}`} key={stage}><span className="timeline-dot" aria-hidden="true" /><span>{current?.displayStage ?? STAGE_LABELS[stage]}</span>{active && current?.operation && <small>{current.operation}</small>}</div> })}</div>{notice && <p className="inline-message" role="status">{notice}</p>}{error && <p className="error-message" role="alert">{error}</p>}{resultsLoadFailed && <button type="button" className="button button-secondary" onClick={onRetryResults}>Retry Review loading</button>}<details className="technical-disclosure"><summary>Show technical details</summary><div className="technical-progress-list">{Object.entries(stages).map(([name, stage]) => <div key={name}><span>{name}</span><span>{stage.message}</span></div>)}</div></details></section>}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { FileVideo, FolderOpen, Info, LockKeyhole, Play, Settings2, Sparkles, X } from 'lucide-react'
import { open } from '@tauri-apps/plugin-dialog'
import type { JobSummary, StageProgress } from '../types'
import { creatorHeadline, providerHelperCopy, sourceKind, YOUTUBE_HELPER_COPY, type CreatorRunState } from '../creatorState'

const STAGE_ORDER = ['ingest', 'asr', 'diarize', 'events', 'candidates', 'score', 'camera', 'render']
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
const AI_OPTIONS = [
  { id: 'clipgauge-local', name: 'ClipGauge Local', description: 'Private scoring on this computer.', tone: 'teal' },
  { id: 'openrouter', name: 'OpenRouter Free', description: 'A free cloud route when available.', tone: 'blue' },
  { id: 'other', name: 'Other providers', description: 'Gemini, Groq, Ollama, and more.', tone: 'neutral' }
]
const CAPTION_OPTIONS = [
  { id: 'classic', name: 'Clean', description: 'Readable and balanced.' },
  { id: 'beast', name: 'Bold Pop', description: 'High-energy emphasis.' },
  { id: 'hormozi', name: 'Punch', description: 'Strong words, strong rhythm.' },
  { id: 'minimal', name: 'Minimal', description: 'Quiet and focused.' }
]

interface Props {
  jobs: JobSummary[]
  running: boolean
  runState: CreatorRunState
  cancelling: boolean
  startedAt: number | null
  stages: Record<string, StageProgress>
  error: string | null
  errorCode: string | null
  notice: string | null
  onRun: (source: string, provider: string, captions: string, model?: string, endpoint?: string, auth?: string, secretHeader?: string, browserSession?: string) => void
  localModelId?: string
  onCancel: () => void
  onContinueCpu: () => void
  onNavigate: (section: 'providers' | 'setup' | 'privacy') => void
  selectedProvider: string
  onSelectProvider: (provider: string) => void
  onOpenJob: (id: string) => void
  onResume: (id: string) => void
}

function displayFileName(source: string) {
  return source.split(/[\\/]/).pop() || source
}

function formatElapsed(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}

export default function Studio({ running, runState, cancelling, startedAt, stages, error, errorCode, notice, onRun, localModelId, onContinueCpu, onCancel, onNavigate, selectedProvider, onSelectProvider }: Props) {
  const [source, setSource] = useState('')
  const provider = selectedProvider
  const [captions, setCaptions] = useState('classic')
  const [browserSession, setBrowserSession] = useState('')
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!startedAt) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [startedAt])

  const elapsed = startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : 0
  const selectedAI = AI_OPTIONS.find((option) => option.id === provider) ?? AI_OPTIONS[0]
  const selectedCaption = CAPTION_OPTIONS.find((option) => option.id === captions) ?? CAPTION_OPTIONS[0]
  const hasProgress = running || Object.keys(stages).length > 0 || runState !== 'IDLE' || Boolean(error)
  const youtubeAttention = sourceKind(source) === 'youtube' && Boolean(error)

  async function chooseFile() {
    const selected = await open({ multiple: false, directory: false, filters: [{ name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi'] }] })
    if (typeof selected === 'string') setSource(selected)
  }

  function dropFile(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault()
    if (!running) {
      const file = event.dataTransfer.files[0] as (File & { path?: string }) | undefined
      if (file?.path) setSource(file.path)
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
      {errorCode === 'ASR_GPU_FALLBACK_REQUIRES_APPROVAL' && <section className="cpu-recovery card-surface" aria-live="polite"><div><strong>Choose how speech should continue</strong><p>GPU speech acceleration failed. Repair it in Setup, or approve a slower CPU run for this video.</p></div><div className="detail-actions"><button type="button" className="button button-secondary" onClick={() => onNavigate('setup')}>Repair GPU acceleration</button><button type="button" className="button button-secondary" onClick={onContinueCpu}>Continue in slower CPU mode</button></div></section>}
      <header className="page-header create-header"><div><p className="section-eyebrow">Create</p><h1>Create clips</h1><p className="page-lede">Turn a long video into vertical clips worth sharing.</p></div><div className="header-actions"><button type="button" className="button button-secondary" onClick={() => onNavigate('privacy')}><LockKeyhole size={16} aria-hidden="true" /> Privacy</button><button type="button" className="button button-secondary" onClick={() => onNavigate('setup')}><Settings2 size={16} aria-hidden="true" /> Setup</button></div></header>
      <div className="create-layout">
        <div className="create-main-column">
          <section className="add-video card-surface" aria-labelledby="add-video-heading">
            <div className="section-heading"><div><p className="section-eyebrow">Step 1</p><h2 id="add-video-heading">Add a video</h2><p className="section-caption">Choose a local file or paste a public YouTube link.</p></div><span className="step-count">1 of 3</span></div>
            <div className={`drop-zone ${source ? 'has-file' : ''}`} onDragOver={(event) => event.preventDefault()} onDrop={dropFile}>
              {source ? <div className="selected-file"><span className="selected-file-icon"><FileVideo size={25} aria-hidden="true" /></span><span className="selected-file-copy"><strong>{displayFileName(source)}</strong><small>{source.startsWith('http') ? 'YouTube link' : 'Local video selected'}</small></span><button type="button" className="button button-quiet" onClick={() => setSource('')} disabled={running}><X size={15} aria-hidden="true" /> Change</button></div> : <div className="drop-zone-empty"><span className="drop-icon"><FolderOpen size={24} aria-hidden="true" /></span><strong>Drop a video here</strong><span>or choose a file from your computer</span><button type="button" className="button button-secondary" onClick={chooseFile} disabled={running}><FolderOpen size={16} aria-hidden="true" /> Choose video</button></div>}
            </div>
            <div className="link-input"><label htmlFor="source-link">Video link</label><input id="source-link" value={source.startsWith('http') ? source : ''} onChange={(event) => setSource(event.target.value)} placeholder="Paste a YouTube link" disabled={running || Boolean(source && !source.startsWith('http'))} /><span className="input-hint">{YOUTUBE_HELPER_COPY}</span></div>
          </section>
          <section className="choice-section" aria-labelledby="ai-heading"><div className="section-heading"><div><p className="section-eyebrow">Step 2</p><h2 id="ai-heading">Choose AI</h2><p className="section-caption">Pick where ClipGauge scores the strongest moments.</p></div><span className="step-count">2 of 3</span></div><div className="choice-card-grid">{AI_OPTIONS.map((option) => <button type="button" key={option.id} className={`choice-card choice-${option.tone} ${provider === option.id ? 'is-selected' : ''}`} onClick={() => chooseAI(option.id)} aria-pressed={provider === option.id}><span className="choice-card-icon"><Sparkles size={17} aria-hidden="true" /></span><span><strong>{option.name}</strong><small>{option.description}</small></span>{provider === option.id && <span className="choice-selected">Selected</span>}</button>)}</div><button type="button" className="text-button" onClick={() => onNavigate('providers')}>Manage AI providers <span aria-hidden="true">→</span></button></section>
          <section className="choice-section" aria-labelledby="caption-heading"><div className="section-heading"><div><p className="section-eyebrow">Step 3</p><h2 id="caption-heading">Choose caption style</h2><p className="section-caption">You can change this later in Review.</p></div><span className="step-count">3 of 3</span></div><div className="caption-choice-grid">{CAPTION_OPTIONS.map((option) => <button type="button" key={option.id} className={`caption-choice ${captions === option.id ? 'is-selected' : ''}`} onClick={() => setCaptions(option.id)} aria-pressed={captions === option.id}><span className={`caption-preview caption-${option.id}`}>Aa</span><span><strong>{option.name}</strong><small>{option.description}</small></span></button>)}</div></section>
          <div className="create-action-row"><button type="button" className="button button-primary create-button" onClick={() => source.trim() && onRun(source.trim(), provider === 'other' ? 'clipgauge-local' : provider, captions, provider === 'clipgauge-local' ? localModelId : undefined)} disabled={running || !source.trim()}><Play size={17} fill="currentColor" aria-hidden="true" />{running ? 'Creating clips…' : 'Create clips'}</button>{running && <button type="button" className="button button-quiet" onClick={onCancel} disabled={cancelling}>{cancelling ? 'Cancelling…' : 'Cancel'}</button>}<span className="action-note"><LockKeyhole size={14} aria-hidden="true" /> {providerHelperCopy(provider)}</span></div>
        </div>
        <aside className="create-side-column"><section className="side-note card-surface"><div className="side-note-icon"><Info size={18} aria-hidden="true" /></div><div><strong>What happens next?</strong><p>ClipGauge finds strong moments, reframes them for vertical video, and adds captions. You’ll get a review screen with every clip and its reasons.</p></div></section><section className="selected-summary card-surface"><p className="section-eyebrow">Your choices</p><div className="summary-row"><span>AI</span><strong>{selectedAI.name}</strong></div><div className="summary-row"><span>Captions</span><strong>{selectedCaption.name}</strong></div><div className="summary-row"><span>Output</span><strong>Vertical 9:16</strong></div></section></aside>
      </div>
      {hasProgress && <section className="processing-panel card-surface" aria-live="polite"><div className="processing-header"><div><p className="section-eyebrow">Creating your clips</p><h2>{creatorHeadline(runState)}</h2></div><span className="elapsed-pill">{formatElapsed(elapsed)} elapsed</span></div><div className="processing-timeline" data-testid="processing-timeline">{STAGE_ORDER.map((stage) => { const current = stages[stage]; const done = Boolean(current && current.fraction >= 1); const active = Boolean(current && !done) || (!current && running && stage === STAGE_ORDER.find((item) => !stages[item])); return <div className={`timeline-step ${done ? 'is-done' : ''} ${active ? 'is-active' : ''}`} key={stage}><span className="timeline-dot" aria-hidden="true">{done ? '✓' : active ? '•' : ''}</span><span>{current?.displayStage ?? STAGE_LABELS[stage]}</span>{active && current?.operation && <small>{current.operation}</small>}</div> })}</div>{notice && <p className="inline-message" role="status">{notice}</p>}{error && <p className="error-message" role="alert">{error}</p>}{youtubeAttention && <div className="youtube-recovery card-surface"><div><strong>YouTube playback verification was rejected</strong><p>ClipGauge itself is ready. You can retry later, or try browser-assisted compatibility after explicit approval. ClipGauge reads the selected browser session only for this operation and never saves cookies.</p></div><label className="browser-session-choice" htmlFor="browser-session">Browser session<select id="browser-session" value={browserSession} onChange={(event) => setBrowserSession(event.target.value)}><option value="">Choose a browser</option><option value="chrome">Chrome</option><option value="firefox">Firefox</option><option value="chromium">Chromium</option></select></label><div className="detail-actions"><button type="button" className="button button-secondary" onClick={() => onNavigate('setup')}>Open Setup</button><button type="button" className="button button-secondary" onClick={() => onRun(source.trim(), provider, captions, provider === 'clipgauge-local' ? localModelId : undefined, undefined, undefined, undefined, browserSession)} disabled={running || !browserSession}>Try browser-assisted YouTube compatibility</button><button type="button" className="button button-secondary" onClick={() => onRun(source.trim(), provider, captions, provider === 'clipgauge-local' ? localModelId : undefined)} disabled={running}>Retry later</button></div></div>}<details className="technical-disclosure"><summary>Show technical details</summary><div className="technical-progress-list">{Object.entries(stages).map(([name, stage]) => <div key={name}><span>{name}</span><span>{stage.message}</span></div>)}</div></details></section>}
    </div>
  )
}

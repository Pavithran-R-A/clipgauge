import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown, HardDrive, RotateCcw, ShieldCheck, Square, X } from 'lucide-react'
import { listen } from '@tauri-apps/api/event'
import { api } from '../api'
import type { LocalSetupInventory, ManagedAssetRow, SetupProgressEvent, YouTubeReadiness } from '../types'
import { assetLifecycleLabel, formatBytes, formatDuration, formatRate, meaningfulEta, progressPercent } from '../setupFormatting'
import { summarizeSetupQueue, type SetupQueueSummary } from '../setupState'

interface Props { onBack: () => void; onUseLocal?: () => void }

type Group = { id: string; title: string; description: string; prefixes: string[]; required: boolean }

const GROUPS: Group[] = [
  { id: 'video', title: 'Video tools', description: 'Read and render video with captions.', prefixes: ['runtime:ffmpeg:'], required: true },
  { id: 'speech', title: 'Speech recognition', description: 'Transcription and word timing.', prefixes: ['model:asr:', 'model:alignment:', 'data:nltk:', 'model:silero:'], required: true },
  { id: 'analysis', title: 'Speaker & audio analysis', description: 'Speaker detection, laughter, audio events, and smart camera signals.', prefixes: ['model:laughter:', 'model:panns:', 'model:campplus:', 'model:ultraface:', 'model:lr-asd:'], required: true },
  { id: 'youtube', title: 'YouTube support', description: 'Retrieve compatible public YouTube videos.', prefixes: ['runtime:yt-dlp:', 'runtime:node:', 'youtube:bgutil-provider:'], required: false }
]

const GROUP_COMMANDS: Record<string, string[]> = {
  video: ['install-ffmpeg'],
  speech: ['install-group', '--group', 'core:asr'],
  analysis: ['install-group', '--group', 'core:analysis'],
  youtube: ['install-group', '--group', 'core:youtube']
}

function assetsFor(inventory: LocalSetupInventory | null, group: Group): ManagedAssetRow[] {
  const rows = (inventory?.managed_assets ?? []).filter((asset) => group.prefixes.some((prefix) => asset.asset_id.startsWith(prefix)))
  const videoTools = inventory?.video_tools
  if (group.id !== 'video' || !videoTools?.ready || videoTools.managed_download_needed) return rows
  const base = rows[0] ?? {
    asset_id: 'runtime:ffmpeg:capability',
    display_name: 'Video tools',
    purpose: 'Reads, processes, and renders video clips with captions.',
    destination: '',
    url: '',
    size_bytes: 0,
    required: true,
    one_time: true,
    license: 'See upstream',
    source: videoTools.source,
    consent_group: 'core',
  }
  return [{
    ...base,
    installed: true,
    cached: true,
    size_bytes: 0,
    installed_size_bytes: 0,
    status: videoTools.source === 'system' ? 'reused-system' : 'ready',
    state: 'READY',
    source: videoTools.source,
    managed_download_needed: false,
    reason: videoTools.reason,
    capabilities: videoTools.capabilities,
  }]
}

function groupSize(rows: ManagedAssetRow[]): number | null {
  const known = rows.map((row) => row.size_bytes).filter((size) => Number.isFinite(size) && size > 0)
  return known.length ? known.reduce((sum, size) => sum + size, 0) : null
}

function groupState(rows: ManagedAssetRow[]): { label: string; tone: 'ready' | 'warning' | 'neutral'; ready: boolean } {
  if (!rows.length) return { label: 'Size calculated during setup', tone: 'neutral', ready: false }
  const repair = rows.some((row) => /repair|invalid|failed/i.test(`${row.status ?? ''} ${row.state ?? ''}`))
  if (repair) return { label: 'Update required', tone: 'warning', ready: false }
  if (rows.every((row) => row.installed)) {
    const system = rows.some((row) => row.source === 'system' || row.status === 'reused-system')
    return { label: system ? 'Ready · System' : 'Ready', tone: 'ready', ready: true }
  }
  if (rows.some((row) => row.installed)) return { label: 'Partially ready', tone: 'warning', ready: false }
  return { label: 'Download required', tone: 'neutral', ready: false }
}

function modelLabel(model: Record<string, unknown>, index: number): string {
  const name = String(model.display_name ?? model.asset_id ?? `Local model ${index + 1}`)
  return name.toLowerCase().includes('balanced') ? 'Balanced' : name.toLowerCase().includes('light') ? 'Lightweight' : name
}

export default function SetupCenter({ onBack, onUseLocal }: Props) {
  const [inventory, setInventory] = useState<LocalSetupInventory | null>(null)
  const [approved, setApproved] = useState(false)
  const [localApproved, setLocalApproved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [operationId, setOperationId] = useState<string | null>(null)
  const [progress, setProgress] = useState<SetupProgressEvent | null>(null)
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [message, setMessage] = useState<string | null>(null)
  const [lastArgs, setLastArgs] = useState<string[] | null>(null)
  const [showDetails, setShowDetails] = useState(false)
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null)
  const [queueSummary, setQueueSummary] = useState<SetupQueueSummary>({ state: 'pending', completed: 0, failed: 0, cancelled: false })
  const [youtubeStatus, setYoutubeStatus] = useState<YouTubeReadiness | null>(null)
  const [youtubeBusy, setYoutubeBusy] = useState(false)
  const queueRef = useRef<string[][]>([])
  const outcomesRef = useRef<Array<'success' | 'failed' | 'cancelled'>>([])
  const currentArgsRef = useRef<string[] | null>(null)
  const failedArgsRef = useRef<string[] | null>(null)
  const failedLabelsRef = useRef<string[]>([])

  const refreshYouTube = () => (api.youtubeReadiness?.() ?? Promise.resolve(null)).then((value) => setYoutubeStatus(value as YouTubeReadiness | null)).catch(() => setYoutubeStatus(null))

  const refresh = (modelId?: string) => api.setupInventory(modelId).then((value) => {
    const next = value as unknown as LocalSetupInventory
    setInventory(next)
    setSelectedModelId((current) => current ?? String(next.local_ai?.selected_model_id ?? next.models?.find((model) => String(model.display_name ?? '').toLowerCase().includes('balanced'))?.asset_id ?? next.models?.[0]?.asset_id ?? ''))
  }).catch(() => setMessage('Setup information is temporarily unavailable.'))

  useEffect(() => {
    refresh()
    void refreshYouTube()
    let stop: (() => void) | undefined
    void listen<SetupProgressEvent>('setup-event', ({ payload }) => {
      setProgress(payload)
      if (payload.event === 'terminal') {
        setOperationId(null)
        const outcome = payload.code === 'CANCELLED' ? 'cancelled' : payload.ok ? 'success' : 'failed'
        outcomesRef.current.push(outcome)
        if (outcome === 'failed') {
          failedArgsRef.current = currentArgsRef.current
          failedLabelsRef.current.push(String(payload.display_name ?? operationLabel(currentArgsRef.current)))
        }
        const next = queueRef.current.shift()
        if (next) {
          void begin(next, 'Continuing with the next approved component.')
        } else {
          setBusy(false)
          setStartedAt(null)
          const summary = summarizeSetupQueue(outcomesRef.current, 0)
          setProgress(summary.state === 'partial_failure' || summary.state === 'failed' ? { ...payload, event: 'terminal' } : null)
          setQueueSummary(summary)
          if (summary.state === 'partial_failure' || summary.state === 'failed') setLastArgs(failedArgsRef.current ?? lastArgs)
          const failedText = failedLabelsRef.current.length ? ` Failed: ${failedLabelsRef.current.join(', ')}.` : ''
          setMessage(summary.state === 'complete' ? 'Setup complete. Installed components will be reused for future videos.' : summary.state === 'cancelled' ? 'Setup cancelled. Verified assets remain available for reuse.' : summary.state === 'partial_failure' ? `Setup needs attention.${failedText} Retry the failed component.` : payload.message ?? `Setup needs attention.${failedText} Retry the failed component.`)
          void refresh()
          void refreshYouTube()
        }
      }
    }).then((unlisten) => { stop = unlisten })
    return () => stop?.()
  }, [])

  useEffect(() => {
    if (!startedAt) return
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [startedAt])

  const models = inventory?.models ?? []
  const selectedModel = models.find((model) => String(model.asset_id) === selectedModelId) ?? models[0]
  const groups = useMemo(() => GROUPS.map((group) => ({ ...group, rows: assetsFor(inventory, group), state: groupState(assetsFor(inventory, group)), size: groupSize(assetsFor(inventory, group)) })), [inventory])
  const requiredGroups = groups.filter((group) => group.required && !group.state.ready)
  const missingGroupTotal = requiredGroups.reduce((sum, group) => sum + (group.size ?? 0), 0)
  const selectedModelSize = Number(selectedModel?.size_bytes ?? 0)
  const selectedLifecycle = String(selectedModel?.lifecycle_state ?? '')
  const optionalLabel = selectedLifecycle === 'VERIFIED' ? 'Installed · 0 B additional' : selectedLifecycle === 'NEEDS_REPAIR' ? 'Needs repair' : selectedModelSize > 0 ? `${formatBytes(selectedModelSize)} additional` : 'Size calculated during setup'
  const allReady = requiredGroups.length === 0
  const localReady = Boolean(inventory?.local_ai?.runtime_ready && inventory?.local_ai?.model_ready)
  const localRuntimeReady = Boolean(inventory?.local_ai?.runtime_ready)
  const localModelReady = Boolean(inventory?.local_ai?.model_ready)
  const localStateLabel = localReady ? 'Ready' : inventory?.local_ai?.state === 'repair-required' ? 'Repair needed' : !localRuntimeReady ? 'Runtime needed' : 'Model needed'
  const setupPercent = progressPercent(progress)
  const setupEta = meaningfulEta(progress)
  const elapsed = progress?.elapsed_seconds ?? (startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : 0)
  const currentTotal = progress?.bytes_total ?? 0
  const currentDone = progress?.bytes_done ?? 0
  const canInstall = approved && !busy && !allReady
  const canInstallLocal = localApproved && !busy && !localReady

  async function testYouTube() {
    setYoutubeBusy(true)
    try { setYoutubeStatus(api.setupToolYouTubeTest ? await api.setupToolYouTubeTest() : null) } catch { setYoutubeStatus(null) }
    finally { setYoutubeBusy(false) }
  }

  function operationLabel(args: string[] | null): string {
    if (!args?.length) return 'component'
    if (args[0] === 'install-ffmpeg') return 'Video tools'
    if (args[0] === 'install-group') return String(args[2] ?? 'component')
    if (args[0] === 'download-model') return String(args[1] ?? 'local model')
    return args[0]
  }

  async function begin(args: string[], startedMessage: string) {
    currentArgsRef.current = args
    setBusy(true)
    setLastArgs(args)
    setStartedAt((value) => value ?? Date.now())
    setMessage(startedMessage)
    setProgress({ event: 'progress', operation: 'Preparing download…', message: 'Checking the approved components…', state: 'STARTING', elapsed_seconds: 0, one_time_download: true })
    try {
      setOperationId(await api.startSetup(args))
    } catch (error) {
      setBusy(false)
      setOperationId(null)
      setStartedAt(null)
      setProgress(null)
      setQueueSummary({ state: 'failed', completed: 0, failed: 1, cancelled: false })
      setMessage(`Setup could not start: ${String(error)}`)
    }
  }

  async function installRequired() {
    if (!canInstall) return
    outcomesRef.current = []
    failedArgsRef.current = null
    failedLabelsRef.current = []
    queueRef.current = requiredGroups.slice(1).map((group) => GROUP_COMMANDS[group.id])
    setQueueSummary({ state: 'running', completed: 0, failed: 0, cancelled: false })
    await begin(GROUP_COMMANDS[requiredGroups[0].id], 'Installing the required components in order.')
  }

  async function installLocal() {
    if (!canInstallLocal) return
    const commands: string[][] = []
    if (!localRuntimeReady) commands.push(['install-runtime'])
    if (!localModelReady && selectedModelId) commands.push(['download-model', selectedModelId])
    if (!commands.length) return
    outcomesRef.current = []
    failedArgsRef.current = null
    failedLabelsRef.current = []
    queueRef.current = commands.slice(1)
    setQueueSummary({ state: 'running', completed: 0, failed: 0, cancelled: false })
    await begin(commands[0], 'Installing ClipGauge Local in order.')
  }

  async function cancel() {
    if (!operationId) return
    queueRef.current = []
    try {
      await api.cancelSetup(operationId)
      setMessage('Cancelling. Completed files remain available for reuse.')
    } catch (error) {
      setMessage(`Could not cancel setup: ${String(error)}`)
    }
  }

  async function retry() {
    if (!lastArgs || busy) return
    outcomesRef.current = []
    failedArgsRef.current = null
    failedLabelsRef.current = []
    queueRef.current = []
    setQueueSummary({ state: 'running', completed: 0, failed: 0, cancelled: false })
    await begin(lastArgs, 'Retrying the selected component.')
  }

  useEffect(() => {
    if (selectedModelId) void refresh(selectedModelId)
  }, [selectedModelId])

  return (
    <div className="page-frame setup-page">
      <header className="page-header setup-header">
        <div><p className="section-eyebrow">Setup & Storage</p><h1>{allReady ? 'Ready to create clips' : 'Core setup needed'}</h1><p className="page-lede">{allReady ? 'Local files and configured providers can create clips. Optional local AI and YouTube support are shown separately below.' : `ClipGauge needs ${missingGroupTotal > 0 ? formatBytes(missingGroupTotal) : 'a few components'} of one-time downloads before core creation is ready.`}</p></div>
        <button type="button" className="button button-quiet" onClick={onBack}><X size={16} aria-hidden="true" /> Close</button>
      </header>
      <section className="setup-overview card-surface">
        <div className="setup-overview-main"><div className="setup-ready-icon"><Check size={20} aria-hidden="true" /></div><div><strong>{allReady ? 'Core components are ready.' : 'Core components need setup.'}</strong><p>Downloads are verified, resumable, and kept on this computer. Optional capabilities have their own status below.</p></div></div>
        <div className="storage-stats"><div><span>Required now</span><strong>{allReady ? 'Ready' : missingGroupTotal > 0 ? formatBytes(missingGroupTotal) : 'Size calculated during setup'}</strong></div><div><span>Already installed</span><strong>{formatBytes(inventory?.storage?.installed_bytes ?? inventory?.storage?.required_bytes)}</strong></div><div><span>Available disk</span><strong>{formatBytes(inventory?.storage?.available_bytes)}</strong></div></div>
        {!allReady && <div className="setup-install-row"><label className="consent-line" htmlFor="setup-approval"><input id="setup-approval" type="checkbox" checked={approved} onChange={(event) => setApproved(event.target.checked)} /><span>I approve these one-time downloads to this computer.</span></label><button type="button" className="button button-primary" onClick={installRequired} disabled={!canInstall}>{busy ? 'Installing…' : `Install required components · ${missingGroupTotal > 0 ? formatBytes(missingGroupTotal) : 'size calculated during setup'}`}</button></div>}
        {message && <p className="inline-message" role="status">{message}</p>}
      </section>
      <section className="component-section"><div className="section-heading"><div><p className="section-eyebrow">What ClipGauge uses</p><h2>One clear list</h2></div><span className="section-caption">{queueSummary.state === 'complete' ? 'Setup complete' : 'No hidden downloads'}</span></div><div className="component-grid">{groups.map((group) => <article className="component-card" key={group.id}><div className="component-card-heading"><span className="component-icon"><HardDrive size={17} aria-hidden="true" /></span><div><h3>{group.title}</h3><p>{group.description}</p></div><span className={`status-pill tone-${group.state.tone}`}><span className="status-dot" aria-hidden="true" />{group.state.label}</span></div><div className="component-card-footer"><span>{group.size ? formatBytes(group.size) : 'Size calculated during setup'}</span>{group.state.ready && <span className="reuse-note"><Check size={14} aria-hidden="true" /> {group.state.label.includes('System') ? 'System component reused' : 'Reused for future videos'}</span>}</div>{group.id === 'youtube' && <div className="component-card-actions"><span className="component-card-action-copy">{youtubeStatus?.reason ?? 'Checking YouTube support…'}</span><button type="button" className="button button-secondary" onClick={testYouTube} disabled={youtubeBusy}>{youtubeBusy ? 'Testing…' : 'Test YouTube support'}</button></div>}</article>)}</div></section>
      <section className="card-surface local-model-section"><div className="section-heading"><div><p className="section-eyebrow">Optional local AI</p><h2>Choose one model</h2><p className="section-caption">Score clips completely on this computer. Only the model you choose counts toward this estimate.</p></div><span className="soft-badge">{optionalLabel}</span></div><div className="model-choice-grid">{models.length ? models.map((model, index) => { const id = String(model.asset_id); const selected = id === String(selectedModel?.asset_id); return <label className={`model-choice ${selected ? 'is-selected' : ''}`} key={id}><input type="radio" name="local-model" value={id} checked={selected} onChange={() => setSelectedModelId(id)} /><span><strong>{modelLabel(model, index)}{index === 1 && <em>Recommended</em>}</strong><small>{model.purpose ?? 'A local model for clip scoring.'}</small><b>{(model as { lifecycle_label?: string }).lifecycle_label ?? 'Download required'}</b><span className="model-download-note">{Number((model as { required_download_bytes?: number }).required_download_bytes ?? model.size_bytes) > 0 ? `${formatBytes(Number((model as { required_download_bytes?: number }).required_download_bytes ?? model.size_bytes))} additional download` : 'No additional download required'}</span></span><span className="choice-check"><Check size={15} aria-hidden="true" /></span></label> }) : <p className="empty-state">Local model choices will appear after the component catalog loads.</p>}</div></section>
      <section className="card-surface local-install-action"><div className="section-heading"><div><p className="section-eyebrow">Local scoring</p><h2>{localReady ? 'ClipGauge Local is ready' : 'Run scoring locally'}</h2><p className="section-caption">Runs completely on this computer. No API key. Install the engine and the one model you choose.</p></div><span className={`status-pill tone-${localReady ? 'ready' : 'warning'}`}><span className="status-dot" aria-hidden="true" />{localStateLabel}</span></div>{localReady ? <button type="button" className="button button-secondary" onClick={onUseLocal}>Use ClipGauge Local</button> : <div className="setup-install-row"><label className="consent-line" htmlFor="local-approval"><input id="local-approval" type="checkbox" checked={localApproved} onChange={(event) => setLocalApproved(event.target.checked)} /><span>I approve this optional local-AI download.</span></label><button type="button" className="button button-primary" onClick={installLocal} disabled={!canInstallLocal}>{busy ? 'Installing…' : inventory?.local_ai?.action ?? 'Install ClipGauge Local'}</button></div>}</section>
      {progress && <section className="download-tray card-surface" aria-live="polite"><div className="download-tray-head"><div><p className="section-eyebrow">Download progress</p><h2>{progress.display_name ?? progress.operation ?? 'Preparing setup'}</h2></div><button type="button" className="button button-secondary" onClick={cancel} disabled={!operationId}><Square size={14} aria-hidden="true" /> Cancel</button></div><p className="download-message">{progress.message ?? 'Preparing verified components…'}</p><div className="progress-facts"><span>{currentTotal > 0 ? `${formatBytes(currentDone)} / ${formatBytes(currentTotal)}` : 'Calculating size…'}</span>{setupPercent != null && <span>{setupPercent}%</span>}{formatRate(progress.bytes_per_second) && <span>{formatRate(progress.bytes_per_second)}</span>}{setupEta && <span>{setupEta} remaining</span>}<span>{formatDuration(elapsed)} elapsed</span>{progress.one_time_download && <span>One-time download</span>}</div><div className="progress-track" role="progressbar" aria-label="Setup download progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={setupPercent ?? undefined}><div className={`progress-fill ${setupPercent == null ? 'is-indeterminate' : ''}`} style={setupPercent != null ? { width: `${setupPercent}%` } : undefined} /></div>{!busy && progress.event === 'terminal' && lastArgs && <button type="button" className="button button-secondary" onClick={retry}><RotateCcw size={15} aria-hidden="true" /> Retry component</button>}</section>}
      <section className="advanced-panel"><button type="button" className="advanced-toggle" onClick={() => setShowDetails((value) => !value)} aria-expanded={showDetails}><ChevronDown size={16} className={showDetails ? 'is-open' : ''} aria-hidden="true" /> Advanced component details</button>{showDetails && <div className="technical-table"><div className="technical-table-head"><span>Component</span><span>Download</span><span>State</span></div>{(inventory?.managed_assets ?? []).map((asset) => <div className="technical-row" key={asset.asset_id}><span><strong>{asset.display_name}</strong><small>{asset.asset_id} · {asset.license}</small></span><code>{asset.size_bytes > 0 ? formatBytes(asset.size_bytes) : 'unknown'}</code><span>{assetLifecycleLabel(asset)}</span></div>)}</div>}</section>
      <p className="page-footnote"><ShieldCheck size={15} aria-hidden="true" /> Components are downloaded only after your approval. Existing verified files are reused; credentials never belong in this folder.</p>
    </div>
  )
}

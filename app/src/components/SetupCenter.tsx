import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown, HardDrive, RotateCcw, ShieldCheck, Square, X } from 'lucide-react'
import { listen } from '@tauri-apps/api/event'
import { api } from '../api'
import type { LocalSetupInventory, ManagedAssetRow, SetupProgressEvent } from '../types'
import { assetLifecycleLabel, formatBytes, formatDuration, formatRate, meaningfulEta, progressPercent } from '../setupFormatting'

interface Props { onBack: () => void }

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
  return (inventory?.managed_assets ?? []).filter((asset) => group.prefixes.some((prefix) => asset.asset_id.startsWith(prefix)))
}

function groupSize(rows: ManagedAssetRow[]): number | null {
  const known = rows.map((row) => row.size_bytes).filter((size) => Number.isFinite(size) && size > 0)
  return known.length ? known.reduce((sum, size) => sum + size, 0) : null
}

function groupState(rows: ManagedAssetRow[]): { label: string; tone: 'ready' | 'warning' | 'neutral' } {
  if (!rows.length) return { label: 'Size calculated during setup', tone: 'neutral' }
  const repair = rows.some((row) => /repair|invalid|failed/i.test(`${row.status ?? ''} ${row.state ?? ''}`))
  if (repair) return { label: 'Repair needed', tone: 'warning' }
  if (rows.every((row) => row.installed)) return { label: 'Installed', tone: 'ready' }
  if (rows.some((row) => row.installed)) return { label: 'Partially ready', tone: 'warning' }
  return { label: 'Download required', tone: 'neutral' }
}

function modelLabel(model: Record<string, unknown>, index: number): string {
  const name = String(model.display_name ?? model.asset_id ?? `Local model ${index + 1}`)
  return name.toLowerCase().includes('balanced') ? 'Balanced' : name.toLowerCase().includes('light') ? 'Lightweight' : name
}

export default function SetupCenter({ onBack }: Props) {
  const [inventory, setInventory] = useState<LocalSetupInventory | null>(null)
  const [approved, setApproved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [operationId, setOperationId] = useState<string | null>(null)
  const [progress, setProgress] = useState<SetupProgressEvent | null>(null)
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [message, setMessage] = useState<string | null>(null)
  const [lastArgs, setLastArgs] = useState<string[] | null>(null)
  const [showDetails, setShowDetails] = useState(false)
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null)
  const queueRef = useRef<string[][]>([])

  const refresh = () => api.setupInventory().then((value) => {
    const next = value as unknown as LocalSetupInventory
    setInventory(next)
    setSelectedModelId((current) => current ?? String(next.models?.find((model) => String(model.display_name ?? '').toLowerCase().includes('balanced'))?.asset_id ?? next.models?.[0]?.asset_id ?? ''))
  }).catch(() => setMessage('Setup information is temporarily unavailable.'))

  useEffect(() => {
    refresh()
    let stop: (() => void) | undefined
    void listen<SetupProgressEvent>('setup-event', ({ payload }) => {
      setProgress(payload)
      if (payload.event === 'terminal') {
        setOperationId(null)
        const next = queueRef.current.shift()
        if (next) {
          void begin(next, queueRef.current.length > 0 ? 'Continuing with the next component.' : 'Finishing the approved setup plan.')
        } else {
          setBusy(false)
          setMessage(payload.ok ? 'Setup complete. Installed components will be reused for future videos.' : payload.message ?? 'Setup needs attention. You can retry the last component.')
          void refresh()
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
  const requiredGroups = groups.filter((group) => group.required && group.state.label !== 'Installed')
  const missingGroupTotal = requiredGroups.reduce((sum, group) => sum + (group.size ?? 0), 0)
  const selectedModelSize = Number(selectedModel?.size_bytes ?? 0)
  const optionalLabel = selectedModelSize > 0 ? formatBytes(selectedModelSize) : 'Size calculated during setup'
  const allReady = requiredGroups.length === 0
  const setupPercent = progressPercent(progress)
  const setupEta = meaningfulEta(progress)
  const elapsed = progress?.elapsed_seconds ?? (startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : 0)
  const currentTotal = progress?.bytes_total ?? 0
  const currentDone = progress?.bytes_done ?? 0
  const canInstall = approved && !busy && !allReady

  async function begin(args: string[], startedMessage: string) {
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
      setMessage(`Setup could not start: ${String(error)}`)
    }
  }

  async function installRequired() {
    if (!canInstall) return
    queueRef.current = requiredGroups.slice(1).map((group) => GROUP_COMMANDS[group.id])
    await begin(GROUP_COMMANDS[requiredGroups[0].id], 'Installing the required components in order.')
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
    await begin(lastArgs, 'Retrying the selected component.')
  }

  return (
    <div className="page-frame setup-page">
      <header className="page-header setup-header">
        <div><p className="section-eyebrow">Setup & Storage</p><h1>{allReady ? 'Ready to create clips' : 'Almost ready'}</h1><p className="page-lede">{allReady ? 'All required components are installed and will be reused for future videos.' : `ClipGauge needs ${missingGroupTotal > 0 ? formatBytes(missingGroupTotal) : 'a few components'} of one-time downloads before you can create clips.`}</p></div>
        <button type="button" className="button button-quiet" onClick={onBack}><X size={16} aria-hidden="true" /> Close</button>
      </header>
      <section className="setup-overview card-surface">
        <div className="setup-overview-main"><div className="setup-ready-icon"><Check size={20} aria-hidden="true" /></div><div><strong>{allReady ? 'Everything needed is here.' : 'One approval, then ClipGauge takes care of the rest.'}</strong><p>Downloads are verified, resumable, and kept on this computer.</p></div></div>
        <div className="storage-stats"><div><span>Required now</span><strong>{allReady ? 'Ready' : missingGroupTotal > 0 ? formatBytes(missingGroupTotal) : 'Size calculated during setup'}</strong></div><div><span>Already installed</span><strong>{formatBytes(inventory?.storage?.installed_bytes ?? inventory?.storage?.required_bytes)}</strong></div><div><span>Available disk</span><strong>{formatBytes(inventory?.storage?.available_bytes)}</strong></div></div>
        {!allReady && <div className="setup-install-row"><label className="consent-line" htmlFor="setup-approval"><input id="setup-approval" type="checkbox" checked={approved} onChange={(event) => setApproved(event.target.checked)} /><span>I approve these one-time downloads to this computer.</span></label><button type="button" className="button button-primary" onClick={installRequired} disabled={!canInstall}>{busy ? 'Installing…' : `Install required components · ${missingGroupTotal > 0 ? formatBytes(missingGroupTotal) : 'size calculated during setup'}`}</button></div>}
        {message && <p className="inline-message" role="status">{message}</p>}
      </section>
      <section className="component-section"><div className="section-heading"><div><p className="section-eyebrow">What ClipGauge uses</p><h2>One clear list</h2></div><span className="section-caption">No hidden downloads</span></div><div className="component-grid">{groups.map((group) => <article className="component-card" key={group.id}><div className="component-card-heading"><span className="component-icon"><HardDrive size={17} aria-hidden="true" /></span><div><h3>{group.title}</h3><p>{group.description}</p></div><span className={`status-pill tone-${group.state.tone}`}><span className="status-dot" aria-hidden="true" />{group.state.label}</span></div><div className="component-card-footer"><span>{group.size ? formatBytes(group.size) : 'Size calculated during setup'}</span>{group.state.label === 'Installed' && <span className="reuse-note"><Check size={14} aria-hidden="true" /> Reused for future videos</span>}</div></article>)}</div></section>
      <section className="card-surface local-model-section"><div className="section-heading"><div><p className="section-eyebrow">Optional local AI</p><h2>Choose one model</h2><p className="section-caption">Score clips completely on this computer. Only the model you choose counts toward this estimate.</p></div><span className="soft-badge">{optionalLabel}</span></div><div className="model-choice-grid">{models.length ? models.map((model, index) => { const id = String(model.asset_id); const selected = id === String(selectedModel?.asset_id); return <label className={`model-choice ${selected ? 'is-selected' : ''}`} key={id}><input type="radio" name="local-model" value={id} checked={selected} onChange={() => setSelectedModelId(id)} /><span><strong>{modelLabel(model, index)}{index === 1 && <em>Recommended</em>}</strong><small>{model.purpose ?? 'A local model for clip scoring.'}</small><b>{Number(model.size_bytes) > 0 ? formatBytes(Number(model.size_bytes)) : 'Size calculated during setup'}</b></span><span className="choice-check"><Check size={15} aria-hidden="true" /></span></label> }) : <p className="empty-state">Local model choices will appear after the component catalog loads.</p>}</div></section>
      {progress && <section className="download-tray card-surface" aria-live="polite"><div className="download-tray-head"><div><p className="section-eyebrow">Download progress</p><h2>{progress.display_name ?? progress.operation ?? 'Preparing setup'}</h2></div><button type="button" className="button button-secondary" onClick={cancel} disabled={!operationId}><Square size={14} aria-hidden="true" /> Cancel</button></div><p className="download-message">{progress.message ?? 'Preparing verified components…'}</p><div className="progress-facts"><span>{currentTotal > 0 ? `${formatBytes(currentDone)} / ${formatBytes(currentTotal)}` : 'Calculating size…'}</span>{setupPercent != null && <span>{setupPercent}%</span>}{formatRate(progress.bytes_per_second) && <span>{formatRate(progress.bytes_per_second)}</span>}{setupEta && <span>{setupEta} remaining</span>}<span>{formatDuration(elapsed)} elapsed</span>{progress.one_time_download && <span>One-time download</span>}</div><div className="progress-track" role="progressbar" aria-label="Setup download progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={setupPercent ?? undefined}><div className={`progress-fill ${setupPercent == null ? 'is-indeterminate' : ''}`} style={setupPercent != null ? { width: `${setupPercent}%` } : undefined} /></div>{!busy && progress.event === 'terminal' && lastArgs && <button type="button" className="button button-secondary" onClick={retry}><RotateCcw size={15} aria-hidden="true" /> Retry component</button>}</section>}
      <section className="advanced-panel"><button type="button" className="advanced-toggle" onClick={() => setShowDetails((value) => !value)} aria-expanded={showDetails}><ChevronDown size={16} className={showDetails ? 'is-open' : ''} aria-hidden="true" /> Advanced component details</button>{showDetails && <div className="technical-table"><div className="technical-table-head"><span>Component</span><span>Download</span><span>State</span></div>{(inventory?.managed_assets ?? []).map((asset) => <div className="technical-row" key={asset.asset_id}><span><strong>{asset.display_name}</strong><small>{asset.asset_id} · {asset.license}</small></span><code>{asset.size_bytes > 0 ? formatBytes(asset.size_bytes) : 'unknown'}</code><span>{assetLifecycleLabel(asset)}</span></div>)}</div>}</section>
      <p className="page-footnote"><ShieldCheck size={15} aria-hidden="true" /> Components are downloaded only after your approval. Existing verified files are reused; credentials never belong in this folder.</p>
    </div>
  )
}

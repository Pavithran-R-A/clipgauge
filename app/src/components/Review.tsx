import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { chooseExportDestination } from '../exportDestination'
import { traceMedia } from '../mediaDiagnostics'
import type { Clip, Collection, JobResults, RenderOutput } from '../types'
import ClipEditor from './ClipEditor'
import { isPlaybackUrl } from '../nativeValidation'
import { friendlyErrorMessage } from '../errorMessaging'
import { providerLocality } from '../providerContract'

const RESTYLE_PRESETS = ['classic', 'beast', 'hormozi', 'minimal', 'karaoke-pop']
const CAMERA_MODES: [string, string][] = [
  ['cut', 'hard cut on speaker change'],
  ['pan', 'eased pan between speakers'],
  ['locked', 'static crop, no switching']
]

interface Props {
  results: JobResults
  onBack: () => void
  onRestyle: (captions: string, camera: string) => void
}

const RULE_LABELS: Record<string, string> = {
  funny_no_laugh: 'Funny moment, no laughter signal',
  funny_corroborated: 'Laughter confirmed',
  shock_no_arousal: 'Surprise with a quiet delivery',
  bait_penalty: 'Engagement bait detected',
  heatmap_boost: 'People replayed this moment'
}

const CAPTION_LABELS: Record<string, string> = { classic: 'Clean', beast: 'Bold Pop', hormozi: 'Punch', minimal: 'Minimal', 'karaoke-pop': 'Karaoke' }
const SIGNAL_LABELS: Record<string, string> = {
  laughter: 'laughter',
  audio_events: 'audio events',
  arousal: 'vocal arousal',
  replay_heatmap: 'replay heatmap',
  visual: 'visual pass'
}

const CATEGORY_LABELS: Record<string, string> = {
  auto: 'Auto',
  knowledge: 'Knowledge',
  entertainment: 'Entertainment',
}

function fmtTime(t: number): string {
  const m = Math.floor(t / 60)
  const s = Math.floor(t % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

function adjustmentLabel(adj: Clip['adjustments'][number]): string {
  return 'factor' in adj ? `×${adj.factor}` : `${adj.bonus >= 0 ? '+' : ''}${adj.bonus}`
}

function adjustmentDirection(adj: Clip['adjustments'][number]): 'up' | 'down' {
  return 'factor' in adj ? (adj.factor >= 1 ? 'up' : 'down') : (adj.bonus >= 0 ? 'up' : 'down')
}

function qualityTier(score: number): string {
  if (score >= 85) return 'Exceptional'
  if (score >= 70) return 'Recommended'
  return 'Review manually'
}

function confidenceLabel(value: string): string {
  if (value === 'standard') return 'Standard model contract'
  if (value === 'local-estimate') return 'Local estimate'
  if (value === 'degraded') return 'Degraded signals'
  return value || 'Not reported'
}

function clipIndexForOutput(output: RenderOutput, clips: Clip[]): number | null {
  if (output.clip_id) {
    const matchingIndexes = clips.reduce<number[]>((indexes, clip, index) => (
      clip.clip_id === output.clip_id ? [...indexes, index] : indexes
    ), [])
    return matchingIndexes.length === 1 ? matchingIndexes[0] : null
  }
  return output.clip
}

interface ReviewClipPair {
  out: RenderOutput
  scoreClip: Clip
  scoreClipIndex: number
  renderClipNumber: number
  identity: string
}

function pairForOutput(output: RenderOutput, clips: Clip[]): ReviewClipPair | null {
  const scoreClipIndex = clipIndexForOutput(output, clips)
  if (scoreClipIndex === null || scoreClipIndex < 0) return null
  const scoreClip = clips[scoreClipIndex]
  if (!scoreClip) return null
  return {
    out: output,
    scoreClip,
    scoreClipIndex,
    renderClipNumber: output.clip,
    identity: output.clip_id ?? `render:${output.clip}`,
  }
}

function clipCountLabel(count: number): string {
  return `${count} clip${count === 1 ? '' : 's'}`
}

function categoryLabel(category: string | undefined): string {
  const normalized = category?.trim().toLowerCase() || 'auto'
  return CATEGORY_LABELS[normalized] ?? normalized.replace(/[-_]/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function collectionSourceLabel(source: Collection['source']): string {
  if (source === 'ai') return 'Suggested'
  if (source === 'deterministic') return 'Deterministic fallback'
  return 'Manual'
}

function scoringLocality(results: JobResults): string {
  const provider = results.score?.provider_kind ?? results.score?.llm_mode ?? ''
  return providerLocality(provider) === 'local' ? 'scored locally' : 'AI-assisted scoring'
}

function OtherMoments({ moments, jobId }: { moments: NonNullable<JobResults['score']>['borderline_candidates']; jobId: string }) {
  const [previewError, setPreviewError] = useState<string | null>(null)
  const mountedRef = useRef(true)
  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])
  if (!moments?.length) return null
  async function preview(moment: { start: number; end: number }) {
    setPreviewError(null)
    try {
      const url = await api.requestPlaybackUrl(jobId, 'source')
      if (!isPlaybackUrl(url)) throw new Error('Playback URL is malformed.')
      if (!mountedRef.current) return
      window.open(`${url}#t=${moment.start},${moment.end}`, '_blank', 'noopener,noreferrer')
    } catch (error) {
      if (mountedRef.current) setPreviewError(friendlyErrorMessage(error, 'Preview unavailable. Retry the preview.'))
    }
  }
  return <details className="other-moments"><summary>Other moments ({moments.length})</summary>{previewError && <p className="field-help" role="alert">{previewError}</p>}<div className="other-moments-list">{moments.map((moment, index) => <div className="other-moment" key={`${moment.start}-${moment.end}-${index}`}><div><strong>{fmtTime(moment.start)}–{fmtTime(moment.end)}</strong><small>Score {Math.round(moment.recommendation_score)} · {moment.reasons?.join(', ') ?? 'Below the recommendation bar'}</small></div><button type="button" className="button button-secondary" onClick={() => void preview(moment)}>Preview source</button></div>)}</div></details>
}

export default function Review({ results, onBack, onRestyle }: Props) {
  const outputs = results.render?.outputs ?? []
  const clips = results.score?.clips ?? []
  const [selected, setSelected] = useState(0)
  const [exported, setExported] = useState<Record<string, string>>({})
  const currentPreset = results.render?.caption_preset ?? 'classic'
  const [restylePreset, setRestylePreset] = useState(currentPreset)
  const [restyleCamera, setRestyleCamera] = useState('cut')
  const [editing, setEditing] = useState<number | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [mediaState, setMediaState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [mediaUrl, setMediaUrl] = useState<string | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)
  const [titleDraft, setTitleDraft] = useState('')
  const [titleEditing, setTitleEditing] = useState(false)
  const [titleBusy, setTitleBusy] = useState(false)
  const [titleOverrides, setTitleOverrides] = useState<Record<string, { title: string; title_source: string }>>({})
  const [collections, setCollections] = useState<Collection[]>(results.collections?.collections ?? [])
  const [collectionDialogOpen, setCollectionDialogOpen] = useState(false)
  const [collectionTitle, setCollectionTitle] = useState('New collection')
  const [selectedCollectionClipIds, setSelectedCollectionClipIds] = useState<string[]>([])
  const [collectionEditorId, setCollectionEditorId] = useState<string | null>(null)
  const [collectionRenameId, setCollectionRenameId] = useState<string | null>(null)
  const [collectionRenameDraft, setCollectionRenameDraft] = useState('')
  const [creatorBusy, setCreatorBusy] = useState(false)
  const [creatorError, setCreatorError] = useState<string | null>(null)
  const mountedRef = useRef(true)
  const styleChanged = restylePreset !== currentPreset || restyleCamera !== 'cut'
  const borderline = results.score?.borderline_candidates

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  const pair = useMemo(() => {
    const out = outputs[selected]
    return out ? pairForOutput(out, clips) : null
  }, [outputs, clips, selected])

  const selectedClipId = pair?.scoreClip.clip_id ?? null
  const titleOverride = selectedClipId ? titleOverrides[selectedClipId] : undefined
  const selectedTitle = titleOverride?.title ?? pair?.scoreClip.title ?? ''
  const selectedTitleSource = titleOverride?.title_source ?? pair?.scoreClip.title_source ?? 'deterministic'
  const creatorClips = results.score?.clips ?? results.enrich?.clips ?? []

  useEffect(() => {
    setTitleDraft(selectedTitle)
    setTitleEditing(false)
  }, [selectedClipId, selectedTitle])

  useEffect(() => {
    setCollections(results.collections?.collections ?? [])
  }, [results.job_id, results.collections])

  function applyCollectionResult(result: Awaited<ReturnType<typeof api.listCollections>> | Awaited<ReturnType<typeof api.createCollection>>) {
    if (result.collections) setCollections(result.collections)
    if (result.collection) {
      setCollections((current) => current.some((item) => item.id === result.collection?.id)
        ? current.map((item) => item.id === result.collection?.id ? result.collection! : item)
        : [...current, result.collection!])
    }
  }

  async function saveTitle() {
    if (!selectedClipId || !titleDraft.trim()) return
    setTitleBusy(true)
    setCreatorError(null)
    try {
      const result = await api.setClipTitle(results.job_id, selectedClipId, titleDraft.trim())
      if (!mountedRef.current) return
      setTitleOverrides((current) => ({
        ...current,
        [selectedClipId]: { title: result.title ?? titleDraft.trim(), title_source: result.title_source ?? 'user' },
      }))
      setTitleDraft(result.title ?? titleDraft.trim())
      setTitleEditing(false)
    } catch (error) {
      if (mountedRef.current) setCreatorError(friendlyErrorMessage(error, 'Title could not be saved.'))
    } finally {
      if (mountedRef.current) setTitleBusy(false)
    }
  }

  async function resetTitle() {
    if (!selectedClipId) return
    setTitleBusy(true)
    setCreatorError(null)
    try {
      const result = await api.resetClipTitle(results.job_id, selectedClipId)
      if (!mountedRef.current) return
      setTitleOverrides((current) => ({
        ...current,
        [selectedClipId]: { title: result.title ?? pair?.scoreClip.title ?? '', title_source: result.title_source ?? 'model' },
      }))
      setTitleDraft(result.title ?? pair?.scoreClip.title ?? '')
      setTitleEditing(false)
    } catch (error) {
      if (mountedRef.current) setCreatorError(friendlyErrorMessage(error, 'Title could not be reset.'))
    } finally {
      if (mountedRef.current) setTitleBusy(false)
    }
  }

  async function createCollection() {
    if (selectedCollectionClipIds.length < 2 || !collectionTitle.trim()) return
    setCreatorBusy(true)
    setCreatorError(null)
    try {
      const result = await api.createCollection(results.job_id, collectionTitle.trim(), selectedCollectionClipIds)
      if (!mountedRef.current) return
      applyCollectionResult(result)
      setCollectionDialogOpen(false)
      setCollectionTitle('New collection')
      setSelectedCollectionClipIds([])
    } catch (error) {
      if (mountedRef.current) setCreatorError(friendlyErrorMessage(error, 'Collection could not be created.'))
    } finally {
      if (mountedRef.current) setCreatorBusy(false)
    }
  }

  async function updateCollection(collection: Collection, title?: string, clipIds?: string[]) {
    const nextClipIds = clipIds ?? collection.clip_ids
    if (nextClipIds.length < 2) return
    setCreatorBusy(true)
    setCreatorError(null)
    try {
      const result = await api.updateCollection(results.job_id, collection.id, title, nextClipIds)
      if (!mountedRef.current) return
      applyCollectionResult(result)
      if (result.collection === undefined) {
        setCollections((current) => current.map((item) => item.id === collection.id
          ? { ...item, ...(title === undefined ? {} : { title }), clip_ids: [...nextClipIds], user_edited: true, source: 'manual' }
          : item))
      }
      setCollectionEditorId(null)
      setCollectionRenameId(null)
    } catch (error) {
      if (mountedRef.current) setCreatorError(friendlyErrorMessage(error, 'Collection could not be updated.'))
    } finally {
      if (mountedRef.current) setCreatorBusy(false)
    }
  }

  async function deleteCollection(collection: Collection) {
    setCreatorBusy(true)
    setCreatorError(null)
    try {
      await api.deleteCollection(results.job_id, collection.id)
      if (mountedRef.current) setCollections((current) => current.filter((item) => item.id !== collection.id))
    } catch (error) {
      if (mountedRef.current) setCreatorError(friendlyErrorMessage(error, 'Collection could not be deleted.'))
    } finally {
      if (mountedRef.current) setCreatorBusy(false)
    }
  }

  async function moveCollectionClip(collection: Collection, index: number, direction: -1 | 1) {
    const target = index + direction
    if (target < 0 || target >= collection.clip_ids.length) return
    const clipIds = [...collection.clip_ids]
    ;[clipIds[index], clipIds[target]] = [clipIds[target], clipIds[index]]
    await updateCollection(collection, undefined, clipIds)
  }

  async function renderCollection(collection: Collection) {
    setCreatorBusy(true)
    setCreatorError(null)
    try {
      const result = await api.renderCollection(results.job_id, collection.id)
      if (!mountedRef.current) return
      if (result.path) setCollections((current) => current.map((item) => item.id === collection.id ? { ...item, render_path: result.path } : item))
    } catch (error) {
      if (mountedRef.current) setCreatorError(friendlyErrorMessage(error, 'Collection render could not be completed.'))
    } finally {
      if (mountedRef.current) setCreatorBusy(false)
    }
  }

  async function regenerateCollections() {
    setCreatorBusy(true)
    setCreatorError(null)
    try {
      const result = await api.regenerateCollections(results.job_id)
      if (mountedRef.current) applyCollectionResult(result)
    } catch (error) {
      if (mountedRef.current) setCreatorError(friendlyErrorMessage(error, 'Collection suggestions could not be regenerated.'))
    } finally {
      if (mountedRef.current) setCreatorBusy(false)
    }
  }

  const artifactAvailable = Boolean(
    pair?.out.path && (pair.out.artifact_status === undefined || pair.out.artifact_status === 'available')
  )

  useEffect(() => {
    setMediaState(artifactAvailable ? 'loading' : 'error')
  }, [artifactAvailable, pair?.out.path, pair?.out.artifact_status, reloadKey])

  useEffect(() => {
    let active = true
    setMediaUrl(null)
    if (!artifactAvailable || !pair) return () => { active = false }
    api.requestPlaybackUrl(results.job_id, 'render', pair.renderClipNumber)
      .then((url) => {
        if (!isPlaybackUrl(url)) throw new Error('Playback URL is malformed.')
        if (active) setMediaUrl(url)
      })
      .catch(() => {
        if (active) setMediaState('error')
      })
    return () => { active = false }
  }, [artifactAvailable, pair?.renderClipNumber, pair?.out.path, reloadKey, results.job_id])

  async function doExport(clipPair: ReviewClipPair) {
    if (!clipPair.out.path || !artifactAvailable) return
    setExportError(null)
    try {
      const suggestedTitle = `${results.ingest?.title ?? 'clip'} ${fmtTime(clipPair.scoreClip.start)}`
      const dest = await chooseExportDestination({
        jobId: results.job_id,
        clip: clipPair.renderClipNumber,
        suggestedTitle,
      })
      if (!dest) return
      if (!mountedRef.current) return
      setExported((prev) => ({ ...prev, [clipPair.identity]: dest }))
    } catch (error) {
      if (mountedRef.current) setExportError(friendlyErrorMessage(error, 'Export could not be completed. Retry the export.'))
    }
  }

  if (editing !== null) {
    return (
      <div className="review">
        <ClipEditor
          key={`${editing}-${reloadKey}`}
          jobId={results.job_id}
          clipIndex={editing}
          onClose={() => setEditing(null)}
          onRendered={() => setReloadKey((k) => k + 1)}
        />
      </div>
    )
  }

  if (results.outcome === 'SUCCESS_NO_RECOMMENDATIONS' || outputs.length === 0) {
    const counts = results.score?.counts
    return (
      <div className="review">
        <header className="review-head">
          <button className="btn-ghost" onClick={onBack}>← studio</button>
          <div className="review-title-block">
            <h1 className="review-title">Analysis complete</h1>
            <p className="review-sub mono">No recommended clips</p>
          </div>
        </header>
        <section className="empty-review card-surface" aria-live="polite" data-testid="no-recommendations">
          <p className="section-eyebrow">No recommended clips</p>
          <h2>We did not find a moment that met ClipGauge&apos;s quality bar.</h2>
          <p>{counts?.scored_count ?? results.score?.scored_count ?? 0} moments were evaluated.</p>
          {results.score?.best_candidate && <p>Best evaluated moment: {fmtTime(results.score.best_candidate.start)}–{fmtTime(results.score.best_candidate.end)} · score {Math.round(results.score.best_candidate.recommendation_score)}.</p>}
          <OtherMoments moments={borderline} jobId={results.job_id} />
          <button className="button button-primary" onClick={onBack}>Create another set</button>
        </section>
      </div>
    )
  }

  return (
    <div className="review">
      <header className="review-head">
        <button className="btn-ghost" onClick={onBack}>
          ← studio
        </button>
        <div className="review-title-block">
          <h1 className="review-title">{results.ingest?.title ?? results.job_id}</h1>
          <p className="review-sub mono">
            {clipCountLabel(outputs.length)} · {scoringLocality(results)} ·{' '}
            {results.candidates?.heatmap_present ? 'replay signals included' : 'audio and visual signals'}
          </p>
        </div>
      </header>

      <div className="restyle-bar">
        <span className="opt-label">captions</span>
        {RESTYLE_PRESETS.map((preset) => (
          <button
            key={preset}
            className={`opt ${restylePreset === preset ? 'opt-on' : ''}`}
            onClick={() => setRestylePreset(preset)}
          >
            {CAPTION_LABELS[preset] ?? preset}
          </button>
        ))}
        <span className="opt-label" style={{ marginLeft: 18 }}>
          camera
        </span>
        {CAMERA_MODES.map(([mode, hint]) => (
          <button
            key={mode}
            className={`opt ${restyleCamera === mode ? 'opt-on' : ''}`}
            onClick={() => setRestyleCamera(mode)}
            title={hint}
          >
            {mode}
          </button>
        ))}
        <button
          className="btn-primary restyle-go"
          disabled={!styleChanged}
          onClick={() => onRestyle(restylePreset, restyleCamera)}
          title="re-renders only the changed stages — scores and cuts stay"
        >
          Apply changes
        </button>
      </div>

      <div className="filmstrip">
        {outputs.map((out, i) => {
          const clipPair = pairForOutput(out, clips)
          const clip = clipPair?.scoreClip
          return (
            <button
              key={`${out.clip_id ?? 'legacy'}-${i}`}
              className={`film-card ${i === selected ? 'film-on' : ''}`}
              onClick={() => setSelected(i)}
              disabled={clipPair === null}
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <span className="film-score mono">{clip ? Math.round(clip.recommendation_score ?? clip.score ?? out.score) : '—'}</span>
              <span className="film-time mono">{clip ? fmtTime(clip.start) : 'Unavailable'}</span>
              <span className="film-platform">{out.best_platform}</span>
            </button>
          )
        })}
      </div>
      <OtherMoments moments={borderline} jobId={results.job_id} />
      <section className="card-surface" aria-labelledby="collections-heading">
        <p className="section-eyebrow">Series / Collections</p>
        <div className="page-header" style={{ marginBottom: 12 }}>
          <div>
            <h2 id="collections-heading">Collections</h2>
            <p className="audit-fine">Content type {'·'} {categoryLabel(results.enrich?.category ?? results.collections?.category)}</p>
          </div>
          <div className="monitor-actions">
            <button type="button" className="button-secondary" onClick={() => { setCollectionDialogOpen(true); setCreatorError(null) }}>Create collection</button>
            <button type="button" className="button-secondary" onClick={() => void regenerateCollections()} disabled={creatorBusy}>Regenerate suggestions</button>
          </div>
        </div>
        {creatorError && <p className="field-help" role="alert">{creatorError}</p>}
        {collections.length === 0 && <p className="audit-fine">No collections yet.</p>}
        {collections.map((collection) => {
          const editingClips = collectionEditorId === collection.id
          const renaming = collectionRenameId === collection.id
          return (
            <div className="ledger-row" key={collection.id}>
              <div style={{ minWidth: 0, flex: 1 }}>
                {renaming ? <div className="monitor-actions"><input aria-label={`Rename ${collection.title}`} value={collectionRenameDraft} onChange={(event) => setCollectionRenameDraft(event.target.value)} /><button type="button" className="button-secondary" onClick={() => void updateCollection(collection, collectionRenameDraft.trim())} disabled={!collectionRenameDraft.trim() || creatorBusy}>Save name</button><button type="button" className="button-quiet" onClick={() => setCollectionRenameId(null)}>Cancel</button></div> : <strong>{collection.title}</strong>}
                <span className="ledger-reason">{collection.clip_ids.length} clips Â· <span className="chip chip-green">{collectionSourceLabel(collection.source)}</span></span>
                {collection.summary && <span className="ledger-reason">{collection.summary}</span>}
                <div className="monitor-actions">
                  <button type="button" className="button-quiet" onClick={() => { setCollectionRenameId(collection.id); setCollectionRenameDraft(collection.title) }}>Rename</button>
                  <button type="button" className="button-quiet" onClick={() => { setCollectionEditorId(editingClips ? null : collection.id); setSelectedCollectionClipIds(collection.clip_ids) }}>Add clip</button>
                  <button type="button" className="button-quiet" onClick={() => void renderCollection(collection)} disabled={creatorBusy}>Render series</button>
                  <button type="button" className="button-quiet" onClick={() => void deleteCollection(collection)} disabled={creatorBusy}>Delete</button>
                </div>
                {editingClips && <div className="choice-section">{creatorClips.filter((clip) => clip.clip_id).map((clip) => { const clipId = clip.clip_id!; return <label key={clipId} className="sig"><input type="checkbox" checked={selectedCollectionClipIds.includes(clipId)} onChange={(event) => setSelectedCollectionClipIds((current) => event.target.checked ? [...new Set([...current, clipId])] : current.filter((id) => id !== clipId))} />{clip.title ?? clipId}</label> })}<button type="button" className="button-secondary" onClick={() => void updateCollection(collection, undefined, selectedCollectionClipIds)} disabled={selectedCollectionClipIds.length < 2 || creatorBusy}>Save clips</button></div>}
                <ol className="ledger">{collection.clip_ids.map((clipId, index) => { const clip = creatorClips.find((item) => item.clip_id === clipId); return <li className="ledger-row" key={clipId}><span>{clip?.title ?? clipId}</span><div className="monitor-actions"><button type="button" className="button-quiet" onClick={() => void updateCollection(collection, undefined, collection.clip_ids.filter((id) => id !== clipId))} disabled={collection.clip_ids.length <= 2 || creatorBusy}>Remove</button><button type="button" className="button-quiet" onClick={() => void moveCollectionClip(collection, index, -1)} disabled={index === 0 || creatorBusy}>Move up</button><button type="button" className="button-quiet" onClick={() => void moveCollectionClip(collection, index, 1)} disabled={index === collection.clip_ids.length - 1 || creatorBusy}>Move down</button></div></li> })}</ol>
                {collection.render_path && <div className="monitor-actions"><video className="monitor" controls playsInline src={api.fileUrl(collection.render_path)} /><span className="mono export-path">{collection.render_path}</span></div>}
              </div>
            </div>
          )
        })}
      </section>
      {collectionDialogOpen && <div className="modal-scrim" role="presentation"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="create-collection-heading"><div className="modal-head"><div><p className="section-eyebrow">Manual collection</p><h2 id="create-collection-heading">Create collection</h2></div><button type="button" className="button-quiet" onClick={() => setCollectionDialogOpen(false)}>Close</button></div><label className="field-stack">Collection title<input value={collectionTitle} onChange={(event) => setCollectionTitle(event.target.value)} /></label><div className="choice-section">{creatorClips.filter((clip) => clip.clip_id).map((clip) => { const clipId = clip.clip_id!; return <label key={clipId} className="sig"><input type="checkbox" checked={selectedCollectionClipIds.includes(clipId)} onChange={(event) => setSelectedCollectionClipIds((current) => event.target.checked ? [...new Set([...current, clipId])] : current.filter((id) => id !== clipId))} />{clip.title ?? clipId}</label> })}</div><div className="monitor-actions"><button type="button" className="button-primary" onClick={() => void createCollection()} disabled={creatorBusy || selectedCollectionClipIds.length < 2 || !collectionTitle.trim()}>Create</button><button type="button" className="button-secondary" onClick={() => setCollectionDialogOpen(false)}>Cancel</button></div></section></div>}

      {pair && (
        <div className="bay">
          <div className="monitor-wrap">
            {artifactAvailable && pair.out.path ? (
              <>
                {mediaUrl && (
                  <video
                    key={`${mediaUrl}-${reloadKey}`}
                    className="monitor"
                    src={mediaUrl}
                    controls
                    playsInline
                    onLoadStart={(event) => traceMedia('review', 'loadstart', event.currentTarget)}
                    onLoadedMetadata={(event) => {
                      traceMedia('review', 'loadedmetadata', event.currentTarget)
                      setMediaState('ready')
                    }}
                    onLoadedData={(event) => traceMedia('review', 'loadeddata', event.currentTarget)}
                    onCanPlay={(event) => traceMedia('review', 'canplay', event.currentTarget)}
                    onCanPlayThrough={(event) => traceMedia('review', 'canplaythrough', event.currentTarget)}
                    onProgress={(event) => traceMedia('review', 'progress', event.currentTarget)}
                    onStalled={(event) => traceMedia('review', 'stalled', event.currentTarget)}
                    onSuspend={(event) => traceMedia('review', 'suspend', event.currentTarget)}
                    onWaiting={(event) => traceMedia('review', 'waiting', event.currentTarget)}
                    onError={(event) => {
                      traceMedia('review', 'error', event.currentTarget)
                      setMediaState('error')
                    }}
                    data-testid="review-video"
                  />
                )}
                {mediaState === 'loading' && <p className="monitor-status mono">loading clip…</p>}
                {mediaState === 'error' && (
                  <div className="monitor-error" role="alert" data-testid="video-error">
                    <strong>This clip could not be loaded<span className="sr-only">CLIP COULD NOT BE LOADED</span></strong>
                    <span>Check the saved render or try loading it again.</span>
                    <button className="btn-secondary" aria-label="RETRY LOAD" onClick={() => setReloadKey((k) => k + 1)}>
                      Try again
                    </button>
                  </div>
                )}
              </>
            ) : (
              <div className="monitor-error" role="alert" data-testid="artifact-error">
                <strong>The rendered clip is unavailable<span className="sr-only">RENDER ARTIFACT UNAVAILABLE</span></strong>
                <span>
                  {pair.out?.artifact_status === 'outside_managed_root'
                    ? 'The clip is outside the managed application folder.'
                    : pair.out?.artifact_status === 'invalid'
                      ? 'The saved render record is invalid.'
                      : 'The rendered clip is missing or unreadable.'}
                </span>
                <button className="btn-secondary" onClick={() => setReloadKey((k) => k + 1)}>
                  RETRY LOAD
                </button>
              </div>
            )}
            <div className="monitor-actions">
              <button className="btn-secondary" onClick={() => setEditing(pair.scoreClipIndex)}>
                Edit clip
              </button>
              <button className="btn-primary" aria-label="EXPORT MP4" onClick={() => doExport(pair)}>
                {exported[pair.identity] ? 'Exported' : 'Export MP4'}
              </button>
              {exported[pair.identity] && (
                <span className="mono export-path">{exported[pair.identity]}</span>
              )}
            </div>
            {exportError && <p className="inline-message" role="alert">{exportError}</p>}
          </div>

          <aside className="audit">
            <p className="audit-kicker">WHY THIS CLIP</p>
            <div className="audit-score-row">
              <div>
                <span className="audit-big mono">{Math.round(pair.scoreClip.recommendation_score ?? pair.scoreClip.score)}</span>
                <span className="audit-score-caption">Recommendation score</span>
              </div>
              <div className="audit-platforms">
                {Object.entries(pair.scoreClip.platform_scores).map(([platform, value]) => (
                  <div className="platform-row" key={platform}>
                    <span className="platform-name">{platform}</span>
                    <div className="platform-bar">
                      <div className="platform-fill" style={{ width: `${value}%` }} />
                    </div>
                    <span className="mono platform-val">{Math.round(value)}</span>
                  </div>
                ))}
              </div>
            </div>
            {selectedClipId && <div className="title-editor">
              <h2 className="audit-title">{selectedTitle}</h2>
              {titleEditing ? <div className="monitor-actions"><label className="field-stack">Publishing title<input aria-label="Publishing title" value={titleDraft} maxLength={120} onChange={(event) => setTitleDraft(event.target.value)} /></label><button type="button" className="button-primary" onClick={() => void saveTitle()} disabled={titleBusy || !titleDraft.trim()}>Save</button><button type="button" className="button-secondary" onClick={() => { setTitleDraft(selectedTitle); setTitleEditing(false) }} disabled={titleBusy}>Cancel</button></div> : <><p className="audit-fine">{selectedTitleSource === 'user' ? 'Edited by you' : <>Publishing title {'·'} {selectedTitleSource}</>}</p><div className="monitor-actions"><button type="button" className="button-secondary" onClick={() => { setTitleDraft(selectedTitle); setTitleEditing(true) }}>Edit title</button><button type="button" className="button-quiet" onClick={() => void resetTitle()} disabled={titleBusy}>Reset to generated</button></div></>}
            </div>}
            <div className="audit-tier"><span>Quality tier</span><strong>{qualityTier(Number(pair.scoreClip.recommendation_score ?? pair.scoreClip.score))}</strong><span>Recommendation confidence</span><strong>{confidenceLabel(pair.scoreClip.confidence)}</strong><span>Platform fit</span><strong>{Math.round(pair.scoreClip.platform_score ?? pair.scoreClip.score)}/100</strong></div>
            <p className="audit-score-note">This is a 0–100 ranking signal, not a probability.</p>
            <p className="audit-summary">{pair.scoreClip.summary}</p>

            <p className="audit-label">SIGNAL BREAKDOWN</p>
            <div className="subs">
              {Object.entries(pair.scoreClip.subscores).map(([name, value]) => (
                <div className="sub-row" key={name}>
                  <span className="sub-name">{name.replace('_', ' ')}</span>
                  <div className="sub-bar">
                    <div className="sub-fill" style={{ width: `${value * 10}%` }} />
                  </div>
                  <span className="mono sub-val">{value.toFixed(1)}</span>
                </div>
              ))}
            </div>

            {pair.scoreClip.adjustments.length > 0 && (
              <>
                <p className="audit-label">WHAT CHANGED THE SCORE</p>
                <div className="ledger">
                  {pair.scoreClip.adjustments.map((adj, i) => (
                    <div className="ledger-row" key={i}>
                      <span className={`ledger-factor mono ${adjustmentDirection(adj)}`}>
                        {adjustmentLabel(adj)}
                      </span>
                      <div>
                        <span className="ledger-rule">{RULE_LABELS[adj.rule] ?? adj.rule}</span>
                        <span className="ledger-reason">{adj.reason}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {pair.scoreClip.ledger && (
              <>
                <p className="audit-label">SCORING DETAILS</p>
                <div className="ledger ledger-explain" data-testid="clip-ledger">
                  <div className="ledger-row">
                    <span className="ledger-factor mono">{Math.round(pair.scoreClip.ledger.recommendation_score ?? pair.scoreClip.ledger.score)}</span>
                    <div>
                      <span className="ledger-rule">Recommendation score</span>
                      <span className="ledger-reason">Platform fit and short-form quality for {pair.scoreClip.best_platform}</span>
                    </div>
                  </div>
                  {pair.scoreClip.platform_score !== undefined && pair.scoreClip.short_quality_score !== undefined && (
                    <div className="ledger-row">
                      <span className="ledger-factor mono">{Math.round(pair.scoreClip.platform_score)}</span>
                      <div>
                        <span className="ledger-rule">Platform fit</span>
                        <span className="ledger-reason">Short-form quality: {Math.round(pair.scoreClip.short_quality_score)}</span>
                      </div>
                    </div>
                  )}
                  <div className="ledger-row">
                    <span className="ledger-factor mono">{Math.round(pair.scoreClip.ledger.composition.curve_score)}</span>
                    <div>
                      <span className="ledger-rule">Signal mix</span>
                      <span className="ledger-reason">
                        arousal {Math.round(pair.scoreClip.ledger.composition.arousal_pct * 100)}% ·{' '}
                        {pair.scoreClip.ledger.composition.heatmap_pct === null
                          ? 'no replay heatmap'
                          : `replay ${Math.round(pair.scoreClip.ledger.composition.heatmap_pct * 100)}%`} ·{' '}
                        {pair.scoreClip.ledger.composition.visual_evidence ? 'visual evidence present' : 'visual evidence unavailable'}
                      </span>
                    </div>
                  </div>
                  <div className="ledger-row">
                    <span className="ledger-factor mono">v{pair.scoreClip.ledger.provenance.scoring_config_version}</span>
                    <div>
                      <span className="ledger-rule">Scoring source</span>
                      <span className="ledger-reason">
                        {pair.scoreClip.ledger.provenance.model} · {pair.scoreClip.ledger.provenance.llm_mode} ·{' '}
                        {pair.scoreClip.ledger.provenance.arousal_source}
                      </span>
                    </div>
                  </div>
                </div>
              </>
            )}

            <p className="audit-label">SIGNALS USED</p>
            <div className="signals">
              {pair.scoreClip.signals_fired.map((signal) => (
                <span className="sig sig-on" key={signal}>
                  <span className="led led-on" />
                  {SIGNAL_LABELS[signal] ?? signal}
                </span>
              ))}
              {pair.scoreClip.signals_missing.map((signal) => (
                <span className="sig sig-off" key={signal}>
                  <span className="led led-off" />
                  {SIGNAL_LABELS[signal] ?? signal}
                </span>
              ))}
            </div>

            {pair.scoreClip.music && (
              <>
                <p className="audit-label">MUSIC DIRECTION</p>
                <div className="music-card">
                  <p className="music-main">
                    <span className="signal-accent">{pair.scoreClip.music.genre}</span> ·{' '}
                    {pair.scoreClip.music.mood} · <span className="mono">{pair.scoreClip.music.bpm_range} bpm</span>
                  </p>
                  <p className="music-theme">{pair.scoreClip.music.theme}</p>
                  <p className="music-alt">
                    also try:{' '}
                    {pair.scoreClip.music.alternatives
                      .map((alt) => `${alt.genre} (${alt.bpm_range})`)
                      .join(' / ')}
                  </p>
                </div>
              </>
            )}

            <p className="audit-fine mono">
              confidence: {pair.scoreClip.confidence} · captions: {results.render?.caption_preset} ·{' '}
              {pair.out.words} words · {pair.out.event_tags} event tags
            </p>
          </aside>
        </div>
      )}
    </div>
  )
}

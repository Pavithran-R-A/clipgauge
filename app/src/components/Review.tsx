import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { chooseExportDestination } from '../exportDestination'
import { traceMedia } from '../mediaDiagnostics'
import type { Clip, JobResults, RenderOutput } from '../types'
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
      {results.collections?.collections?.length ? <section className="card-surface" aria-labelledby="collections-heading"><p className="section-eyebrow">Series / Collections</p><h2 id="collections-heading">Suggested collections</h2>{results.collections.collections.map((collection) => <div className="ledger-row" key={collection.id}><div><strong>{collection.title}</strong><span className="ledger-reason">{collection.clip_ids.length} clips · {collection.source}</span></div></div>)}</section> : null}

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
            {pair.scoreClip.title && <><h2 className="audit-title">{pair.scoreClip.title}</h2><p className="audit-fine">Publishing title · {pair.scoreClip.title_source ?? 'deterministic'}</p>{pair.scoreClip.short_description && <p className="audit-summary">{pair.scoreClip.short_description}</p>}</>}
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

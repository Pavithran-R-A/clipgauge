import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { chooseExportDestination } from '../exportDestination'
import { traceMedia } from '../mediaDiagnostics'
import type { Clip, JobResults, RenderOutput } from '../types'
import ClipEditor from './ClipEditor'

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

export default function Review({ results, onBack, onRestyle }: Props) {
  const outputs = results.render?.outputs ?? []
  const clips = results.score?.clips ?? []
  const [selected, setSelected] = useState(0)
  const [exported, setExported] = useState<Record<number, string>>({})
  const currentPreset = results.render?.caption_preset ?? 'classic'
  const [restylePreset, setRestylePreset] = useState(currentPreset)
  const [restyleCamera, setRestyleCamera] = useState('cut')
  const [editing, setEditing] = useState<number | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [mediaState, setMediaState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [mediaUrl, setMediaUrl] = useState<string | null>(null)
  const styleChanged = restylePreset !== currentPreset || restyleCamera !== 'cut'

  const pair = useMemo(() => {
    const out = outputs[selected]
    const clip = out ? clips[out.clip] : undefined
    return { out, clip }
  }, [outputs, clips, selected])

  const artifactAvailable = Boolean(
    pair.out?.path && (pair.out.artifact_status === undefined || pair.out.artifact_status === 'available')
  )

  useEffect(() => {
    setMediaState(artifactAvailable ? 'loading' : 'error')
  }, [artifactAvailable, pair.out?.path, pair.out?.artifact_status, reloadKey])

  useEffect(() => {
    let active = true
    setMediaUrl(null)
    if (!artifactAvailable || !pair.out) return () => { active = false }
    api.requestPlaybackUrl(results.job_id, 'render', pair.out.clip)
      .then((url) => {
        if (active) setMediaUrl(url)
      })
      .catch(() => {
        if (active) setMediaState('error')
      })
    return () => { active = false }
  }, [artifactAvailable, pair.out?.clip, pair.out?.path, reloadKey, results.job_id])

  async function doExport(out: RenderOutput, clip: Clip) {
    if (!out.path || !artifactAvailable) return
    const suggestedTitle = `${results.ingest?.title ?? 'clip'} ${fmtTime(clip.start)}`
    const dest = await chooseExportDestination({
      jobId: results.job_id,
      clip: out.clip,
      suggestedTitle,
    })
    if (!dest) return
    setExported((prev) => ({ ...prev, [out.clip]: dest }))
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

  return (
    <div className="review">
      <header className="review-head">
        <button className="btn-ghost" onClick={onBack}>
          ← studio
        </button>
        <div className="review-title-block">
          <h1 className="review-title">{results.ingest?.title ?? results.job_id}</h1>
          <p className="review-sub mono">
            {outputs.length} clips · {results.score?.llm_mode === 'ollama' ? 'scored locally' : 'AI-assisted scoring'} ·{' '}
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
          const clip = clips[out.clip]
          return (
            <button
              key={out.clip}
              className={`film-card ${i === selected ? 'film-on' : ''}`}
              onClick={() => setSelected(i)}
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <span className="film-score mono">{Math.round(clip?.recommendation_score ?? clip?.score ?? out.score)}</span>
              <span className="film-time mono">{clip ? fmtTime(clip.start) : ''}</span>
              <span className="film-platform">{out.best_platform}</span>
            </button>
          )
        })}
      </div>

      {pair.out && pair.clip && (
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
              <button className="btn-secondary" onClick={() => setEditing(pair.out!.clip)}>
                Edit clip
              </button>
              <button className="btn-primary" aria-label="EXPORT MP4" onClick={() => doExport(pair.out!, pair.clip!)}>
                {exported[pair.out.clip] ? 'Exported' : 'Export MP4'}
              </button>
              {exported[pair.out.clip] && (
                <span className="mono export-path">{exported[pair.out.clip]}</span>
              )}
            </div>
          </div>

          <aside className="audit">
            <p className="audit-kicker">WHY THIS CLIP</p>
            <div className="audit-score-row">
              <div>
                <span className="audit-big mono">{Math.round(pair.clip.recommendation_score ?? pair.clip.score)}</span>
                <span className="audit-score-caption">recommendation</span>
              </div>
              <div className="audit-platforms">
                {Object.entries(pair.clip.platform_scores).map(([platform, value]) => (
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
            <p className="audit-summary">{pair.clip.summary}</p>

            <p className="audit-label">SIGNAL BREAKDOWN</p>
            <div className="subs">
              {Object.entries(pair.clip.subscores).map(([name, value]) => (
                <div className="sub-row" key={name}>
                  <span className="sub-name">{name.replace('_', ' ')}</span>
                  <div className="sub-bar">
                    <div className="sub-fill" style={{ width: `${value * 10}%` }} />
                  </div>
                  <span className="mono sub-val">{value.toFixed(1)}</span>
                </div>
              ))}
            </div>

            {pair.clip.adjustments.length > 0 && (
              <>
                <p className="audit-label">WHAT CHANGED THE SCORE</p>
                <div className="ledger">
                  {pair.clip.adjustments.map((adj, i) => (
                    <div className="ledger-row" key={i}>
                      <span className={`ledger-factor mono ${adj.factor >= 1 ? 'up' : 'down'}`}>
                        ×{adj.factor}
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

            {pair.clip.ledger && (
              <>
                <p className="audit-label">SCORING DETAILS</p>
                <div className="ledger ledger-explain" data-testid="clip-ledger">
                  <div className="ledger-row">
                    <span className="ledger-factor mono">{Math.round(pair.clip.ledger.recommendation_score ?? pair.clip.ledger.score)}</span>
                    <div>
                      <span className="ledger-rule">Recommendation score</span>
                      <span className="ledger-reason">Platform fit and short-form quality for {pair.clip.best_platform}</span>
                    </div>
                  </div>
                  {pair.clip.platform_score !== undefined && pair.clip.short_quality_score !== undefined && (
                    <div className="ledger-row">
                      <span className="ledger-factor mono">{Math.round(pair.clip.platform_score)}</span>
                      <div>
                        <span className="ledger-rule">Platform fit</span>
                        <span className="ledger-reason">Short-form quality: {Math.round(pair.clip.short_quality_score)}</span>
                      </div>
                    </div>
                  )}
                  <div className="ledger-row">
                    <span className="ledger-factor mono">{Math.round(pair.clip.ledger.composition.curve_score)}</span>
                    <div>
                      <span className="ledger-rule">Signal mix</span>
                      <span className="ledger-reason">
                        arousal {Math.round(pair.clip.ledger.composition.arousal_pct * 100)}% ·{' '}
                        {pair.clip.ledger.composition.heatmap_pct === null
                          ? 'no replay heatmap'
                          : `replay ${Math.round(pair.clip.ledger.composition.heatmap_pct * 100)}%`} ·{' '}
                        {pair.clip.ledger.composition.visual_evidence ? 'visual evidence present' : 'visual evidence unavailable'}
                      </span>
                    </div>
                  </div>
                  <div className="ledger-row">
                    <span className="ledger-factor mono">v{pair.clip.ledger.provenance.scoring_config_version}</span>
                    <div>
                      <span className="ledger-rule">Scoring source</span>
                      <span className="ledger-reason">
                        {pair.clip.ledger.provenance.model} · {pair.clip.ledger.provenance.llm_mode} ·{' '}
                        {pair.clip.ledger.provenance.arousal_source}
                      </span>
                    </div>
                  </div>
                </div>
              </>
            )}

            <p className="audit-label">SIGNALS USED</p>
            <div className="signals">
              {pair.clip.signals_fired.map((signal) => (
                <span className="sig sig-on" key={signal}>
                  <span className="led led-on" />
                  {SIGNAL_LABELS[signal] ?? signal}
                </span>
              ))}
              {pair.clip.signals_missing.map((signal) => (
                <span className="sig sig-off" key={signal}>
                  <span className="led led-off" />
                  {SIGNAL_LABELS[signal] ?? signal}
                </span>
              ))}
            </div>

            {pair.clip.music && (
              <>
                <p className="audit-label">MUSIC DIRECTION</p>
                <div className="music-card">
                  <p className="music-main">
                    <span className="signal-accent">{pair.clip.music.genre}</span> ·{' '}
                    {pair.clip.music.mood} · <span className="mono">{pair.clip.music.bpm_range} bpm</span>
                  </p>
                  <p className="music-theme">{pair.clip.music.theme}</p>
                  <p className="music-alt">
                    also try:{' '}
                    {pair.clip.music.alternatives
                      .map((alt) => `${alt.genre} (${alt.bpm_range})`)
                      .join(' / ')}
                  </p>
                </div>
              </>
            )}

            <p className="audit-fine mono">
              confidence: {pair.clip.confidence} · captions: {results.render?.caption_preset} ·{' '}
              {pair.out.words} words · {pair.out.event_tags} event tags
            </p>
          </aside>
        </div>
      )}
    </div>
  )
}

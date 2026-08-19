import { useEffect, useState } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import { api } from '../api'
import type { JobSummary, PrivacySummary } from '../types'
import KeyModal from './KeyModal'

const STAGE_ORDER = [
  'ingest', 'asr', 'diarize', 'events', 'candidates', 'score', 'camera', 'render'
]

const STAGE_LABELS: Record<string, string> = {
  ingest: 'INGEST',
  asr: 'TRANSCRIBE',
  diarize: 'SPEAKERS',
  events: 'LISTEN',
  candidates: 'SCAN',
  score: 'JUDGE',
  camera: 'DIRECT',
  render: 'RENDER'
}

const CAPTION_PRESETS = ['classic', 'beast', 'hormozi', 'minimal', 'karaoke-pop']

interface Props {
  jobs: JobSummary[]
  running: boolean
  cancelling: boolean
  startedAt: number | null
  stages: Record<string, { fraction: number; message: string }>
  error: string | null
  notice: string | null
  onRun: (source: string, llm: string, captions: string) => void
  onCancel: () => void
  onOpenLoop: () => void
  onOpenJob: (id: string) => void
  onResume: (id: string, llm?: string) => void
}

export default function Studio({ jobs, running, cancelling, startedAt, stages, error, notice, onRun, onCancel, onOpenLoop, onOpenJob, onResume }: Props) {
  const [source, setSource] = useState('')
  const [llm, setLlm] = useState('gemini')
  const [captions, setCaptions] = useState('classic')
  const [showKey, setShowKey] = useState(false)
  const [privacy, setPrivacy] = useState<PrivacySummary | null>(null)
  const [supportMessage, setSupportMessage] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!startedAt) return
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [startedAt])

  const elapsed = startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : 0
  const elapsedLabel = `${String(Math.floor(elapsed / 60)).padStart(2, '0')}:${String(elapsed % 60).padStart(2, '0')}`

  async function showPrivacy() {
    try {
      setPrivacy(await api.privacySummary(llm))
    } catch (error) {
      setSupportMessage(`Privacy summary unavailable: ${String(error)}`)
    }
  }

  async function makeSupportBundle() {
    setSupportMessage('Generating a redacted support bundle…')
    try {
      const path = await api.generateSupportBundle()
      setSupportMessage(`Support bundle saved locally: ${path}`)
    } catch (error) {
      setSupportMessage(`Support bundle failed: ${String(error)}`)
    }
  }

  async function chooseFile() {
    const selected = await open({
      multiple: false,
      directory: false,
      filters: [{ name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi'] }]
    })
    if (typeof selected === 'string') setSource(selected)
  }

  function dropFile(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault()
    if (running) return
    const file = event.dataTransfer.files[0] as (File & { path?: string }) | undefined
    if (file?.path) setSource(file.path)
  }

  return (
    <div className="studio">
      <div className="grain" />
      {showKey && <KeyModal onClose={() => setShowKey(false)} />}
      {privacy && (
        <div className="modal-scrim" onClick={() => setPrivacy(null)}>
          <div className="modal privacy-modal" role="dialog" aria-modal="true" aria-labelledby="privacy-title" onClick={(event) => event.stopPropagation()}>
            <header className="modal-head">
              <p id="privacy-title" className="audit-kicker">PRIVACY ACTIVITY</p>
              <button className="btn-ghost" onClick={() => setPrivacy(null)}>close</button>
            </header>
            <p className="ig-intro">ClipGauge is local-first, but this mode still performs the network operations listed below. Telemetry is {privacy.telemetry}.</p>
            <p className="audit-label">LEAVES THIS DEVICE</p>
            <ul className="privacy-list">{privacy.llm.network.map((item) => <li key={item}>{item}</li>)}</ul>
            <p className="audit-label">STAYS LOCAL</p>
            <ul className="privacy-list">{privacy.llm.device.map((item) => <li key={item}>{item}</li>)}</ul>
            <p className="ig-message">{privacy.llm.provider}</p>
            <p className="ig-message">{privacy.instagram}</p>
          </div>
        </div>
      )}
      <aside className="rail">
        <header className="rail-brand">
          <span className="rail-logo">ClipGauge</span>
          <span className="rail-sub">local AI video clipper</span>
        </header>
        <div className="rail-jobs">
          <p className="rail-label">SESSIONS</p>
          {jobs.length === 0 && <p className="rail-empty">nothing yet</p>}
          {jobs.map((job) => (
            <button
              key={job.id}
              className={`rail-job ${job.rendered ? '' : 'partial'}`}
              onClick={() => (job.rendered ? onOpenJob(job.id) : onResume(job.id))}
              disabled={running}
              title={job.rendered ? 'open results' : 'resume from checkpoint'}
            >
              <span className={`led ${job.rendered ? 'led-on' : 'led-half'}`} />
              <span className="rail-job-title">{job.title ?? job.id}</span>
              <span className="rail-job-hint">
                {job.rendered ? 'open' : job.resume_safe === false ? 'inspect' : `resume${job.last_stage ? ` · ${job.last_stage}` : ''}`}
              </span>
            </button>
          ))}
        </div>
        <footer className="rail-foot">
          <button className="btn-ghost" onClick={() => setShowKey(true)}>
            ◈ gemini key
          </button>
          <button className="btn-ghost" onClick={onOpenLoop}>
            ⟳ instagram loop
          </button>
          <button className="btn-ghost" onClick={showPrivacy}>
            privacy activity
          </button>
          <button className="btn-ghost" onClick={makeSupportBundle}>
            support bundle
          </button>
        </footer>
      </aside>

      <main className="stage-area">
        <section className="input-block">
          <h1 className="input-heading">
            FEED IT<span className="amber"> AN HOUR.</span>
          </h1>
          <div
            className="input-row source-drop"
            onDragOver={(event) => event.preventDefault()}
            onDrop={dropFile}
            aria-label="Video source drop area"
          >
            <input
              value={source}
              onChange={(e) => setSource(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && source.trim() && !running && onRun(source.trim(), llm, captions)}
              placeholder="YouTube URL or a path to a video file"
              disabled={running}
            />
            <button
              className="btn-secondary"
              onClick={chooseFile}
              disabled={running}
              aria-label="Choose a local video file"
            >
              CHOOSE FILE
            </button>
            <button
              className="btn-primary"
              onClick={() => onRun(source.trim(), llm, captions)}
              disabled={running || !source.trim()}
            >
              {running ? 'WORKING' : 'CUT IT'}
            </button>
            {running && (
              <button
                className="btn-ghost"
                onClick={onCancel}
                disabled={cancelling}
                aria-label="Cancel the active job"
              >
                {cancelling ? 'CANCELLING' : 'CANCEL'}
              </button>
            )}
          </div>
          <div className="run-options">
            <div className="opt-group">
              <span className="opt-label">brain</span>
              {['gemini', 'ollama'].map((mode) => (
                <button
                  key={mode}
                  className={`opt ${llm === mode ? 'opt-on' : ''}`}
                  onClick={() => setLlm(mode)}
                  disabled={running}
                >
                  {mode}
                </button>
              ))}
            </div>
            <div className="opt-group">
              <span className="opt-label">captions</span>
              {CAPTION_PRESETS.map((preset) => (
                <button
                  key={preset}
                  className={`opt ${captions === preset ? 'opt-on' : ''}`}
                  onClick={() => setCaptions(preset)}
                  disabled={running}
                >
                  {preset}
                </button>
              ))}
            </div>
          </div>
        </section>

        {(running || Object.keys(stages).length > 0) && (
          <section className="deck" aria-label="Pipeline progress" aria-live="polite">
            {STAGE_ORDER.filter((s) => stages[s] || running).map((name, i) => {
              const st = stages[name]
              const state = !st ? 'idle' : st.fraction >= 1 ? 'done' : 'live'
              return (
                <div className={`deck-row ${state}`} key={name} style={{ animationDelay: `${i * 40}ms` }}>
                  <span className="deck-name mono">{STAGE_LABELS[name] ?? name.toUpperCase()}</span>
                  <div
                    className="deck-bar"
                    role="progressbar"
                    aria-label={`${STAGE_LABELS[name] ?? name} stage progress`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={st && st.fraction >= 0 ? Math.round(Math.min(1, st.fraction) * 100) : undefined}
                  >
                    <div
                      className={`deck-fill ${st && st.fraction < 0 ? 'indeterminate' : ''}`}
                      style={st && st.fraction >= 0 ? { width: `${Math.min(100, st.fraction * 100)}%` } : undefined}
                    />
                  </div>
                  <span className="deck-msg">{st?.message ?? ''}</span>
                </div>
              )
            })}
            <p className="elapsed mono" aria-label={`Elapsed time ${elapsedLabel}`}>
              ELAPSED {elapsedLabel}{stages.render?.message ? ` · ${stages.render.message}` : ''}
            </p>
          </section>
        )}

        {notice && (
          <section className="status-block" role="status">
            <span className="led led-half" />
            {notice}
          </section>
        )}
        {supportMessage && (
          <section className="status-block" role="status">
            <span className="led led-half" />
            {supportMessage}
          </section>
        )}
        {error && (
          <section className="error-block" role="alert">
            <span className="led led-err" />
            {error}
          </section>
        )}
      </main>
    </div>
  )
}

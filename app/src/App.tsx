import { useCallback, useEffect, useRef, useState } from 'react'
import { listen } from '@tauri-apps/api/event'
import { api } from './api'
import type { JobResults, JobSummary, PipelineEvent, SetupState, StageProgress } from './types'
import AppShell, { type AppSection } from './components/AppShell'
import About from './components/About'
import Integrations from './components/Integrations'
import Loop from './components/Loop'
import Onboarding from './components/Onboarding'
import PrivacyPanel from './components/PrivacyPanel'
import ProviderCenter from './components/ProviderCenter'
import Review from './components/Review'
import Sessions from './components/Sessions'
import SetupCenter from './components/SetupCenter'
import Studio from './components/Studio'
import SupportPage from './components/SupportPage'
import { sourceKind, type CreatorRunState } from './creatorState'
import { resolveSelectedLocalModel } from './setupState'
import './styles.css'

type View = 'boot' | 'onboarding' | 'shell' | 'review' | 'loop'

const FRIENDLY_FAILURES: Record<string, string> = {
  SPEAKER_MODEL_DOWNLOAD_FAILED: 'Speaker analysis couldn’t start because its model could not be downloaded. Open Setup & Storage and retry the component.',
  SPEAKER_MODEL_VERIFY_FAILED: 'Speaker analysis couldn’t start because the downloaded model did not pass verification. Open Setup & Storage and repair it.',
  SPEAKER_MODEL_LOAD_FAILED: 'Speaker analysis couldn’t start because the speaker model could not be loaded. Retry the component or continue without speaker-aware reframing.',
  SPEAKER_AUDIO_LOAD_FAILED: 'Speaker analysis couldn’t read the audio for this video. Retry the job or continue without speaker-aware reframing.',
  SPEAKER_ANALYSIS_FAILED: 'Speaker analysis could not complete. Retry the job or continue without speaker-aware reframing.',
  SPEAKER_CLUSTER_FAILED: 'Speaker grouping could not complete. Retry the job or continue without speaker-aware reframing.',
  PROVIDER_UNAVAILABLE: 'The selected AI is unavailable. Open AI Providers or choose another provider.',
  YTDLP_ATTESTATION_REQUIRED: 'YouTube rejected this download during playback verification. ClipGauge itself is ready; retry later, try optional browser-assisted compatibility with explicit approval, or import the video file directly.',
  YTDLP_LOGIN_REQUIRED: 'This video requires a signed-in YouTube session. Use a browser session only if you explicitly consent.',
  ASR_GPU_FALLBACK_REQUIRES_APPROVAL: 'GPU speech acceleration failed. Repair GPU acceleration, or explicitly continue in slower CPU mode.'
}

export default function App() {
  const [view, setView] = useState<View>('boot')
  const [section, setSection] = useState<AppSection>('create')
  const [, setSetup] = useState<SetupState | null>(null)
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [activeJob, setActiveJob] = useState<string | null>(null)
  const [results, setResults] = useState<JobResults | null>(null)
  const [stages, setStages] = useState<Record<string, StageProgress>>({})
  const [running, setRunning] = useState(false)
  const [runState, setRunState] = useState<CreatorRunState>('IDLE')
  const [cancelling, setCancelling] = useState(false)
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null)
  const [runError, setRunError] = useState<string | null>(null)
  const [runErrorCode, setRunErrorCode] = useState<string | null>(null)
  const [runNotice, setRunNotice] = useState<string | null>(null)
  const [selectedProvider, setSelectedProvider] = useState('clipgauge-local')
  const [selectedLocalModelId, setSelectedLocalModelId] = useState<string | null>(null)
  const unlistenRef = useRef<(() => void) | null>(null)
  const activeJobRef = useRef<string | null>(null)
  activeJobRef.current = activeJob

  const refreshJobs = useCallback(() => { api.listJobs().then(setJobs).catch(() => setJobs([])) }, [])

  useEffect(() => {
    api.setupState().then((state) => { setSetup(state); setView(state.onboarded ? 'shell' : 'onboarding') }).catch(() => setView('onboarding'))
    refreshJobs()
  }, [refreshJobs])

  useEffect(() => {
    const report = (message: string) => {
      const bounded = message.replace(/\s+/g, ' ').slice(0, 240)
      console.error('[ClipGauge app QA]', bounded)
      void api.recordMediaEvent({ label: 'app', event: 'runtime_error', error_message: bounded })
    }
    const onError = (event: ErrorEvent) => report(event.error?.message ?? event.message)
    const onReject = (event: PromiseRejectionEvent) => report(String(event.reason))
    window.addEventListener('error', onError)
    window.addEventListener('unhandledrejection', onReject)
    return () => {
      window.removeEventListener('error', onError)
      window.removeEventListener('unhandledrejection', onReject)
    }
  }, [])

  useEffect(() => {
    const kick = () => { api.igStatus().then((status) => (status.connected ? api.igSync() : null)).catch(() => null) }
    kick()
    const timer = window.setInterval(kick, 60 * 60 * 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    let disposed = false
    listen<PipelineEvent>('pipeline-event', ({ payload }) => {
      if (payload.event === 'job' && payload.job_id) {
        setActiveJob(payload.job_id)
        setResults(null)
      } else if (payload.event === 'progress' && payload.stage) {
        setStages((previous) => ({ ...previous, [payload.stage!]: { fraction: payload.fraction ?? -1, message: payload.message ?? '', displayStage: payload.display_stage, operation: payload.operation, indeterminate: payload.indeterminate ?? (payload.fraction ?? -1) < 0, elapsedSeconds: payload.elapsed_seconds, stageElapsedSeconds: payload.stage_elapsed_seconds, etaSeconds: payload.eta_seconds, bytesDone: payload.bytes_done, bytesTotal: payload.bytes_total, bytesPerSecond: payload.bytes_per_second, accelerator: payload.accelerator, oneTimeDownload: payload.one_time_download } }))
      } else if (payload.event === 'terminal') {
        setRunning(false)
        setCancelling(false)
        setRunStartedAt(null)
        refreshJobs()
        if (payload.code === 'CANCELLED') {
          setRunState('CANCELLED')
          setRunError(null)
          setRunNotice(payload.message ?? 'Job cancelled. Completed work remains available to resume.')
        } else if (payload.ok && activeJobRef.current) {
          setRunState('SUCCEEDED')
          setRunNotice(null)
          api.jobResults(activeJobRef.current).then((result) => { setResults(result); setView('review') }).catch((error) => setRunError(String(error)))
        } else if (!payload.ok) {
          setRunState('FAILED')
          setRunErrorCode(payload.code ?? null)
          setRunNotice(null)
          const friendly = payload.code ? FRIENDLY_FAILURES[payload.code] : undefined
          const diagnostic = payload.diagnostic_id ? ` Technical details: ${payload.diagnostic_id}.` : ''
          setRunError(`${friendly ?? payload.message ?? 'The video could not be processed.'}${diagnostic}`)
        }
      } else if (payload.event === 'result') {
        setRunning(false)
        setCancelling(false)
        setRunNotice(null)
        setRunState(payload.ok ? 'SUCCEEDED' : 'FAILED')
        refreshJobs()
        if (payload.ok && activeJobRef.current && payload.stages) api.jobResults(activeJobRef.current).then((result) => { setResults(result); setView('review') }).catch((error) => setRunError(String(error)))
        else if (!payload.ok) setRunError(String(payload.message ?? payload.error ?? 'The video could not be processed.'))
      } else if (payload.event === 'exited') {
        setRunning(false)
        setRunState('FAILED')
        setCancelling(false)
        setRunNotice(null)
        setRunError('The video stopped before finishing. Retry the job and keep the diagnostic details for support.')
      }
    }).then((unlisten) => { if (disposed) unlisten(); else unlistenRef.current = unlisten })
    return () => { disposed = true; unlistenRef.current?.() }
  }, [refreshJobs])

  const startRun = useCallback(async (source: string, provider: string, captions: string, model?: string, endpoint?: string, auth?: string, secretHeader?: string, browserSession?: string) => {
    setRunning(true)
    setRunState('RUNNING')
    setRunStartedAt(Date.now())
    setCancelling(false)
    setRunError(null)
    setRunErrorCode(null)
    setRunNotice(null)
    setStages({})
    setResults(null)
    setActiveJob(null)
    try {
      const resolvedModel = model ?? (provider === 'clipgauge-local' ? resolveSelectedLocalModel(await api.setupInventory()) : undefined)
      const preflight = await api.preflight(provider, resolvedModel, endpoint, auth, secretHeader, sourceKind(source) === 'youtube' ? source : undefined)
      const blocked = preflight.checks.filter((check) => check.state === 'blocked')
      const warnings = preflight.checks.filter((check) => check.state === 'warning')
      if (preflight.state === 'blocked' || blocked.length) {
        setRunning(false)
        setRunStartedAt(null)
        setRunState('FAILED')
        const first = blocked[0]
        setRunError(`${first?.message ?? 'This run needs a setup step first.'}${first?.remediation ? ` ${first.remediation}` : ''}`)
        return
      }
      if (warnings.length) setRunNotice(`Before you start: ${warnings.slice(0, 2).map((check) => check.message).join(' ')}`)
      setRunning(true)
      setRunState('RUNNING')
      setRunStartedAt(Date.now())
      await api.runJob(source, provider, captions, resolvedModel, endpoint, auth, secretHeader, browserSession)
    } catch (error) {
      setRunning(false)
      setRunState('FAILED')
      setRunError(String(error))
      setRunErrorCode(null)
    }
  }, [])

  const openJob = useCallback(async (jobId: string) => {
    const result = await api.jobResults(jobId)
    setActiveJob(jobId)
    setResults(result)
    if (result.render?.outputs?.length) setView('review')
  }, [])

  const continueCpu = useCallback(() => {
    if (!activeJob) return
    setRunning(true)
    setRunState('RUNNING')
    setRunError(null)
    setRunErrorCode(null)
    setRunNotice(null)
    setStages({})
    void api.resumeJob(activeJob, undefined, undefined, undefined, undefined, undefined, undefined, undefined, true)
  }, [activeJob])

  if (view === 'boot') return <div className="boot" />
  if (view === 'onboarding') return <Onboarding onDone={() => { void api.markOnboarded(); setSetup((current) => current ? { ...current, onboarded: true } : current); setView('shell') }} />
  if (view === 'loop') return <Loop onBack={() => { setSection('integrations'); setView('shell') }} />
  if (view === 'review' && results) return <Review results={results} onBack={() => { setSection('create'); setView('shell'); refreshJobs() }} onRestyle={(captions, camera) => { setRunning(true); setRunState('RUNNING'); setRunStartedAt(Date.now()); setCancelling(false); setRunError(null); setRunNotice(null); setStages({}); setActiveJob(results.job_id); setSection('create'); setView('shell'); void api.resumeJob(results.job_id, undefined, captions, camera) }} />

  function navigate(next: AppSection) {
    setRunError(null)
    setRunErrorCode(null)
    setRunNotice(null)
    setSection(next)
  }

  let content
  if (section === 'create') content = <Studio jobs={jobs} running={running} runState={runState} cancelling={cancelling} startedAt={runStartedAt} stages={stages} error={runError} errorCode={runErrorCode} notice={runNotice} onRun={startRun} localModelId={selectedLocalModelId ?? undefined} onContinueCpu={continueCpu} onCancel={() => { if (!activeJob) return; setCancelling(true); api.cancelJob(activeJob).catch((error) => { setCancelling(false); setRunError(String(error)) }) }} onNavigate={navigate} selectedProvider={selectedProvider} onSelectProvider={setSelectedProvider} onOpenJob={openJob} onResume={(id) => { setRunning(true); setRunState('RUNNING'); setCancelling(false); setRunError(null); setRunErrorCode(null); setRunNotice(null); setStages({}); setActiveJob(id); void api.resumeJob(id) }} />
  else if (section === 'sessions') content = <Sessions jobs={jobs} onBack={() => setSection('create')} onOpenJob={openJob} onResume={(id) => { setSection('create'); setRunning(true); setRunState('RUNNING'); setActiveJob(id); void api.resumeJob(id) }} />
  else if (section === 'setup') content = <SetupCenter onBack={() => setSection('create')} onUseLocal={(modelId) => { if (modelId) setSelectedLocalModelId(modelId); setSelectedProvider('clipgauge-local'); setSection('create') }} />
  else if (section === 'providers') content = <ProviderCenter selectedProvider={selectedProvider} onSelectProvider={setSelectedProvider} onBack={() => setSection('create')} onOpenSetup={() => setSection('setup')} />
  else if (section === 'integrations') content = <Integrations onBack={() => setSection('create')} onOpenLoop={() => setView('loop')} />
  else if (section === 'privacy') content = <PrivacyPanel provider={selectedProvider} onBack={() => setSection('create')} />
  else if (section === 'help') content = <SupportPage onBack={() => setSection('create')} onNavigate={(next) => setSection(next)} provider={selectedProvider} />
  else content = <About onBack={() => setSection('create')} />

  return <AppShell active={section} onNavigate={navigate} jobs={jobs} running={running} onOpenJob={openJob} onResume={(id) => { setSection('create'); setRunning(true); setRunState('RUNNING'); setActiveJob(id); void api.resumeJob(id) }} onSupport={() => setSection('help')}>{content}</AppShell>
}

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
import { type CreatorRunState } from './creatorState'
import { resolveSelectedLocalModel } from './setupState'
import { readCachedSetupInventory, writeCachedSetupInventory } from './setupInventoryCache'
import { validateJobResults } from './jobResultsValidation'
import { isInstagramStatus, isJobSummaryList, isLocalSetupInventory, isPreflightResult, isSetupState } from './nativeValidation'
import { friendlyErrorMessage } from './errorMessaging'
import './styles.css'

function readSavedProviderModel(provider: string): string | undefined {
  try {
    return window.localStorage.getItem(`clipgauge.provider-model.${provider}`) ?? undefined
  } catch {
    return undefined
  }
}

function readSavedProviderEndpoint(provider: string): string | undefined {
  try {
    return window.localStorage.getItem(`clipgauge.provider-endpoint.${provider}`) ?? undefined
  } catch {
    return undefined
  }
}

const SETUP_STATE_CACHE_KEY = 'clipgauge.setup.state.v1'

function isBooleanRecord(value: unknown): value is Record<string, boolean> {
  return typeof value === 'object'
    && value !== null
    && !Array.isArray(value)
    && Object.values(value).every((item) => typeof item === 'boolean')
}

function readCachedSetupState(): SetupState | null {
  try {
    const raw = window.localStorage.getItem(SETUP_STATE_CACHE_KEY)
    if (!raw) return null
    const value: unknown = JSON.parse(raw)
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
    const state = value as Partial<SetupState>
    if (typeof state.onboarded !== 'boolean' || typeof state.has_gemini_key !== 'boolean') return null
    if (state.provider_keys !== undefined && !isBooleanRecord(state.provider_keys)) return null
    return {
      onboarded: state.onboarded,
      has_gemini_key: state.has_gemini_key,
      provider_keys: state.provider_keys,
    }
  } catch {
    return null
  }
}

function writeCachedSetupState(value: SetupState) {
  try { window.localStorage.setItem(SETUP_STATE_CACHE_KEY, JSON.stringify(value)) } catch { /* optional browser storage */ }
}

function readCachedLocalModel(): string | undefined {
  const inventory = readCachedSetupInventory()
  return inventory ? resolveSelectedLocalModel(inventory) : undefined
}

function requireValidJobResults(value: unknown): JobResults {
  if (!validateJobResults(value)) throw new Error('Saved session results are malformed. Retry the session or run the video again.')
  return value
}

type View = 'boot' | 'onboarding' | 'shell' | 'review' | 'loop'
type AttemptExpectation = { jobId: string | null; attemptId: string | null; previousAttemptId: string | null; awaitingJob: boolean }

const FRIENDLY_FAILURES: Record<string, string> = {
  SPEAKER_MODEL_DOWNLOAD_FAILED: 'Speaker analysis couldn’t start because its model could not be downloaded. Open Setup & Storage and retry the component.',
  SPEAKER_MODEL_VERIFY_FAILED: 'Speaker analysis couldn’t start because the downloaded model did not pass verification. Open Setup & Storage and repair it.',
  SPEAKER_MODEL_LOAD_FAILED: 'Speaker analysis couldn’t start because the speaker model could not be loaded. Retry the component or continue without speaker-aware reframing.',
  SPEAKER_AUDIO_LOAD_FAILED: 'Speaker analysis couldn’t read the audio for this video. Retry the job or continue without speaker-aware reframing.',
  SPEAKER_ANALYSIS_FAILED: 'Speaker analysis could not complete. Retry the job or continue without speaker-aware reframing.',
  SPEAKER_CLUSTER_FAILED: 'Speaker grouping could not complete. Retry the job or continue without speaker-aware reframing.',
  PROVIDER_UNAVAILABLE: 'The selected AI is unavailable. Open AI Providers or choose another provider.',
  YTDLP_ATTESTATION_REQUIRED: 'YouTube rejected this download during playback verification. ClipGauge itself is ready; retry later or import the video file directly.',
  YTDLP_LOGIN_REQUIRED: 'This video requires a signed-in YouTube session. Use a browser session only if you explicitly consent.',
  ASR_RUNTIME_MISSING: 'Speech recognition runtime files are missing. Open Setup & Storage and repair speech recognition.',
  ASR_CPU_COMPUTE_UNSUPPORTED: 'This computer cannot use the selected CPU speech mode. Repair speech recognition, then retry.',
  ASR_MODEL_LOAD_RESOURCE_EXHAUSTED: 'Speech recognition needs more working memory. Close other applications and retry in Low-memory mode.',
  ASR_TRANSCRIPTION_RESOURCE_EXHAUSTED: 'Speech recognition needs more working memory. Close other applications and retry in Low-memory mode.',
  ASR_MODEL_LOAD_FAILED: 'Speech recognition could not load its model. Repair speech recognition, then retry.',
  ASR_AUDIO_LOAD_FAILED: 'Speech recognition could not read this video audio. Retry the job or choose another video.',
  ASR_TRANSCRIPTION_FAILED: 'Speech recognition could not complete. Retry the job or repair speech recognition.',
  ASR_VAD_FAILED: 'Speech activity detection could not start. Repair speech recognition, then retry.',
  ASR_ALIGNMENT_FAILED: 'Word timing could not complete. Retry the job or repair speech recognition.',
  ASR_CHECKPOINT_WRITE: 'Speech recognition finished, but its checkpoint could not be saved. Retry the job.',
  ASR_GPU_FALLBACK_REQUIRES_APPROVAL: 'GPU speech acceleration failed. Repair GPU acceleration, or explicitly continue in slower CPU mode.'
}

export default function App() {
  const [cachedSetupState] = useState<SetupState | null>(() => readCachedSetupState())
  const [view, setView] = useState<View>(cachedSetupState ? (cachedSetupState.onboarded ? 'shell' : 'onboarding') : 'boot')
  const [section, setSection] = useState<AppSection>('create')
  const [, setSetup] = useState<SetupState | null>(cachedSetupState)
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [jobsError, setJobsError] = useState<string | null>(null)
  const [activeJob, setActiveJob] = useState<string | null>(null)
  const [activeDiagnosticId, setActiveDiagnosticId] = useState<string | null>(null)
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
  const [selectedLocalModelId, setSelectedLocalModelId] = useState<string | null>(() => readCachedLocalModel() ?? null)
  const [gpuRepairing, setGpuRepairing] = useState(false)
  const unlistenRef = useRef<(() => void) | null>(null)
  const activeJobRef = useRef<string | null>(null)
  const activeAttemptRef = useRef<string | null>(null)
  const attemptExpectationRef = useRef<AttemptExpectation | null>(null)
  const jobsRequestRef = useRef(0)
  const mountedRef = useRef(true)
  const selectedLocalModelRef = useRef<string | null>(selectedLocalModelId)
  activeJobRef.current = activeJob
  selectedLocalModelRef.current = selectedLocalModelId

  const prepareAttempt = useCallback((jobId: string | null) => {
    const previousAttemptId = activeAttemptRef.current
    attemptExpectationRef.current = { jobId, attemptId: null, previousAttemptId, awaitingJob: true }
    activeJobRef.current = jobId
    activeAttemptRef.current = null
    setActiveJob(jobId)
    setResults(null)
    setActiveDiagnosticId(null)
  }, [])

  const refreshJobs = useCallback(() => {
    const requestId = ++jobsRequestRef.current
    api.listJobs().then((value) => {
      if (!isJobSummaryList(value)) throw new Error('Saved session list is malformed.')
      if (requestId === jobsRequestRef.current && mountedRef.current) { setJobs(value); setJobsError(null) }
    }).catch(() => { if (requestId === jobsRequestRef.current && mountedRef.current) { setJobs([]); setJobsError('Sessions unavailable. Open Sessions and retry.') } })
  }, [])

  useEffect(() => {
    mountedRef.current = true
    let active = true
    api.setupState().then((state) => {
      if (!active) return
      if (!isSetupState(state)) throw new Error('Setup state is malformed.')
      writeCachedSetupState(state)
      setSetup(state)
      setView(state.onboarded ? 'shell' : 'onboarding')
    }).catch(() => { if (active && !cachedSetupState) setView('onboarding') })
    refreshJobs()
    return () => { active = false; mountedRef.current = false }
  }, [cachedSetupState, refreshJobs])

  useEffect(() => {
    const report = (message: string) => {
      const bounded = message.replace(/\s+/g, ' ').slice(0, 240)
      console.error('[ClipGauge app QA]', bounded)
      void api.recordMediaEvent({ label: 'app', event: 'runtime_error', error_message: bounded }).catch(() => undefined)
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
    const kick = () => {
      api.igStatus().then((status) => {
        if (!isInstagramStatus(status)) throw new Error('Instagram status is malformed.')
        return status.connected ? api.igSync() : null
      }).catch(() => null)
    }
    kick()
    const timer = window.setInterval(kick, 60 * 60 * 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    let disposed = false
    listen<PipelineEvent>('pipeline-event', ({ payload }) => {
      if (disposed) return
      const expected = attemptExpectationRef.current
      if (expected) {
        if (payload.event === 'job' && payload.job_id) {
          if (expected.jobId && payload.job_id !== expected.jobId) return
          if (expected.previousAttemptId && payload.attempt_id === expected.previousAttemptId) return
          if (expected.attemptId && payload.attempt_id !== expected.attemptId) return
          if (expected.awaitingJob) {
            attemptExpectationRef.current = { jobId: payload.job_id, attemptId: payload.attempt_id ?? null, previousAttemptId: expected.previousAttemptId, awaitingJob: false }
          }
        } else if (expected.awaitingJob && !(expected.jobId === null && payload.event === 'terminal')) {
          return
        } else if (payload.job_id && payload.job_id !== expected.jobId) {
          return
        } else if (payload.attempt_id && payload.attempt_id !== expected.attemptId) {
          return
        }
      } else {
        if (payload.job_id && activeJobRef.current && payload.job_id !== activeJobRef.current) return
        if (payload.attempt_id && activeAttemptRef.current && payload.attempt_id !== activeAttemptRef.current) return
      }
      if (payload.event === 'job' && payload.job_id) {
        activeJobRef.current = payload.job_id
        activeAttemptRef.current = payload.attempt_id ?? null
        setActiveJob(payload.job_id)
        setResults(null)
      } else if (payload.event === 'progress' && payload.stage) {
        setStages((previous) => ({ ...previous, [payload.stage!]: { fraction: payload.fraction ?? -1, message: payload.message ?? '', displayStage: payload.display_stage, operation: payload.operation, indeterminate: payload.indeterminate ?? (payload.fraction ?? -1) < 0, elapsedSeconds: payload.elapsed_seconds, stageElapsedSeconds: payload.stage_elapsed_seconds, etaSeconds: payload.eta_seconds, bytesDone: payload.bytes_done, bytesTotal: payload.bytes_total, bytesPerSecond: payload.bytes_per_second, accelerator: payload.accelerator, oneTimeDownload: payload.one_time_download } }))
      } else if (payload.event === 'terminal') {
        setActiveDiagnosticId(payload.diagnostic_id ?? null)
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
          setRunNotice(payload.code === 'NO_RECOMMENDED_CLIPS' ? (payload.message ?? 'No recommended clips were found.') : null)
          api.jobResults(activeJobRef.current).then((result) => { const checked = requireValidJobResults(result); if (!disposed) { setActiveDiagnosticId(checked.score?.diagnostic_id ?? payload.diagnostic_id ?? null); setResults(checked); setView('review') } }).catch((error) => { if (!disposed) setRunError(friendlyErrorMessage(error, 'Results could not be loaded. Retry the job.')) })
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
        if (payload.ok && activeJobRef.current && payload.stages) api.jobResults(activeJobRef.current).then((result) => { const checked = requireValidJobResults(result); if (!disposed) { setActiveDiagnosticId(checked.score?.diagnostic_id ?? payload.diagnostic_id ?? null); setResults(checked); setView('review') } }).catch((error) => { if (!disposed) setRunError(friendlyErrorMessage(error, 'Results could not be loaded. Retry the job.')) })
        else if (!payload.ok) setRunError('The video could not be processed. Retry the job.')
      } else if (payload.event === 'exited') {
        setRunning(false)
        setRunState('FAILED')
        setCancelling(false)
        setRunNotice(null)
        setRunError('The video stopped before finishing. Retry the job and keep the diagnostic details for support.')
      }
    }).then((unlisten) => { if (disposed) unlisten(); else unlistenRef.current = unlisten }).catch(() => {
      if (!disposed) setRunError('Pipeline events are unavailable. Restart ClipGauge and retry.')
    })
    return () => { disposed = true; unlistenRef.current?.() }
  }, [refreshJobs])

  const startRun = useCallback(async (source: string, provider: string, captions: string, model?: string, endpoint?: string, auth?: string, secretHeader?: string, browserSession?: string, qualityMode = 'private', outputPreference = 'recommended') => {
    setRunning(true)
    setRunState('RUNNING')
    setRunStartedAt(Date.now())
    setCancelling(false)
    setRunError(null)
    setRunErrorCode(null)
    setRunNotice(null)
    setStages({})
    setResults(null)
    prepareAttempt(null)
    try {
      const savedModel = provider !== 'clipgauge-local' ? readSavedProviderModel(provider) : undefined
      const resolvedLocalModel = async () => {
        if (selectedLocalModelRef.current) return selectedLocalModelRef.current
        const inventory = await api.setupInventory()
        if (!mountedRef.current) return undefined
        if (!isLocalSetupInventory(inventory)) return undefined
        writeCachedSetupInventory(inventory)
        const discovered = resolveSelectedLocalModel(inventory)
        if (discovered) {
          selectedLocalModelRef.current = discovered
          setSelectedLocalModelId(discovered)
        }
        return discovered
      }
      const resolvedModel = model ?? savedModel ?? (provider === 'clipgauge-local' ? await resolvedLocalModel() : undefined)
      if (!mountedRef.current) return
      const endpointConfigured = provider === 'custom' || provider === 'cloudflare'
      const resolvedEndpoint = endpoint ?? (endpointConfigured ? readSavedProviderEndpoint(provider) : undefined)
      const resolvedAuth = auth ?? (endpointConfigured ? 'bearer' : undefined)
      const preflight = await api.preflight(provider, resolvedModel, resolvedEndpoint, resolvedAuth, secretHeader, source, qualityMode)
      if (!mountedRef.current) return
      if (!isPreflightResult(preflight)) throw new Error('Preflight response is malformed. Open Setup and retry.')
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
      if (!mountedRef.current) return
      setRunning(true)
      setRunState('RUNNING')
      setRunStartedAt(Date.now())
      await api.runJob(source, provider, captions, resolvedModel, resolvedEndpoint, resolvedAuth, secretHeader, browserSession, qualityMode, outputPreference)
    } catch (error) {
      if (!mountedRef.current) return
      setRunning(false)
      setRunState('FAILED')
      setRunError(friendlyErrorMessage(error, 'The video could not be processed. Retry the job.'))
      setRunErrorCode(null)
    }
  }, [prepareAttempt])

  const openJob = useCallback(async (jobId: string) => {
    try {
      const result = requireValidJobResults(await api.jobResults(jobId))
      if (!mountedRef.current) return
      setActiveJob(jobId)
      setActiveDiagnosticId(result.score?.diagnostic_id ?? null)
      setResults(result)
      if (result.render?.outputs?.length || result.outcome === 'SUCCESS_NO_RECOMMENDATIONS') setView('review')
    } catch (error) {
      if (!mountedRef.current) return
      setSection('create')
      setRunError(friendlyErrorMessage(error, 'This session could not be opened. Retry from Sessions.'))
    }
  }, [])

  const resumeJobAction = useCallback(async (jobId: string, provider?: string, captions?: string, camera?: string, model?: string, endpoint?: string, auth?: string, secretHeader?: string, allowCpuAsrFallback = false, notice = 'Starting recovery…', qualityMode?: string, outputPreference?: string) => {
    prepareAttempt(jobId)
    setRunning(true)
    setRunState('RUNNING')
    setRunStartedAt(Date.now())
    setCancelling(false)
    setRunError(null)
    setRunErrorCode(null)
    setRunNotice(notice)
    setStages({})
    try {
      await api.resumeJob(jobId, provider, captions, camera, model, endpoint, auth, secretHeader, allowCpuAsrFallback, qualityMode, outputPreference)
    } catch (error) {
      if (!mountedRef.current) return
      setRunning(false)
      setRunState('FAILED')
      setRunNotice(null)
      setRunError(friendlyErrorMessage(error, 'The session could not be resumed. Retry the job.'))
      attemptExpectationRef.current = { jobId, attemptId: activeAttemptRef.current, previousAttemptId: activeAttemptRef.current, awaitingJob: false }
    }
  }, [prepareAttempt])

  const continueCpu = useCallback(() => {
    const jobId = activeJobRef.current ?? activeJob
    if (!jobId) return
    void resumeJobAction(jobId, undefined, undefined, undefined, undefined, undefined, undefined, undefined, true, 'Starting CPU recovery…')
  }, [activeJob, resumeJobAction])

  const repairGpu = useCallback(async () => {
    setGpuRepairing(true)
    setRunError(null)
    try {
      await api.repairGpu()
      if (mountedRef.current) setRunNotice('GPU speech acceleration repair completed. Retry the job.')
    } catch (error) {
      if (mountedRef.current) setRunError(friendlyErrorMessage(error, 'GPU repair could not start. Retry from Setup & Storage.'))
    } finally {
      if (mountedRef.current) setGpuRepairing(false)
    }
  }, [])

  const resumeFromSessions = useCallback((jobId: string) => {
    setSection('create')
    void resumeJobAction(jobId)
  }, [resumeJobAction])

  const resumeFromReview = useCallback((jobId: string, captions?: string, camera?: string) => {
    setSection('create')
    setView('shell')
    void resumeJobAction(jobId, undefined, captions, camera, undefined, undefined, undefined, undefined, false, 'Starting restyle…')
  }, [resumeJobAction])


  if (view === 'boot') return <div className="boot" />
  if (view === 'onboarding') return <Onboarding onDone={() => { void Promise.resolve(api.markOnboarded()).catch((error) => setRunError(friendlyErrorMessage(error, 'Setup completion could not be saved. Restart ClipGauge and retry.'))); setSetup((current) => { const next = current ? { ...current, onboarded: true } : { onboarded: true, has_gemini_key: false }; writeCachedSetupState(next); return next }); setView('shell') }} />
  if (view === 'loop') return <Loop onBack={() => { setSection('integrations'); setView('shell') }} />
  if (view === 'review' && results) return <Review results={results} onBack={() => { setSection('create'); setView('shell'); refreshJobs() }} onRestyle={(captions, camera) => resumeFromReview(results.job_id, captions, camera)} />

  function navigate(next: AppSection) {
    setRunError(null)
    setRunErrorCode(null)
    setRunNotice(null)
    if (next === 'sessions' && jobsError) refreshJobs()
    setSection(next)
  }

  let content
  if (section === 'create') content = <Studio jobs={jobs} running={running} runState={runState} cancelling={cancelling} startedAt={runStartedAt} stages={stages} error={runError} errorCode={runErrorCode} notice={runNotice} onRun={startRun} localModelId={selectedLocalModelId ?? undefined} onContinueCpu={continueCpu} onRepairGpu={repairGpu} gpuRepairing={gpuRepairing} onCancel={() => { if (!activeJob) return; setCancelling(true); api.cancelJob(activeJob).catch((error) => { if (!mountedRef.current) return; setCancelling(false); setRunError(friendlyErrorMessage(error, 'The job could not be cancelled. Retry the action.')) }) }} onNavigate={navigate} selectedProvider={selectedProvider} onSelectProvider={setSelectedProvider} onOpenJob={openJob} onResume={(id) => { void resumeJobAction(id) }} />
  else if (section === 'sessions') content = <Sessions jobs={jobs} onBack={() => setSection('create')} onOpenJob={openJob} onResume={resumeFromSessions} />
  else if (section === 'setup') content = <SetupCenter jobs={jobs} onBack={() => setSection('create')} onUseLocal={(modelId) => { if (modelId) setSelectedLocalModelId(modelId); setSelectedProvider('clipgauge-local'); setSection('create') }} />
  else if (section === 'providers') content = <ProviderCenter selectedProvider={selectedProvider} onSelectProvider={setSelectedProvider} onSelectLocalModel={setSelectedLocalModelId} onBack={() => setSection('create')} onOpenSetup={() => setSection('setup')} />
  else if (section === 'integrations') content = <Integrations onBack={() => setSection('create')} onOpenLoop={() => setView('loop')} />
  else if (section === 'privacy') content = <PrivacyPanel provider={selectedProvider} onBack={() => setSection('create')} />
  else if (section === 'help') content = <SupportPage onBack={() => setSection('create')} onNavigate={(next) => setSection(next)} provider={selectedProvider} currentJobId={activeJob} currentDiagnosticId={activeDiagnosticId} />
  else content = <About onBack={() => setSection('create')} />

  return <AppShell active={section} onNavigate={navigate} jobs={jobs} jobsError={jobsError} running={running} onOpenJob={openJob} onResume={resumeFromSessions} onSupport={() => setSection('help')}>{content}</AppShell>
}

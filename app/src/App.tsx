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
import { normalizeLocalModelState, readSavedLocalModel, writeSavedLocalModel, type LocalModelState } from './localModelState'
import { readCachedSetupInventory, writeCachedSetupInventory } from './setupInventoryCache'
import { normalizeJobResults } from './jobResultsValidation'
import { isInstagramStatus, isJobSummaryList, isLocalSetupInventory, isPreflightResult, isSetupState } from './nativeValidation'
import { friendlyErrorMessage } from './errorMessaging'
import { isCloudProvider, type QualityMode } from './providerContract'
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

function readSavedValue(key: string): string | undefined {
  try { return window.localStorage.getItem(key) ?? undefined } catch { return undefined }
}

function writeSavedValue(key: string, value: string): void {
  try { window.localStorage.setItem(key, value) } catch { /* optional browser storage */ }
}

function readQualityMode(): QualityMode {
  const value = readSavedValue('clipgauge.quality-mode.v1')
  return value === 'balanced' || value === 'best' ? value : 'private'
}

function readCloudProvider(): string {
  const value = readSavedValue('clipgauge.cloud-provider.v1')
  return value && isCloudProvider(value) ? value : 'openrouter'
}

const SETUP_STATE_CACHE_KEY = 'clipgauge.setup.state.v1'
const RESULTS_LOAD_FAILURE_MESSAGE = 'Your clips were created, but Review could not load them.'
const PROVIDER_QUALIFICATION_TTL_MS = 10 * 60 * 1000

type SavedProviderQualification = { checkedAt: string; modelAvailable: boolean; modelCompatible: boolean; serviceReady: boolean; endpointReady: boolean }

function readProviderQualification(provider: string): SavedProviderQualification | null {
  try {
    const raw = window.localStorage.getItem(`clipgauge.provider-readiness.${provider}`)
    if (!raw) return null
    const value: unknown = JSON.parse(raw)
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
    const record = value as Partial<SavedProviderQualification>
    if (typeof record.checkedAt !== 'string' || !Number.isFinite(Date.parse(record.checkedAt))) return null
    if (Date.now() - Date.parse(record.checkedAt) > PROVIDER_QUALIFICATION_TTL_MS) return null
    if (typeof record.modelAvailable !== 'boolean' || typeof record.modelCompatible !== 'boolean' || typeof record.serviceReady !== 'boolean' || typeof record.endpointReady !== 'boolean') return null
    return { checkedAt: record.checkedAt, modelAvailable: record.modelAvailable, modelCompatible: record.modelCompatible, serviceReady: record.serviceReady, endpointReady: record.endpointReady }
  } catch {
    return null
  }
}

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

function requireValidJobResults(value: unknown): JobResults {
  const normalized = normalizeJobResults(value)
  if (!normalized) throw new Error('Saved session results are malformed. Retry the session or run the video again.')
  return normalized
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
  ASR_RESOURCE_LIMIT: 'This audio is too large for safe speech recognition on this computer. Try a shorter video or Low-memory mode.',
  ASR_MODEL_LOAD_FAILED: 'Speech recognition could not load its model. Repair speech recognition, then retry.',
  ASR_AUDIO_LOAD_FAILED: 'Speech recognition could not read this video audio. Retry the job or choose another video.',
  ASR_TRANSCRIPTION_FAILED: 'Speech recognition could not complete. Retry the job or repair speech recognition.',
  ASR_VAD_FAILED: 'Speech activity detection could not start. Repair speech recognition, then retry.',
  ASR_ALIGNMENT_FAILED: 'Word timing could not complete. Retry the job or repair speech recognition.',
  ASR_CHECKPOINT_WRITE: 'Speech recognition finished, but its checkpoint could not be saved. Retry the job.',
  ASR_GPU_FALLBACK_REQUIRES_APPROVAL: 'GPU speech acceleration failed. Repair GPU acceleration, or explicitly continue in slower CPU mode.',
  ASR_RESOURCE_HEADROOM_LOW: 'Speech recognition needs more available memory. Close applications, then retry in Low-memory mode.',
  PIPELINE_RESOURCE_EXHAUSTED: 'ClipGauge stopped because system resources became insufficient. Close applications, free disk space, then retry.',
  DISK_SPACE_LOW: 'This run needs more free disk space. Open Setup & Storage, then retry.',
  LOCAL_MODEL_NOT_RUNNABLE: 'The selected local model is not verified yet. Open Setup & Storage and choose a ready model.',
  PIPELINE_NATIVE_CRASH: 'The local pipeline stopped unexpectedly. Retry once and keep the diagnostic details for support.',
  ASR_NATIVE_CRASH: 'Speech recognition stopped unexpectedly. Retry once, or continue with CPU recovery.',
  CUDA_NATIVE_CRASH: 'CUDA speech processing stopped unexpectedly. Continue once in slower CPU mode, or repair GPU acceleration.',
  WINDOWS_ACCESS_VIOLATION: 'Windows stopped speech processing unexpectedly. Continue once in slower CPU mode, then keep the diagnostic details.'
}

export default function App() {
  const [cachedSetupState] = useState<SetupState | null>(() => readCachedSetupState())
  const [view, setView] = useState<View>(cachedSetupState ? (cachedSetupState.onboarded ? 'shell' : 'onboarding') : 'boot')
  const [section, setSection] = useState<AppSection>('create')
  const [setup, setSetup] = useState<SetupState | null>(cachedSetupState)
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
  const [resultsLoadJobId, setResultsLoadJobId] = useState<string | null>(null)
  const [finalElapsedSeconds, setFinalElapsedSeconds] = useState<number | null>(null)
  const [selectedProvider, setSelectedProvider] = useState(() => readSavedValue('clipgauge.selected-provider.v1') ?? 'clipgauge-local')
  const [selectedLocalProvider, setSelectedLocalProvider] = useState(() => readSavedValue('clipgauge.local-provider.v1') ?? 'clipgauge-local')
  const [selectedCloudProvider, setSelectedCloudProvider] = useState(readCloudProvider)
  const [selectedCloudModel, setSelectedCloudModel] = useState<string | null>(() => readSavedProviderModel(readCloudProvider()) ?? null)
  const [qualityMode, setQualityMode] = useState<QualityMode>(readQualityMode)
  const [localModelState, setLocalModelState] = useState<LocalModelState>(() => normalizeLocalModelState(readCachedSetupInventory(), readSavedLocalModel()))
  const [cpuResumeAvailable, setCpuResumeAvailable] = useState(false)
  const [gpuRepairing, setGpuRepairing] = useState(false)
  const unlistenRef = useRef<(() => void) | null>(null)
  const activeJobRef = useRef<string | null>(null)
  const activeAttemptRef = useRef<string | null>(null)
  const attemptExpectationRef = useRef<AttemptExpectation | null>(null)
  const jobsRequestRef = useRef(0)
  const resultsRequestRef = useRef(0)
  const mountedRef = useRef(true)
  const runStartedAtRef = useRef<number | null>(null)
  const lastElapsedSecondsRef = useRef<number | null>(null)
  activeJobRef.current = activeJob
  const cloudConfigured = Boolean(isCloudProvider(selectedCloudProvider)
    && (selectedCloudProvider === 'gemini'
      ? Boolean(setup?.has_gemini_key)
      : Boolean(setup?.provider_keys?.[selectedCloudProvider] ?? setup?.provider_keys?.[`preset-${selectedCloudProvider}`])))
  const providerQualification = readProviderQualification(selectedCloudProvider)
  const refreshSetupState = useCallback(() => {
    return api.setupState().then((state) => {
      if (!isSetupState(state) || !mountedRef.current) return false
      setSetup(state)
      writeCachedSetupState(state)
      return true
    }).catch(() => false)
  }, [])

  const refreshLocalModelState = useCallback(async (modelId?: string): Promise<LocalModelState | null> => {
    setLocalModelState((current) => ({ ...current, loading: true, error: null }))
    try {
      const inventory = await api.setupInventory(modelId)
      if (!isLocalSetupInventory(inventory)) throw new Error('Setup inventory is malformed. Open Setup and retry.')
      writeCachedSetupInventory(inventory)
      const next = normalizeLocalModelState(inventory, readSavedLocalModel())
      setLocalModelState(next)
      return next
    } catch (error) {
      const message = friendlyErrorMessage(error, 'Local model state could not be refreshed. Open Setup and retry.')
      setLocalModelState((current) => ({ ...current, loading: false, error: message }))
      return null
    }
  }, [])

  const saveAndRefreshLocalModel = useCallback(async (modelId: string) => {
    await api.saveLocalModel(modelId)
    writeSavedLocalModel(modelId)
    const next = await refreshLocalModelState(modelId)
    if (!next) throw new Error('Local model state could not be refreshed after saving.')
  }, [refreshLocalModelState])

  const selectProvider = useCallback((provider: string) => {
    setSelectedProvider(provider)
    writeSavedValue('clipgauge.selected-provider.v1', provider)
    setRunNotice(null)
    setRunError(null)
    setRunErrorCode(null)
    if (isCloudProvider(provider)) {
      setSelectedCloudProvider(provider)
      writeSavedValue('clipgauge.cloud-provider.v1', provider)
      setSelectedCloudModel(readSavedProviderModel(provider) ?? null)
      void refreshSetupState()
    } else {
      setSelectedLocalProvider(provider)
      writeSavedValue('clipgauge.local-provider.v1', provider)
      void refreshLocalModelState()
    }
  }, [refreshLocalModelState, refreshSetupState])

  const selectQualityMode = useCallback((mode: QualityMode) => {
    setQualityMode(mode)
    writeSavedValue('clipgauge.quality-mode.v1', mode)
  }, [])

  const prepareAttempt = useCallback((jobId: string | null) => {
    resultsRequestRef.current += 1
    const previousAttemptId = activeAttemptRef.current
    attemptExpectationRef.current = { jobId, attemptId: null, previousAttemptId, awaitingJob: true }
    activeJobRef.current = jobId
    activeAttemptRef.current = null
    setActiveJob(jobId)
    setResults(null)
    setResultsLoadJobId(null)
    setActiveDiagnosticId(null)
    setCpuResumeAvailable(false)
  }, [])

  const loadResults = useCallback((jobId: string, diagnosticId?: string | null, failureMessage = RESULTS_LOAD_FAILURE_MESSAGE) => {
    const requestId = ++resultsRequestRef.current
    setResultsLoadJobId(jobId)
    return api.jobResults(jobId).then((result) => {
      const checked = requireValidJobResults(result)
      if (!mountedRef.current || requestId !== resultsRequestRef.current || activeJobRef.current !== jobId) return false
      setActiveDiagnosticId(checked.score?.diagnostic_id ?? diagnosticId ?? null)
      setResults(checked)
      setResultsLoadJobId(null)
      setRunError(null)
      setView('review')
      return true
    }).catch(() => {
      if (mountedRef.current && requestId === resultsRequestRef.current && activeJobRef.current === jobId) setRunError(failureMessage)
      return false
    })
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
    void refreshLocalModelState()
    api.setupState().then((state) => {
      if (!active) return
      if (!isSetupState(state)) throw new Error('Setup state is malformed.')
      writeCachedSetupState(state)
      setSetup(state)
      setView(state.onboarded ? 'shell' : 'onboarding')
    }).catch(() => { if (active && !cachedSetupState) setView('onboarding') })
    refreshJobs()
    return () => { active = false; mountedRef.current = false }
  }, [cachedSetupState, refreshJobs, refreshLocalModelState])

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
        setRunNotice(null)
      } else if (payload.event === 'progress' && payload.stage) {
        setRunNotice(null)
        if (typeof payload.elapsed_seconds === 'number' && Number.isFinite(payload.elapsed_seconds)) lastElapsedSecondsRef.current = payload.elapsed_seconds
        setStages((previous) => ({ ...previous, [payload.stage!]: { fraction: payload.fraction ?? -1, message: payload.message ?? '', displayStage: payload.display_stage, operation: payload.operation, indeterminate: payload.indeterminate ?? (payload.fraction ?? -1) < 0, elapsedSeconds: payload.elapsed_seconds, stageElapsedSeconds: payload.stage_elapsed_seconds, etaSeconds: payload.eta_seconds, bytesDone: payload.bytes_done, bytesTotal: payload.bytes_total, bytesPerSecond: payload.bytes_per_second, accelerator: payload.accelerator, oneTimeDownload: payload.one_time_download } }))
      } else if (payload.event === 'terminal') {
        const terminalElapsed = typeof payload.elapsed_seconds === 'number' && Number.isFinite(payload.elapsed_seconds)
          ? payload.elapsed_seconds
          : lastElapsedSecondsRef.current ?? (runStartedAtRef.current ? Math.max(0, Math.floor((Date.now() - runStartedAtRef.current) / 1000)) : 0)
        lastElapsedSecondsRef.current = terminalElapsed
        setFinalElapsedSeconds(terminalElapsed)
        setActiveDiagnosticId(payload.diagnostic_id ?? null)
        setRunning(false)
        setCancelling(false)
        setRunStartedAt(null)
        runStartedAtRef.current = null
        refreshJobs()
        if (payload.code === 'CANCELLED') {
          setCpuResumeAvailable(false)
          setRunState('CANCELLED')
          setRunError(null)
          setRunNotice(payload.message ?? 'Job cancelled. Completed work remains available to resume.')
        } else if (payload.ok && activeJobRef.current) {
          setCpuResumeAvailable(false)
          setRunState('SUCCEEDED')
          setRunNotice(payload.code === 'NO_RECOMMENDED_CLIPS' ? (payload.message ?? 'No recommended clips were found.') : null)
          void loadResults(activeJobRef.current, payload.diagnostic_id)
        } else if (!payload.ok) {
          setCpuResumeAvailable(payload.allow_cpu_resume === true)
          setRunState('FAILED')
          setRunErrorCode(payload.code ?? null)
          setRunNotice(null)
          const friendly = payload.code ? FRIENDLY_FAILURES[payload.code] : undefined
          const diagnostic = payload.diagnostic_id ? ` Technical details: ${payload.diagnostic_id}.` : ''
          setRunError(`${friendly ?? payload.message ?? 'The video could not be processed.'}${diagnostic}`)
        }
      } else if (payload.event === 'result') {
        setCpuResumeAvailable(false)
        const resultElapsed = typeof payload.elapsed_seconds === 'number' && Number.isFinite(payload.elapsed_seconds)
          ? payload.elapsed_seconds
          : lastElapsedSecondsRef.current ?? (runStartedAtRef.current ? Math.max(0, Math.floor((Date.now() - runStartedAtRef.current) / 1000)) : 0)
        lastElapsedSecondsRef.current = resultElapsed
        setFinalElapsedSeconds(resultElapsed)
        setRunning(false)
        setCancelling(false)
        setRunStartedAt(null)
        runStartedAtRef.current = null
        setRunNotice(null)
        setRunState(payload.ok ? 'SUCCEEDED' : 'FAILED')
        refreshJobs()
        if (payload.ok && activeJobRef.current && payload.stages) void loadResults(activeJobRef.current, payload.diagnostic_id)
        else if (!payload.ok) setRunError('The video could not be processed. Retry the job.')
      } else if (payload.event === 'exited') {
        const terminalElapsed = lastElapsedSecondsRef.current ?? (runStartedAtRef.current ? Math.max(0, Math.floor((Date.now() - runStartedAtRef.current) / 1000)) : 0)
        lastElapsedSecondsRef.current = terminalElapsed
        setFinalElapsedSeconds(terminalElapsed)
        setRunning(false)
        setRunState('FAILED')
        setCancelling(false)
        setRunStartedAt(null)
        runStartedAtRef.current = null
        setRunNotice(null)
        setRunErrorCode(payload.code ?? 'PIPELINE_NATIVE_CRASH')
        setCpuResumeAvailable(payload.allow_cpu_resume === true)
        const friendly = payload.code ? FRIENDLY_FAILURES[payload.code] : undefined
        const diagnostic = payload.diagnostic_id ? ` Technical details: ${payload.diagnostic_id}.` : ''
        setRunError(`${friendly ?? payload.message ?? 'The video stopped unexpectedly.'}${diagnostic}`)
      }
    }).then((unlisten) => { if (disposed) unlisten(); else unlistenRef.current = unlisten }).catch(() => {
      if (!disposed) setRunError('Pipeline events are unavailable. Restart ClipGauge and retry.')
    })
    return () => { disposed = true; unlistenRef.current?.() }
  }, [loadResults, refreshJobs])

  const startRun = useCallback(async (source: string, provider: string, captions: string, model?: string, endpoint?: string, auth?: string, secretHeader?: string, browserSession?: string, qualityMode = 'private', outputPreference = 'recommended') => {
    setRunning(true)
    setRunState('RUNNING')
    const startedAt = Date.now()
    runStartedAtRef.current = startedAt
    lastElapsedSecondsRef.current = null
    setFinalElapsedSeconds(null)
    setRunStartedAt(startedAt)
    setCancelling(false)
    setRunError(null)
    setRunErrorCode(null)
    setRunNotice(null)
    setStages({})
    setResults(null)
    prepareAttempt(null)
    try {
      const savedModel = provider !== 'clipgauge-local' ? readSavedProviderModel(provider) : undefined
      const refreshedLocalState = provider === 'clipgauge-local' ? await refreshLocalModelState() : null
      const resolvedModel = provider === 'clipgauge-local' ? refreshedLocalState?.runnableModelId ?? undefined : model ?? savedModel
      if (!mountedRef.current) return
      if (provider === 'clipgauge-local' && !resolvedModel) {
        setRunning(false)
        setRunStartedAt(null)
        runStartedAtRef.current = null
        setRunState('FAILED')
        setRunErrorCode('LOCAL_MODEL_NOT_RUNNABLE')
        setRunError('Choose a verified, runnable local model in Setup & Storage first.')
        return
      }
      const endpointConfigured = provider === 'custom' || provider === 'cloudflare'
      const resolvedEndpoint = endpoint ?? (endpointConfigured ? readSavedProviderEndpoint(provider) : undefined)
      const resolvedAuth = auth ?? (endpointConfigured ? 'bearer' : undefined)
      const preflight = await api.preflight(provider, resolvedModel, resolvedEndpoint, resolvedAuth, secretHeader, source, qualityMode)
      if (!mountedRef.current) return
      if (!isPreflightResult(preflight)) throw new Error('Preflight response is malformed. Open Setup and retry.')
      const blocked = preflight.checks.filter((check) => check.state === 'blocked')
      const warnings = preflight.checks.filter((check) => check.state === 'warning')
      if (preflight.state === 'blocked' || blocked.length) {
        const preflightElapsed = lastElapsedSecondsRef.current ?? (runStartedAtRef.current ? Math.max(0, Math.floor((Date.now() - runStartedAtRef.current) / 1000)) : 0)
        lastElapsedSecondsRef.current = preflightElapsed
        setRunning(false)
        setRunStartedAt(null)
        runStartedAtRef.current = null
        setFinalElapsedSeconds(preflightElapsed)
        setRunState('FAILED')
        const first = blocked[0]
        setRunError(`${first?.message ?? 'This run needs a setup step first.'}${first?.remediation ? ` ${first.remediation}` : ''}`)
        return
      }
      if (warnings.length) setRunNotice(`Before you start: ${warnings.slice(0, 2).map((check) => check.message).join(' ')}`)
      if (!mountedRef.current) return
      await api.runJob(source, provider, captions, resolvedModel, resolvedEndpoint, resolvedAuth, secretHeader, browserSession, qualityMode, outputPreference)
    } catch (error) {
      if (!mountedRef.current) return
      const elapsed = lastElapsedSecondsRef.current ?? (runStartedAtRef.current ? Math.max(0, Math.floor((Date.now() - runStartedAtRef.current) / 1000)) : 0)
      lastElapsedSecondsRef.current = elapsed
      setFinalElapsedSeconds(elapsed)
      setRunning(false)
      setRunStartedAt(null)
      runStartedAtRef.current = null
      setRunState('FAILED')
      setRunError(friendlyErrorMessage(error, 'The video could not be processed. Retry the job.'))
      setRunErrorCode(null)
    }
  }, [prepareAttempt, refreshLocalModelState])

  const openJob = useCallback(async (jobId: string) => {
    resultsRequestRef.current += 1
    activeJobRef.current = jobId
    setActiveJob(jobId)
    setResults(null)
    try {
      const loaded = await loadResults(jobId, null, 'This session could not be opened. Retry from Sessions.')
      if (!mountedRef.current) return
      if (!loaded && activeJobRef.current === jobId) setSection('create')
    } catch { /* loadResults owns its user-facing error */ }
  }, [loadResults])

  const resumeJobAction = useCallback(async (jobId: string, provider?: string, captions?: string, camera?: string, model?: string, endpoint?: string, auth?: string, secretHeader?: string, allowCpuAsrFallback = false, notice = 'Starting recovery…', qualityMode?: string, outputPreference?: string) => {
    prepareAttempt(jobId)
    setRunning(true)
    setRunState('RUNNING')
    const startedAt = Date.now()
    runStartedAtRef.current = startedAt
    lastElapsedSecondsRef.current = null
    setFinalElapsedSeconds(null)
    setRunStartedAt(startedAt)
    setCancelling(false)
    setRunError(null)
    setRunErrorCode(null)
    setRunNotice(notice)
    setStages({})
    try {
      await api.resumeJob(jobId, provider, captions, camera, model, endpoint, auth, secretHeader, allowCpuAsrFallback, qualityMode, outputPreference)
    } catch (error) {
      if (!mountedRef.current) return
      const elapsed = lastElapsedSecondsRef.current ?? (runStartedAtRef.current ? Math.max(0, Math.floor((Date.now() - runStartedAtRef.current) / 1000)) : 0)
      lastElapsedSecondsRef.current = elapsed
      setFinalElapsedSeconds(elapsed)
      setRunning(false)
      setRunStartedAt(null)
      runStartedAtRef.current = null
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

  const retryResults = useCallback(() => {
    if (!resultsLoadJobId) return
    void loadResults(resultsLoadJobId, activeDiagnosticId)
  }, [activeDiagnosticId, loadResults, resultsLoadJobId])

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
    resultsRequestRef.current += 1
    setRunError(null)
    setRunErrorCode(null)
    setRunNotice(null)
    if (next === 'sessions' && jobsError) refreshJobs()
    setSection(next)
  }

  let content
  if (section === 'create') content = <Studio jobs={jobs} running={running} runState={runState} cancelling={cancelling} startedAt={runStartedAt} elapsedSeconds={finalElapsedSeconds} stages={stages} error={runError} errorCode={runErrorCode} cpuResumeAvailable={cpuResumeAvailable} notice={runNotice} resultsLoadFailed={Boolean(resultsLoadJobId)} onRetryResults={retryResults} onRun={startRun} localModelId={selectedLocalProvider === 'clipgauge-local' ? localModelState.preferredModelId ?? undefined : undefined} localModelReady={selectedLocalProvider === 'clipgauge-local' ? Boolean(localModelState.runnableModelId && localModelState.runnableModelId === localModelState.preferredModelId) : undefined} localModelLoading={selectedLocalProvider === 'clipgauge-local' ? localModelState.loading : false} localModelError={selectedLocalProvider === 'clipgauge-local' ? localModelState.error : null} selectedLocalProvider={selectedLocalProvider} selectedCloudProvider={selectedCloudProvider} selectedCloudModel={selectedCloudModel} cloudModelAvailable={providerQualification?.modelAvailable} cloudModelCompatible={providerQualification?.modelCompatible} cloudServiceReady={providerQualification?.serviceReady} cloudConfigured={cloudConfigured} providerEndpoint={selectedCloudProvider === 'custom' || selectedCloudProvider === 'cloudflare' ? readSavedProviderEndpoint(selectedCloudProvider) : undefined} qualityMode={qualityMode} onQualityModeChange={selectQualityMode} onContinueCpu={continueCpu} onRepairGpu={repairGpu} gpuRepairing={gpuRepairing} onCancel={() => { if (!activeJob) return; setCancelling(true); api.cancelJob(activeJob).catch((error) => { if (!mountedRef.current) return; setCancelling(false); setRunError(friendlyErrorMessage(error, 'The job could not be cancelled. Retry the action.')) }) }} onNavigate={navigate} selectedProvider={selectedProvider} onSelectProvider={selectProvider} onOpenJob={openJob} onResume={(id) => { void resumeJobAction(id) }} />
  else if (section === 'sessions') content = <Sessions jobs={jobs} onBack={() => setSection('create')} onOpenJob={openJob} onResume={resumeFromSessions} />
  else if (section === 'setup') content = <SetupCenter jobs={jobs} localModelState={localModelState} onRefreshLocalModelState={refreshLocalModelState} onSaveLocalModel={saveAndRefreshLocalModel} onBack={() => { void refreshLocalModelState(); setSection('create') }} onUseLocal={(modelId) => { if (typeof modelId === 'string' && modelId !== localModelState.preferredModelId) void saveAndRefreshLocalModel(modelId); selectProvider('clipgauge-local'); selectQualityMode('private'); setSection('create') }} />
  else if (section === 'providers') content = <ProviderCenter selectedProvider={selectedProvider} localModelState={localModelState} onRefreshLocalModelState={refreshLocalModelState} onSaveLocalModel={saveAndRefreshLocalModel} onSelectCloudModel={(provider, model) => { setSelectedCloudProvider(provider); setSelectedCloudModel(model); writeSavedValue('clipgauge.cloud-provider.v1', provider); writeSavedValue(`clipgauge.provider-model.${provider}`, model) }} onSelectProvider={selectProvider} onBack={() => { void refreshSetupState(); void refreshLocalModelState(); setSection('create') }} onOpenSetup={() => setSection('setup')} />
  else if (section === 'integrations') content = <Integrations onBack={() => setSection('create')} onOpenLoop={() => setView('loop')} />
  else if (section === 'privacy') content = <PrivacyPanel provider={qualityMode === 'private' ? selectedLocalProvider : selectedCloudProvider} onBack={() => setSection('create')} />
  else if (section === 'help') content = <SupportPage onBack={() => setSection('create')} onNavigate={(next) => setSection(next)} provider={selectedProvider} currentJobId={activeJob} currentDiagnosticId={activeDiagnosticId} />
  else content = <About onBack={() => setSection('create')} />

  return <AppShell active={section} onNavigate={navigate} jobs={jobs} jobsError={jobsError} running={running} onOpenJob={openJob} onResume={resumeFromSessions} onSupport={() => setSection('help')}>{content}</AppShell>
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown, HardDrive, RotateCcw, ShieldCheck, Square, X } from 'lucide-react'
import { listen } from '@tauri-apps/api/event'
import { api } from '../api'
import type { GpuDiagnostics, JobSummary, LocalSetupInventory, ManagedAssetRow, SetupProgressEvent, YouTubeReadiness } from '../types'
import { assetLifecycleLabel, diskState, formatBytes, formatDuration, formatRate, meaningfulEta, progressPercent } from '../setupFormatting'
import { isLocalAiUnavailable, resolveSelectedLocalModel, summarizeSetupQueue, type SetupQueueSummary } from '../setupState'
import { readCachedSetupInventory, writeCachedSetupInventory } from '../setupInventoryCache'
import { loadErrorMessage, setupPhaseLabel, type SetupLoadState } from '../setupLifecycle'
import { isLocalSetupInventory, isStorageCleanupPreview, isStorageCleanupResult, isYouTubeReadiness as isNativeYouTubeReadiness } from '../nativeValidation'
import { friendlyErrorMessage } from '../errorMessaging'

interface Props { onBack: () => void; onUseLocal?: (modelId?: string) => void; jobs?: JobSummary[] }

type Group = { id: string; title: string; description: string; prefixes: string[]; required: boolean }
type GpuUiState = 'CHECKING' | 'READY' | 'CPU_ONLY' | 'UNAVAILABLE' | 'DEGRADED' | 'REPAIR_REQUIRED'
type GpuLoadState = SetupLoadState<GpuDiagnostics>
type GpuCacheIdentity = {
  gpu_identity: string[]
  driver_version: string[]
  cuda_runtime_fingerprint: string
  cudnn_runtime_fingerprint: string
  pipeline_environment_fingerprint: string | null
}
type GpuCacheRecord = { schema_version: number; app_version: string; identity: GpuCacheIdentity; value: GpuDiagnostics; verifiedAt: string }
const GPU_CACHE_KEY = 'clipgauge.setup.gpu.v1'
const GPU_CACHE_SCHEMA_VERSION = 1
const GPU_CACHE_APP_VERSION = '0.5.16'
const YOUTUBE_CACHE_SCHEMA_VERSION = 1
const YOUTUBE_CACHE_APP_VERSION = '0.5.16'
const GPU_CACHE_TTL_MS = 15 * 60 * 1000

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isGpuDiagnostics(value: unknown): value is GpuDiagnostics {
  if (!isRecord(value)) return false
  const hardware = value.hardware
  if (hardware === undefined) return true
  if (!isRecord(hardware)) return false
  const nvidia = hardware.nvidia
  if (nvidia !== undefined) {
    if (!isRecord(nvidia)) return false
    if (nvidia.gpus !== undefined && (!Array.isArray(nvidia.gpus) || !nvidia.gpus.every(isRecord))) return false
  }
  const cuda = hardware.cuda_ctranslate2
  if (cuda !== undefined && (!isRecord(cuda) || (cuda.compute_types !== undefined && !isStringArray(cuda.compute_types)))) return false
  const pytorch = hardware.pytorch_cuda
  if (pytorch !== undefined && !isRecord(pytorch)) return false
  return true
}

function isGpuCache(value: unknown): value is GpuCacheRecord {
  const identity = isRecord(value) ? value.identity : null
  return isRecord(value)
    && value.schema_version === GPU_CACHE_SCHEMA_VERSION
    && value.app_version === GPU_CACHE_APP_VERSION
    && isRecord(identity)
    && Array.isArray(identity.gpu_identity) && identity.gpu_identity.every((item) => typeof item === 'string')
    && Array.isArray(identity.driver_version) && identity.driver_version.every((item) => typeof item === 'string')
    && typeof identity.cuda_runtime_fingerprint === 'string'
    && typeof identity.cudnn_runtime_fingerprint === 'string'
    && (identity.pipeline_environment_fingerprint === null || typeof identity.pipeline_environment_fingerprint === 'string')
    && typeof value.verifiedAt === 'string'
    && Number.isFinite(Date.parse(value.verifiedAt))
    && isGpuDiagnostics(value.value)
}

function isYouTubeReadiness(value: unknown): value is YouTubeReadiness {
  return isRecord(value)
    && typeof value.state === 'string'
    && typeof value.ready === 'boolean'
    && typeof value.reason === 'string'
    && isStringArray(value.actions)
    && Array.isArray(value.checks)
}

function isYouTubeCache(value: unknown): value is { schema_version: number; app_version: string; value: YouTubeReadiness | null; verifiedAt: string } {
  return isRecord(value)
    && value.schema_version === YOUTUBE_CACHE_SCHEMA_VERSION
    && value.app_version === YOUTUBE_CACHE_APP_VERSION
    && typeof value.verifiedAt === 'string'
    && Number.isFinite(Date.parse(value.verifiedAt))
    && (value.value === null || isYouTubeReadiness(value.value))
}

function readCached<T>(key: string, guard: (value: unknown) => value is T): T | null {
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return null
    const value: unknown = JSON.parse(raw)
    return guard(value) ? value : null
  } catch {
    return null
  }
}

function writeCached<T>(key: string, value: T) {
  try { window.localStorage.setItem(key, JSON.stringify(value)) } catch { /* optional browser storage */ }
}

function gpuCacheIdentity(value: GpuDiagnostics): GpuCacheIdentity {
  const gpus = value.hardware?.nvidia?.gpus ?? []
  const cuda = value.hardware?.cuda_ctranslate2
  const pytorch = value.hardware?.pytorch_cuda
  return {
    gpu_identity: gpus.map((gpu) => String(gpu.name ?? 'unknown')),
    driver_version: gpus.map((gpu) => String(gpu.driver ?? 'unknown')),
    cuda_runtime_fingerprint: JSON.stringify({
      available: cuda?.available ?? null,
      verified: cuda?.verified ?? null,
      device_count: cuda?.device_count ?? null,
      compute_types: cuda?.compute_types ?? [],
      compiled_cuda: pytorch?.compiled_cuda ?? null,
      ready: value.cuda_runtime_ready ?? null,
    }),
    cudnn_runtime_fingerprint: JSON.stringify({ ready: value.cudnn_runtime_ready ?? null }),
    pipeline_environment_fingerprint: value.environment?.expected_fingerprint ?? value.environment?.stored_fingerprint ?? null,
  }
}

function inventoryVerifiedLabel(value: number | null | undefined): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return null
  const date = new Date(value * 1000)
  return Number.isNaN(date.getTime()) ? null : date.toLocaleString()
}

function gpuUiState(load: GpuLoadState, diagnostics: GpuDiagnostics | null, verifiedAt?: string): { state: GpuUiState; reason: string } {
  const lastVerified = verifiedAt ? ` Last verified: ${new Date(verifiedAt).toLocaleString()}.` : ''
  if (load.phase === 'error' && diagnostics) {
    const lastKnown = gpuUiState({ phase: 'ready', value: diagnostics }, diagnostics)
    return { state: lastKnown.state, reason: `Refresh failed — using last verified state.${lastVerified} ${load.message ?? 'Retry diagnostics when convenient.'}` }
  }
  if (load.phase === 'error') return { state: 'UNAVAILABLE', reason: 'GPU diagnostics unavailable. CPU processing remains available. Retry diagnostics when convenient.' }
  if (load.phase === 'loading') return { state: 'CHECKING', reason: 'Checking GPU capabilities…' }
  const nvidia = diagnostics?.hardware?.nvidia
  const cuda = diagnostics?.hardware?.cuda_ctranslate2
  const pytorch = diagnostics?.hardware?.pytorch_cuda
  if (!nvidia?.available && !cuda?.available && !pytorch?.available) return { state: 'CPU_ONLY', reason: 'No supported GPU was detected. CPU processing remains available.' }
  if (!diagnostics?.cuda_runtime_ready || !diagnostics.cudnn_runtime_ready) return { state: 'REPAIR_REQUIRED', reason: diagnostics?.environment?.reason ?? 'Managed CUDA libraries need repair.' }
  if (cuda?.verified && pytorch?.verified) return { state: 'READY', reason: 'CUDA speech transcription and alignment verified.' }
  return { state: 'DEGRADED', reason: pytorch?.reason ?? cuda?.reason ?? 'GPU hardware exists, but one speech path is unavailable.' }
}

const GROUPS: Group[] = [
  { id: 'video', title: 'Video tools', description: 'Read and render video with captions.', prefixes: ['runtime:ffmpeg:'], required: true },
  { id: 'speech', title: 'Speech recognition', description: 'Transcription and word timing.', prefixes: ['model:asr:', 'model:alignment:', 'data:nltk:', 'model:vad:', 'model:silero:'], required: true },
  { id: 'analysis', title: 'Speaker & audio analysis', description: 'Speaker detection, laughter, audio events, and smart camera signals.', prefixes: ['model:laughter:', 'model:panns:', 'model:campplus:', 'model:ultraface:', 'model:lr-asd:'], required: true },
  { id: 'youtube', title: 'YouTube support', description: 'Best-effort public YouTube import; availability depends on YouTube.', prefixes: ['runtime:yt-dlp:', 'runtime:node:', 'youtube:bgutil-provider:'], required: false }
]

const GROUP_COMMANDS: Record<string, string[]> = {
  video: ['install-ffmpeg'],
  speech: ['install-group', '--group', 'core:asr'],
  analysis: ['install-group', '--group', 'core:analysis'],
  youtube: ['install-group', '--group', 'core:youtube']
}

const YOUTUBE_CACHE_KEY = 'clipgauge.setup.youtube.v1'
const YOUTUBE_CACHE_TTL_MS = 15 * 60 * 1000

function assetsFor(inventory: LocalSetupInventory | null, group: Group): ManagedAssetRow[] {
  const rows = (inventory?.managed_assets ?? []).filter((asset) => group.prefixes.some((prefix) => asset.asset_id.startsWith(prefix)))
  const videoTools = inventory?.video_tools
  if (group.id === 'video' && videoTools && !videoTools.ready && rows.some((row) => row.installed)) {
    return rows.map((row) => ({ ...row, installed: false, cached: false, status: 'needs-repair', state: 'NEEDS_REPAIR', reason: videoTools.reason }))
  }
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
    size_bytes: base.size_bytes,
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

function youtubeStatusCopy(status: YouTubeReadiness | null): string {
  if (!status) return 'Checking YouTube tools…'
  if (status.state === 'PUBLIC_DOWNLOAD_VERIFIED') return 'Live public download verified.'
  if (status.state === 'DEPENDENCIES_READY' || status.state === 'READY') {
    return 'YouTube tools installed; live public download is not verified. Local-file import always remains available.'
  }
  return status.reason
}

function youtubeLoadCopy(status: YouTubeReadiness | null, load: SetupLoadState<YouTubeReadiness | null>): string {
  if (load.phase === 'loading') return 'Checking YouTube tools…'
  if (load.phase === 'error') return load.message ?? 'YouTube status is unavailable. Retry the check.'
  return status ? youtubeStatusCopy(status) : 'YouTube status is unavailable. Retry the check.'
}

function statusHasRepair(status: YouTubeReadiness | null): boolean {
  return Boolean(status?.actions.includes('Repair'))
}

function modelLabel(model: Record<string, unknown>, index: number): string {
  const name = String(model.display_name ?? model.asset_id ?? `Local model ${index + 1}`)
  return name.toLowerCase().includes('balanced') ? 'Balanced' : name.toLowerCase().includes('light') ? 'Lightweight' : name
}

export default function SetupCenter({ onBack, onUseLocal, jobs = [] }: Props) {
  const cachedInventoryValue = readCachedSetupInventory()
  const cachedGpu = readCached(GPU_CACHE_KEY, isGpuCache)
  const cachedYouTube = readCached(YOUTUBE_CACHE_KEY, isYouTubeCache)
  const [inventory, setInventory] = useState<LocalSetupInventory | null>(cachedInventoryValue)
  const [inventoryLoad, setInventoryLoad] = useState<SetupLoadState<LocalSetupInventory>>(cachedInventoryValue ? { phase: 'ready', value: cachedInventoryValue } : { phase: 'loading' })
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
  const [youtubeStatus, setYoutubeStatus] = useState<YouTubeReadiness | null>(cachedYouTube?.value ?? null)
  const [youtubeVerifiedAt, setYoutubeVerifiedAt] = useState<string | null>(cachedYouTube?.verifiedAt ?? null)
  const [youtubeLoad, setYoutubeLoad] = useState<SetupLoadState<YouTubeReadiness | null>>(cachedYouTube ? { phase: 'ready', value: cachedYouTube.value } : { phase: 'loading' })
  const [youtubeBusy, setYoutubeBusy] = useState(false)
  const [youtubeApproved, setYoutubeApproved] = useState(false)
  const [cleanupBusy, setCleanupBusy] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState('')
  const [gpuDiagnostics, setGpuDiagnostics] = useState<GpuDiagnostics | null>(cachedGpu?.value ?? null)
  const [gpuVerifiedAt, setGpuVerifiedAt] = useState<string | null>(cachedGpu?.verifiedAt ?? null)
  const [gpuLoad, setGpuLoad] = useState<GpuLoadState>(cachedGpu?.value ? { phase: 'ready', value: cachedGpu.value } : { phase: 'loading' })
  const [gpuBusy, setGpuBusy] = useState(false)
  const youtubeStatusCopy = (status: YouTubeReadiness | null) => {
    const copy = youtubeLoadCopy(status, youtubeLoad)
    if (!youtubeVerifiedAt) return copy
    return `${copy} Last public compatibility test: ${new Date(youtubeVerifiedAt).toLocaleString()}.`
  }
  const queueRef = useRef<string[][]>([])
  const outcomesRef = useRef<Array<'success' | 'failed' | 'cancelled'>>([])
  const currentArgsRef = useRef<string[] | null>(null)
  const failedArgsRef = useRef<string[] | null>(null)
  const failedLabelsRef = useRef<string[]>([])
  const inventoryRequestRef = useRef(0)
  const youtubeRequestRef = useRef(0)
  const gpuRequestRef = useRef(0)
  const modelSaveRequestRef = useRef(0)
  const mountedRef = useRef(true)

  const refreshYouTube = (force = false) => {
    if (!force && cachedYouTube?.verifiedAt && Date.now() - Date.parse(cachedYouTube.verifiedAt) < YOUTUBE_CACHE_TTL_MS) {
      return Promise.resolve(cachedYouTube.value)
    }
    const requestId = ++youtubeRequestRef.current
    setYoutubeLoad({ phase: 'loading' })
    return (api.youtubeReadiness?.() ?? Promise.resolve(null)).then((value) => {
      if (!mountedRef.current || requestId !== youtubeRequestRef.current) return
      if (value !== null && !isNativeYouTubeReadiness(value)) throw new Error('YouTube readiness data is malformed.')
      const next = value as YouTubeReadiness | null
      const verifiedAt = new Date().toISOString()
      setYoutubeStatus(next)
      setYoutubeVerifiedAt(verifiedAt)
      writeCached(YOUTUBE_CACHE_KEY, { schema_version: YOUTUBE_CACHE_SCHEMA_VERSION, app_version: YOUTUBE_CACHE_APP_VERSION, value: next, verifiedAt })
      setYoutubeLoad({ phase: 'ready', value: next })
    }).catch((error) => {
      if (!mountedRef.current || requestId !== youtubeRequestRef.current) return
      setYoutubeLoad({ phase: 'error', value: youtubeStatus, message: youtubeStatus ? `Refresh failed — using last verified state. ${loadErrorMessage(error)}` : loadErrorMessage(error) })
    })
  }

  const refresh = (modelId?: string) => {
    const requestId = ++inventoryRequestRef.current
    if (!inventory) setInventoryLoad({ phase: 'loading' })
    return api.setupInventory(modelId).then((value) => {
      if (!mountedRef.current || requestId !== inventoryRequestRef.current) return
      if (!isLocalSetupInventory(value)) throw new Error('Setup inventory data is malformed.')
      const next = value
      setInventory(next)
      writeCachedSetupInventory(next)
      setInventoryLoad({ phase: 'ready', value: next })
      setSelectedModelId((current) => resolveSelectedLocalModel(next, current) ?? null)
    }).catch((error) => {
      if (mountedRef.current && requestId === inventoryRequestRef.current) setInventoryLoad({ phase: 'error', message: loadErrorMessage(error) })
    })
  }

  const refreshGpu = (force = false) => {
    if (!force && cachedGpu?.verifiedAt && Date.now() - Date.parse(cachedGpu.verifiedAt) < GPU_CACHE_TTL_MS) {
      return Promise.resolve(cachedGpu.value)
    }
    const requestId = ++gpuRequestRef.current
    if (!gpuDiagnostics) setGpuLoad({ phase: 'loading' })
    return api.gpuDiagnostics().then((value) => {
      if (!mountedRef.current || requestId !== gpuRequestRef.current) return
      if (!isGpuDiagnostics(value)) throw new Error('GPU diagnostics data is malformed.')
      setGpuDiagnostics(value)
      const verifiedAt = new Date().toISOString()
      setGpuVerifiedAt(verifiedAt)
      writeCached(GPU_CACHE_KEY, { schema_version: GPU_CACHE_SCHEMA_VERSION, app_version: GPU_CACHE_APP_VERSION, identity: gpuCacheIdentity(value), value, verifiedAt })
      setGpuLoad({ phase: 'ready', value })
    }).catch((error) => {
      if (!mountedRef.current || requestId !== gpuRequestRef.current) return
      setGpuLoad({ phase: 'error', message: loadErrorMessage(error) })
    })
  }

  useEffect(() => {
    mountedRef.current = true
    let disposed = false
    void refresh()
    void refreshYouTube()
    void refreshGpu()
    let stop: (() => void) | undefined
    void listen<SetupProgressEvent>('setup-event', ({ payload }) => {
      if (!mountedRef.current || disposed) return
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
          void refreshYouTube(true)
        }
      }
    }).then((unlisten) => {
      if (disposed) unlisten()
      else stop = unlisten
    }).catch(() => {
      if (mountedRef.current && !disposed) setMessage('Setup progress events are unavailable. Restart ClipGauge and retry.')
    })
    return () => {
      disposed = true
      mountedRef.current = false
      stop?.()
    }
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
  const allReady = inventoryLoad.phase === 'ready' && requiredGroups.length === 0
  const localReady = Boolean(inventory?.local_ai?.runtime_ready && inventory?.local_ai?.model_ready)
  const localUnavailable = isLocalAiUnavailable(inventory)
  const localRuntimeReady = Boolean(inventory?.local_ai?.runtime_ready)
  const localModelReady = Boolean(inventory?.local_ai?.model_ready)
  const localStateLabel = localUnavailable ? 'Unavailable' : localReady ? 'Ready' : inventory?.local_ai?.state === 'repair-required' ? 'Repair needed' : !localRuntimeReady ? 'Runtime needed' : 'Model needed'
  const setupPercent = progressPercent(progress)
  const setupEta = meaningfulEta(progress)
  const elapsed = progress?.elapsed_seconds ?? (startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : 0)
  const currentTotal = progress?.bytes_total ?? 0
  const currentDone = progress?.bytes_done ?? 0
  const storageStatus = diskState(inventory?.storage?.available_bytes, inventory?.storage?.required_bytes)
  const storageBlocked = storageStatus.state === 'CRITICAL'
  const inventoryVerifiedAt = inventoryVerifiedLabel(inventory?.last_verified_at)
  const canInstall = approved && !busy && inventoryLoad.phase === 'ready' && !allReady && !storageBlocked
  const canInstallLocal = !localUnavailable && localApproved && !busy && inventoryLoad.phase === 'ready' && !localReady && !storageBlocked
  const youtubeNeedsInstall = Boolean((youtubeLoad.phase === 'ready' || youtubeLoad.phase === 'error') && youtubeStatus?.actions.some((action) => action === 'Install' || action === 'Repair'))
  const canInstallYouTube = youtubeApproved && !busy && youtubeNeedsInstall && !storageBlocked

  async function testYouTube() {
    const requestId = ++youtubeRequestRef.current
    setYoutubeBusy(true)
    setYoutubeLoad({ phase: 'loading' })
    try {
      const next = api.setupToolYouTubeTest ? await api.setupToolYouTubeTest() : null
      if (!mountedRef.current || requestId !== youtubeRequestRef.current) return
      if (next !== null && !isNativeYouTubeReadiness(next)) throw new Error('YouTube readiness data is malformed.')
      const verifiedAt = new Date().toISOString()
      setYoutubeStatus(next)
      setYoutubeVerifiedAt(verifiedAt)
      writeCached(YOUTUBE_CACHE_KEY, { schema_version: YOUTUBE_CACHE_SCHEMA_VERSION, app_version: YOUTUBE_CACHE_APP_VERSION, value: next, verifiedAt })
      setYoutubeLoad({ phase: 'ready', value: next })
    } catch (error) {
      if (!mountedRef.current || requestId !== youtubeRequestRef.current) return
      setYoutubeLoad({ phase: 'error', value: youtubeStatus, message: youtubeStatus ? `Test failed — using last verified state. ${loadErrorMessage(error)}` : loadErrorMessage(error) })
    }
    finally { if (mountedRef.current && requestId === youtubeRequestRef.current) setYoutubeBusy(false) }
  }

  async function repairGpu() {
    setGpuBusy(true)
    setMessage('Repairing verified GPU speech components…')
    try {
      await api.repairGpu()
      setMessage('GPU speech acceleration is repaired. Retry the failed job.')
      await refreshGpu(true)
      await refresh()
    } catch (error) {
      setMessage(`GPU repair could not complete: ${loadErrorMessage(error)}`)
    } finally {
      setGpuBusy(false)
    }
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
      const operationId = await api.startSetup(args)
      if (typeof operationId !== 'string' || !operationId.trim()) throw new Error('Setup returned an invalid operation id.')
      setOperationId(operationId)
    } catch (error) {
      setBusy(false)
      setOperationId(null)
      setStartedAt(null)
      setProgress(null)
      setQueueSummary({ state: 'failed', completed: 0, failed: 1, cancelled: false })
      setMessage(friendlyErrorMessage(error, 'Setup could not start. Retry the setup.'))
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
      setMessage(friendlyErrorMessage(error, 'Could not cancel setup. Retry the action.'))
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

  function selectModel(modelId: string) {
    const requestId = ++modelSaveRequestRef.current
    setSelectedModelId(modelId)
    void Promise.resolve(api.saveLocalModel?.(modelId)).catch(() => {
      if (mountedRef.current && requestId === modelSaveRequestRef.current) setMessage('Local model choice could not be saved. Retry before installing.')
    })
    void refresh(modelId)
  }

  async function installYouTube() {
    if (!canInstallYouTube) return
    outcomesRef.current = []
    failedArgsRef.current = null
    failedLabelsRef.current = []
    queueRef.current = []
    setQueueSummary({ state: 'running', completed: 0, failed: 0, cancelled: false })
    await begin(GROUP_COMMANDS.youtube, 'Installing the approved YouTube support bundle.')
  }

  async function cleanupStorage(target: 'safe-cache' | 'obsolete-runtime-archives' | 'session' | 'failed-session') {
    const jobId = target === 'session' || target === 'failed-session' ? sessionId.trim() : undefined
    if ((target === 'session' || target === 'failed-session') && !jobId) {
      setMessage('Enter a session ID before cleanup.')
      return
    }
    setCleanupBusy(target)
    try {
      const preview = await api.storagePreview(target, jobId)
      if (!isStorageCleanupPreview(preview)) throw new Error('Cleanup preview data is malformed.')
      if (!preview.paths.length) {
        setMessage('Nothing matched that cleanup request.')
        return
      }
      const scope = target === 'session' ? `session ${jobId}` : target === 'failed-session' ? `failed session ${jobId}` : target === 'safe-cache' ? 'safe temporary cache' : 'obsolete runtime archives'
      if (!window.confirm(`Delete ${formatBytes(preview.bytes)} from ${scope}? User sessions and source media remain untouched.`)) return
      const result = await api.storageCleanup(target, jobId)
      if (!isStorageCleanupResult(result)) throw new Error('Cleanup result data is malformed.')
      setMessage(`Removed ${formatBytes(result.bytes)}. Verified components remain available.`)
      if (target === 'session' || target === 'failed-session') setSessionId('')
      await refresh()
    } catch (error) {
      setMessage(`Cleanup could not run: ${loadErrorMessage(error)}`)
    } finally {
      setCleanupBusy(null)
    }
  }

  const gpuStatus = gpuUiState(gpuLoad, gpuDiagnostics, gpuVerifiedAt ?? undefined)
  return (
    <div className="page-frame setup-page">
      <section className="card-surface storage-session-picker" aria-labelledby="storage-session-heading"><div className="section-heading"><div><p className="section-eyebrow">Safe cleanup</p><h2 id="storage-session-heading">Choose a saved session</h2><p className="section-caption">Select a session before deleting it. Source files stay untouched unless you confirm the selected cleanup.</p></div></div><label className="field-stack" htmlFor="storage-session-select"><span>Session</span><select id="storage-session-select" value={sessionId} onChange={(event) => setSessionId(event.target.value)}><option value="">Choose a saved session</option>{jobs.map((job) => <option value={job.id} key={job.id}>{job.title ?? 'Untitled video'} — {job.id}</option>)}</select></label>{!jobs.length && <p className="field-help">No saved sessions are available.</p>}</section>
      <header className="page-header setup-header">
        <div><p className="section-eyebrow">Setup & Storage</p><h1>{inventoryLoad.phase === 'loading' ? 'Loading setup information…' : inventoryLoad.phase === 'error' ? 'Setup information unavailable' : allReady ? 'Ready to create clips' : 'Core setup needed'}</h1><p className="page-lede">{inventoryLoad.phase === 'loading' ? 'Checking local components and available storage.' : inventoryLoad.phase === 'error' ? inventoryLoad.message : allReady ? 'Local files and configured providers can create clips. Optional local AI and best-effort YouTube import are shown separately below.' : `ClipGauge needs ${missingGroupTotal > 0 ? formatBytes(missingGroupTotal) : 'a few components'} of one-time downloads before core creation is ready.`}</p></div>
        <button type="button" className="button button-quiet" onClick={onBack}><X size={16} aria-hidden="true" /> Close</button>
      </header>
      <section className="setup-overview card-surface">
        <div className="setup-overview-main"><div className="setup-ready-icon"><Check size={20} aria-hidden="true" /></div><div><strong>{inventoryLoad.phase === 'loading' ? 'Checking local components.' : inventoryLoad.phase === 'error' ? 'Setup check needs attention.' : allReady ? 'Core components are ready.' : 'Core components need setup.'}</strong><p>Downloads are verified, resumable, and kept on this computer. Selected provider: ClipGauge Local — {localStateLabel}.</p>{inventoryVerifiedAt && <p className="setup-last-verified">Last verified: {inventoryVerifiedAt}</p>}</div></div>
        <div className="storage-stats"><div><span>Required now</span><strong>{inventoryLoad.phase === 'loading' ? 'Checking…' : inventoryLoad.phase === 'error' ? 'Unavailable' : allReady ? 'Ready' : missingGroupTotal > 0 ? formatBytes(missingGroupTotal) : 'Size calculated during setup'}</strong></div><div><span>Already installed</span><strong>{inventoryLoad.phase === 'loading' ? 'Checking…' : inventoryLoad.phase === 'error' ? 'Unavailable' : formatBytes(inventory?.storage?.installed_bytes ?? inventory?.storage?.required_bytes)}</strong></div><div><span>Available disk</span><strong>{inventoryLoad.phase === 'loading' ? 'Checking…' : inventoryLoad.phase === 'error' ? 'Unavailable' : formatBytes(inventory?.storage?.available_bytes)}</strong></div></div>
        {(storageStatus.state === 'LOW' || storageStatus.state === 'CRITICAL') && <div className={`inline-message storage-warning storage-${storageStatus.state.toLowerCase()}`} role="alert"><HardDrive size={16} aria-hidden="true" /><span><strong>{storageStatus.state === 'CRITICAL' ? 'Critical free space' : 'Low free space'}</strong> {storageStatus.message} Keep your sessions and source files, or clear only the safe cache and selected sessions below.{storageStatus.state === 'CRITICAL' && ' Required setup downloads are paused until more space is available.'}</span></div>}
        {!allReady && <div className="setup-install-row"><label className="consent-line" htmlFor="setup-approval"><input id="setup-approval" type="checkbox" checked={approved} onChange={(event) => setApproved(event.target.checked)} /><span>I approve these one-time downloads to this computer.</span></label><button type="button" className="button button-primary" onClick={installRequired} disabled={!canInstall}>{busy ? 'Installing…' : `Install required components · ${missingGroupTotal > 0 ? formatBytes(missingGroupTotal) : 'size calculated during setup'}`}</button></div>}
        {inventoryLoad.phase === 'loading' && <p className="inline-message" role="status">{setupPhaseLabel('loading')}</p>}
        {inventoryLoad.phase === 'error' && <p className="inline-message" role="alert">{inventoryLoad.message} <button type="button" className="button button-secondary" onClick={() => void refresh()}>Retry setup check</button></p>}
        {message && <p className="inline-message" role="status">{message}</p>}
      </section>
          <section className="card-surface gpu-diagnostics" aria-live="polite"><div className="section-heading"><div><p className="section-eyebrow">Speech acceleration</p><h2>GPU diagnostics</h2><p className="section-caption">Optional performance capability. CPU processing remains available.</p></div><span className={`status-pill tone-${gpuStatus.state === 'READY' ? 'ready' : gpuStatus.state === 'CPU_ONLY' || gpuStatus.state === 'UNAVAILABLE' ? 'neutral' : 'warning'}`}><span className="status-dot" aria-hidden="true" />{gpuStatus.state}</span></div><p className="inline-message" role="status">{gpuStatus.reason}</p>{gpuLoad.phase === 'error' && <button type="button" className="button button-secondary" onClick={() => void refreshGpu(true)} disabled={gpuBusy}>Retry GPU diagnostics</button>}{gpuDiagnostics && <details className="gpu-details"><summary>Show GPU details</summary><div className="technical-table"><div className="technical-row"><span><strong>GPU</strong><small>{gpuDiagnostics.hardware?.nvidia?.gpus?.[0]?.name ?? 'Not detected'}</small></span><span>{gpuDiagnostics.hardware?.nvidia?.gpus?.[0]?.driver ? `Driver ${gpuDiagnostics.hardware.nvidia.gpus[0].driver}` : 'Unavailable'}</span><span>{gpuDiagnostics.hardware?.nvidia?.verified ? 'Verified' : 'Unavailable'}</span></div><div className="technical-row"><span><strong>Transcription</strong><small>CTranslate2 CUDA</small></span><span>{gpuDiagnostics.hardware?.cuda_ctranslate2?.compute_types?.join(', ') ?? 'Unavailable'}</span><span>{gpuDiagnostics.hardware?.cuda_ctranslate2?.verified ? 'Ready' : 'CPU fallback'}</span></div><div className="technical-row"><span><strong>Word alignment</strong><small>PyTorch / WhisperX</small></span><span>{gpuDiagnostics.hardware?.pytorch_cuda?.compiled_cuda ? `CUDA ${gpuDiagnostics.hardware.pytorch_cuda.compiled_cuda}` : 'CPU build'}</span><span>{gpuDiagnostics.hardware?.pytorch_cuda?.verified ? 'Ready' : 'CPU alignment'}</span></div><div className="technical-row"><span><strong>Managed libraries</strong><small>Approved CUDA and cuDNN files</small></span><span>{gpuDiagnostics.cuda_runtime_ready && gpuDiagnostics.cudnn_runtime_ready ? 'Verified' : 'Repair needed'}</span><span>{gpuDiagnostics.environment?.state ?? 'Unknown'}</span></div></div></details>}<div className="detail-actions"><button type="button" className="button button-secondary" onClick={repairGpu} disabled={gpuBusy}>{gpuBusy ? 'Repairing GPU acceleration…' : 'Repair GPU acceleration'}</button><button type="button" className="button button-quiet" onClick={() => void refreshGpu(true)} disabled={gpuBusy}>Refresh diagnostics</button></div></section>
      <section className="card-surface storage-breakdown-section"><div className="section-heading"><div><p className="section-eyebrow">Storage breakdown</p><h2>What uses disk space</h2><p className="section-caption">Sessions and source media stay untouched. Cleanup requires an explicit action and confirmation.</p></div></div><div className="storage-breakdown-grid">{(inventory?.storage?.breakdown ?? []).map((row) => <div className="summary-row" key={row.category}><span>{row.display_name}</span><strong>{formatBytes(row.bytes)}</strong></div>)}</div><div className="detail-actions storage-cleanup-actions"><button type="button" className="button button-secondary" onClick={() => void cleanupStorage('safe-cache')} disabled={cleanupBusy !== null}>{cleanupBusy === 'safe-cache' ? 'Checking…' : 'Clear safe cache'}</button><button type="button" className="button button-secondary" onClick={() => void cleanupStorage('obsolete-runtime-archives')} disabled={cleanupBusy !== null}>{cleanupBusy === 'obsolete-runtime-archives' ? 'Checking…' : 'Remove obsolete runtime archives'}</button><button type="button" className="button button-secondary" onClick={() => void cleanupStorage('session')} disabled={cleanupBusy !== null || !sessionId.trim()}>{cleanupBusy === 'session' ? 'Checking…' : 'Delete session'}</button><button type="button" className="button button-secondary" onClick={() => void cleanupStorage('failed-session')} disabled={cleanupBusy !== null || !sessionId.trim()}>{cleanupBusy === 'failed-session' ? 'Checking…' : 'Delete failed session'}</button></div></section>
      <section className="component-section"><div className="section-heading"><div><p className="section-eyebrow">What ClipGauge uses</p><h2>One clear list</h2></div><span className="section-caption">{queueSummary.state === 'complete' ? 'Setup complete' : 'No hidden downloads'}</span></div><div className="component-grid">{groups.map((group) => <article className="component-card" key={group.id}><div className="component-card-heading"><span className="component-icon"><HardDrive size={17} aria-hidden="true" /></span><div><h3>{group.title}</h3><p>{group.description}</p></div><span className={`status-pill tone-${group.state.tone}`}><span className="status-dot" aria-hidden="true" />{group.state.label}</span></div><div className="component-card-footer"><span>{group.size ? formatBytes(group.size) : 'Size calculated during setup'}</span>{group.state.ready && <span className="reuse-note"><Check size={14} aria-hidden="true" /> {group.state.label.includes('System') ? 'System component reused' : 'Reused for future videos'}</span>}</div>{group.id === 'youtube' && <div className="component-card-actions"><span className="component-card-action-copy">{youtubeStatusCopy(youtubeStatus)}</span>{youtubeNeedsInstall && <label className="consent-line" htmlFor="youtube-approval"><input id="youtube-approval" type="checkbox" checked={youtubeApproved} onChange={(event) => setYoutubeApproved(event.target.checked)} /><span>I approve YouTube support installation.</span></label>}<div className="detail-actions">{youtubeNeedsInstall && <button type="button" className="button button-primary" onClick={installYouTube} disabled={!canInstallYouTube}>{statusHasRepair(youtubeStatus) ? 'Repair YouTube support' : 'Install YouTube support'}</button>}<button type="button" className="button button-secondary" onClick={testYouTube} disabled={youtubeBusy}>{youtubeBusy ? 'Testing…' : 'Test YouTube support'}</button></div></div>}</article>)}</div></section>
      <section className="card-surface local-model-section"><div className="section-heading"><div><p className="section-eyebrow">Optional local AI</p><h2>Choose one model</h2><p className="section-caption">Score clips completely on this computer. Only the model you choose counts toward this estimate.</p></div><span className="soft-badge">{optionalLabel}</span></div><div className="model-choice-grid">{models.length ? models.map((model, index) => { const id = String(model.asset_id); const selected = id === String(selectedModel?.asset_id); return <label className={`model-choice ${selected ? 'is-selected' : ''}`} key={id}><input type="radio" name="local-model" value={id} checked={selected} onChange={() => selectModel(id)} /><span><strong>{modelLabel(model, index)}{index === 1 && <em>Recommended</em>}</strong><small>{model.purpose ?? 'A local model for clip scoring.'}</small><b>{(model as { lifecycle_label?: string }).lifecycle_label ?? 'Download required'}</b><span className="model-download-note">{Number((model as { required_download_bytes?: number }).required_download_bytes ?? model.size_bytes) > 0 ? `${formatBytes(Number((model as { required_download_bytes?: number }).required_download_bytes ?? model.size_bytes))} additional download` : 'No additional download required'}</span></span><span className="choice-check"><Check size={15} aria-hidden="true" /></span></label> }) : <p className="empty-state">Local model choices will appear after the component catalog loads.</p>}</div></section>
      <section className="card-surface local-install-action"><div className="section-heading"><div><p className="section-eyebrow">Local scoring</p><h2>{localReady ? 'ClipGauge Local is ready' : 'Run scoring locally'}</h2><p className="section-caption">Runs completely on this computer. No API key. Install the engine and the one model you choose.</p></div><span className={`status-pill tone-${localReady ? 'ready' : 'warning'}`}><span className="status-dot" aria-hidden="true" />{localStateLabel}</span></div>{localReady ? <button type="button" className="button button-secondary" onClick={() => onUseLocal?.(selectedModelId ?? String(selectedModel?.asset_id ?? ''))}>Use ClipGauge Local</button> : <div className="setup-install-row"><label className="consent-line" htmlFor="local-approval"><input id="local-approval" type="checkbox" checked={localApproved} onChange={(event) => setLocalApproved(event.target.checked)} /><span>I approve this optional local-AI download.</span></label><button type="button" className="button button-primary" onClick={installLocal} disabled={!canInstallLocal}>{busy ? 'Installing…' : inventory?.local_ai?.action ?? 'Install ClipGauge Local'}</button></div>}</section>
      {progress && <section className="download-tray card-surface" aria-live="polite"><div className="download-tray-head"><div><p className="section-eyebrow">Download progress</p><h2>{progress.display_name ?? progress.operation ?? 'Preparing setup'}</h2></div><button type="button" className="button button-secondary" onClick={cancel} disabled={!operationId}><Square size={14} aria-hidden="true" /> Cancel</button></div><p className="download-message">{progress.message ?? 'Preparing verified components…'}</p><div className="progress-facts"><span>{currentTotal > 0 ? `${formatBytes(currentDone)} / ${formatBytes(currentTotal)}` : 'Calculating size…'}</span>{setupPercent != null && <span>{setupPercent}%</span>}{formatRate(progress.bytes_per_second) && <span>{formatRate(progress.bytes_per_second)}</span>}{setupEta && <span>{setupEta} remaining</span>}<span>{formatDuration(elapsed)} elapsed</span>{progress.one_time_download && <span>One-time download</span>}</div><div className="progress-track" role="progressbar" aria-label="Setup download progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={setupPercent ?? undefined}><div className={`progress-fill ${setupPercent == null ? 'is-indeterminate' : ''}`} style={setupPercent != null ? { width: `${setupPercent}%` } : undefined} /></div>{!busy && progress.event === 'terminal' && lastArgs && <button type="button" className="button button-secondary" onClick={retry}><RotateCcw size={15} aria-hidden="true" /> Retry component</button>}</section>}
      <section className="advanced-panel"><button type="button" className="advanced-toggle" onClick={() => setShowDetails((value) => !value)} aria-expanded={showDetails}><ChevronDown size={16} className={showDetails ? 'is-open' : ''} aria-hidden="true" /> Advanced component details</button>{showDetails && <div className="technical-table"><div className="technical-table-head"><span>Component</span><span>Download</span><span>State</span></div>{(inventory?.managed_assets ?? []).map((asset) => <div className="technical-row" key={asset.asset_id}><span><strong>{asset.display_name}</strong><small>{asset.asset_id} · {asset.license}</small></span><code>{asset.size_bytes > 0 ? formatBytes(asset.size_bytes) : 'unknown'}</code><span>{assetLifecycleLabel(asset)}</span></div>)}</div>}</section>
      <p className="page-footnote"><ShieldCheck size={15} aria-hidden="true" /> Components are downloaded only after your approval. Existing verified files are reused; credentials never belong in this folder.</p>
    </div>
  )
}

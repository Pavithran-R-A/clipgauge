import type { JobSummary, LocalSetupInventory, PreflightResult, PrivacySummary, ProviderModel, ProviderModelsResult, ProviderTestResult, SetupState, StorageCleanupPreview, StorageCleanupResult, YouTubeReadiness } from './types'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isRecordArray(value: unknown): value is Array<Record<string, unknown>> {
  return Array.isArray(value) && value.every(isRecord)
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isStorageBreakdown(value: unknown): boolean {
  return value === undefined || (Array.isArray(value) && value.every((row) => isRecord(row)
    && typeof row.category === 'string'
    && typeof row.display_name === 'string'
    && isFiniteNumber(row.bytes)
    && (row.deletable === undefined || typeof row.deletable === 'boolean')
    && (row.requires_confirmation === undefined || typeof row.requires_confirmation === 'boolean')))
}

function isManagedAssetArray(value: unknown): boolean {
  return value === undefined || (isRecordArray(value) && value.every((asset) => typeof asset.asset_id === 'string' && asset.asset_id.trim().length > 0))
}

function isProviderModel(value: unknown): value is ProviderModel | string {
  if (typeof value === 'string') return value.trim().length > 0
  return isRecord(value)
    && typeof value.id === 'string'
    && value.id.trim().length > 0
    && (value.compatibility === 'FULL' || value.compatibility === 'TEXT-ONLY' || value.compatibility === 'NO STRUCTURED OUTPUT' || value.compatibility === 'UNSUPPORTED')
}

export function isSetupState(value: unknown): value is SetupState {
  return isRecord(value)
    && typeof value.onboarded === 'boolean'
    && typeof value.has_gemini_key === 'boolean'
    && (value.provider_keys === undefined || (isRecord(value.provider_keys) && Object.values(value.provider_keys).every((item) => typeof item === 'boolean')))
}

export function isOnboardingInventory(value: unknown): value is Pick<LocalSetupInventory, 'runtime' | 'models'> {
  return isRecord(value) && isRecord(value.runtime) && isRecordArray(value.models)
}

export function isProviderInventory(value: unknown): value is Pick<LocalSetupInventory, 'models' | 'local_ai'> {
  return isRecord(value) && isRecordArray(value.models) && (value.local_ai === undefined || isRecord(value.local_ai))
}

export function isLocalSetupInventory(value: unknown): value is LocalSetupInventory {
  return isRecord(value)
    && isRecord(value.runtime)
    && isRecordArray(value.models)
    && typeof value.state === 'string'
    && (value.last_verified_at === undefined || value.last_verified_at === null || isFiniteNumber(value.last_verified_at))
    && (value.platform === undefined || typeof value.platform === 'string')
    && (value.runtime_manifest_digest === undefined || typeof value.runtime_manifest_digest === 'string')
    && isRecordArray(value.core_assets)
    && isRecord(value.storage)
    && isStorageBreakdown(value.storage.breakdown)
    && isRecordArray(value.catalog)
    && isManagedAssetArray(value.managed_assets)
}

export function isYouTubeReadiness(value: unknown): value is YouTubeReadiness {
  return isRecord(value)
    && typeof value.state === 'string'
    && typeof value.ready === 'boolean'
    && typeof value.reason === 'string'
    && Array.isArray(value.actions)
    && value.actions.every((action) => typeof action === 'string')
    && Array.isArray(value.checks)
    && value.checks.every((check) => isRecord(check) && typeof check.name === 'string' && typeof check.ready === 'boolean' && typeof check.message === 'string')
}

export function isPreflightResult(value: unknown): value is PreflightResult {
  return isRecord(value)
    && (value.state === 'ready' || value.state === 'warning' || value.state === 'blocked')
    && typeof value.selected_llm === 'string'
    && Array.isArray(value.checks)
    && value.checks.every((check) => isRecord(check) && typeof check.name === 'string' && (check.state === 'ready' || check.state === 'warning' || check.state === 'blocked') && typeof check.message === 'string')
}

export function isProviderTestResult(value: unknown): value is ProviderTestResult {
  return isRecord(value)
    && (value.state === 'PASS' || value.state === 'WARNING' || value.state === 'FAIL')
    && (value.provider === undefined || typeof value.provider === 'string')
    && (value.model === undefined || typeof value.model === 'string')
    && (value.code === undefined || typeof value.code === 'string')
    && (value.message === undefined || typeof value.message === 'string')
    && (value.models === undefined || (Array.isArray(value.models) && value.models.every(isProviderModel)))
}

export function isProviderModelsResult(value: unknown): value is ProviderModelsResult {
  return isRecord(value)
    && (value.state === 'PASS' || value.state === 'WARNING' || value.state === 'FAIL')
    && (value.provider === undefined || typeof value.provider === 'string')
    && (value.requested_model === undefined || typeof value.requested_model === 'string')
    && (value.code === undefined || typeof value.code === 'string')
    && (value.message === undefined || typeof value.message === 'string')
    && (value.models === undefined || Array.isArray(value.models))
}

export function isJobSummaryList(value: unknown): value is JobSummary[] {
  return Array.isArray(value) && value.every((item) => isRecord(item)
    && typeof item.id === 'string'
    && (typeof item.title === 'string' || item.title === null)
    && typeof item.ingested === 'boolean'
    && typeof item.rendered === 'boolean'
    && (item.lifecycle_state === undefined || typeof item.lifecycle_state === 'string')
    && (item.last_stage === undefined || typeof item.last_stage === 'string' || item.last_stage === null)
    && (item.resume_safe === undefined || typeof item.resume_safe === 'boolean')
    && (item.outcome === undefined || item.outcome === null || item.outcome === 'SUCCESS_WITH_CLIPS' || item.outcome === 'SUCCESS_NO_RECOMMENDATIONS' || item.outcome === 'FAILED'))
}

export function isPrivacySummary(value: unknown): value is PrivacySummary {
  if (!isRecord(value) || typeof value.local_first !== 'boolean' || typeof value.telemetry !== 'string' || typeof value.instagram !== 'string' || typeof value.source !== 'string' || !isRecord(value.llm)) return false
  return typeof value.llm.mode === 'string'
    && Array.isArray(value.llm.device) && value.llm.device.every((item) => typeof item === 'string')
    && Array.isArray(value.llm.network) && value.llm.network.every((item) => typeof item === 'string')
    && typeof value.llm.provider === 'string'
    && (value.llm.model === undefined || value.llm.model === null || typeof value.llm.model === 'string')
    && (value.llm.endpoint === undefined || value.llm.endpoint === null || typeof value.llm.endpoint === 'string')
}

export function isStorageCleanupPreview(value: unknown): value is StorageCleanupPreview {
  return isRecord(value)
    && typeof value.target === 'string'
    && isFiniteNumber(value.bytes)
    && value.bytes >= 0
    && Array.isArray(value.paths)
    && value.paths.every((path) => typeof path === 'string')
    && typeof value.requires_confirmation === 'boolean'
    && (value.job_id === undefined || value.job_id === null || typeof value.job_id === 'string')
}

export function isStorageCleanupResult(value: unknown): value is StorageCleanupResult {
  if (!isStorageCleanupPreview(value)) return false
  const result = value as StorageCleanupResult
  return result.removed === undefined || (Array.isArray(result.removed) && result.removed.every((path) => typeof path === 'string'))
}

export function isPlaybackUrl(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

export function isInstagramStatus(value: unknown): value is { connected: boolean; username?: string } {
  return isRecord(value)
    && typeof value.connected === 'boolean'
    && (value.username === undefined || typeof value.username === 'string')
}

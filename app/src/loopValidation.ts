import type { LoopOverview, SyncSummary } from './types'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isNullableNumber(value: unknown): boolean {
  return value === null || isNumber(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isNumberRecord(value: unknown): boolean {
  return isRecord(value) && Object.values(value).every(isNumber)
}

function isMetrics(value: unknown): boolean {
  if (value === null) return true
  if (!isRecord(value)) return false
  return Object.values(value).every((item) => item === null || isNumber(item))
}

function isAdjustment(value: unknown): boolean {
  return isRecord(value) && typeof value.rule === 'string' && isNumber(value.factor) && typeof value.reason === 'string'
}

function isLinked(value: unknown): boolean {
  if (!isRecord(value)) return false
  return typeof value.job_id === 'string'
    && Number.isInteger(value.clip_index)
    && (value.media_id === null || typeof value.media_id === 'string')
    && typeof value.link_source === 'string'
    && isNumber(value.linked_at)
    && isNumber(value.score)
    && isNumber(value.reels_score)
    && isNumber(value.config_version)
    && (value.subscores === null || isNumberRecord(value.subscores))
    && (value.adjustments === null || (Array.isArray(value.adjustments) && value.adjustments.every(isAdjustment)))
    && (value.signals_fired === null || isStringArray(value.signals_fired))
    && (value.signals_missing === null || isStringArray(value.signals_missing))
    && typeof value.summary === 'string'
    && isNullableNumber(value.clip_duration)
    && (value.clip_thumb === null || typeof value.clip_thumb === 'string')
    && (value.ig_thumb === null || typeof value.ig_thumb === 'string')
    && (value.permalink === null || typeof value.permalink === 'string')
    && (value.caption === null || typeof value.caption === 'string')
    && isNullableNumber(value.posted_at)
    && typeof value.media_deleted === 'boolean'
    && isNullableNumber(value.media_age_hours)
    && typeof value.settling === 'boolean'
    && isMetrics(value.metrics)
    && Array.isArray(value.snapshots)
    && value.snapshots.every((snapshot) => isRecord(snapshot) && isNullableNumber(snapshot.age_hours) && isNullableNumber(snapshot.views))
    && Number.isInteger(value.snapshot_count)
}

function isSuggestion(value: unknown): boolean {
  return isRecord(value)
    && typeof value.media_id === 'string'
    && typeof value.job_id === 'string'
    && Number.isInteger(value.clip_index)
    && isNumber(value.confidence)
    && typeof value.clip_summary === 'string'
    && isNullableNumber(value.clip_duration)
    && (value.clip_thumb === null || typeof value.clip_thumb === 'string')
    && isNullableNumber(value.clip_reels_score)
}

function isUnlinked(value: unknown): boolean {
  return isRecord(value)
    && typeof value.media_id === 'string'
    && (value.thumb === null || typeof value.thumb === 'string')
    && (value.permalink === null || typeof value.permalink === 'string')
    && typeof value.caption === 'string'
    && isNullableNumber(value.posted_at)
    && isNullableNumber(value.duration_s)
    && typeof value.copyright_flagged === 'boolean'
    && (value.suggestion === null || isSuggestion(value.suggestion))
}

function isClip(value: unknown): boolean {
  return isRecord(value)
    && typeof value.job_id === 'string'
    && Number.isInteger(value.clip_index)
    && typeof value.summary === 'string'
    && isNullableNumber(value.duration)
    && isNullableNumber(value.reels_score)
    && (value.thumb === null || typeof value.thumb === 'string')
    && typeof value.linked === 'boolean'
}

function isCalibrationVersion(value: unknown): boolean {
  return isRecord(value)
    && isNumber(value.version)
    && isNumberRecord(value.constants)
    && (value.fitted_from_n === undefined || isNullableNumber(value.fitted_from_n))
    && (value.spearman_rho === undefined || isNullableNumber(value.spearman_rho))
    && (value.pairwise_acc === undefined || isNullableNumber(value.pairwise_acc))
    && (value.note === undefined || value.note === null || typeof value.note === 'string')
    && (value.created_at === undefined || isNullableNumber(value.created_at))
}

function isReport(value: unknown): boolean {
  return isRecord(value)
    && Number.isInteger(value.pairs)
    && typeof value.ready === 'boolean'
    && (value.note === undefined || typeof value.note === 'string')
    && (value.spearman_rho === undefined || isNullableNumber(value.spearman_rho))
    && (value.pairwise_accuracy === undefined || isNullableNumber(value.pairwise_accuracy))
    && (value.kendall_tau === undefined || isNullableNumber(value.kendall_tau))
}

export function validateLoopOverview(value: unknown): value is LoopOverview {
  if (!isRecord(value)) return false
  const calibration = value.calibration
  return typeof value.connected === 'boolean'
    && (value.username === null || typeof value.username === 'string')
    && isNullableNumber(value.last_synced_at)
    && Array.isArray(value.linked)
    && value.linked.every(isLinked)
    && Array.isArray(value.unlinked)
    && value.unlinked.every(isUnlinked)
    && Array.isArray(value.clip_library)
    && value.clip_library.every(isClip)
    && isReport(value.report)
    && isRecord(calibration)
    && isCalibrationVersion(calibration.active)
    && Array.isArray(calibration.history)
    && calibration.history.every(isCalibrationVersion)
    && Number.isFinite(calibration.qualifying_outcomes)
    && Number.isFinite(calibration.recomputable_outcomes)
    && Number.isFinite(calibration.threshold)
}

export function validateSyncSummary(value: unknown): value is SyncSummary {
  if (!isRecord(value) || typeof value.ok !== 'boolean') return false
  if (value.error !== undefined && typeof value.error !== 'string') return false
  if (value.username !== undefined && typeof value.username !== 'string') return false
  for (const key of ['new_media', 'thumbs_cached', 'snapshots_pulled', 'tombstoned'] as const) {
    if (value[key] !== undefined && !isNumber(value[key])) return false
  }
  if (value.fit !== undefined) {
    if (!isRecord(value.fit) || typeof value.fit.applied !== 'boolean') return false
    if (value.fit.version !== undefined && !isNumber(value.fit.version)) return false
    if (value.fit.reason !== undefined && typeof value.fit.reason !== 'string') return false
  }
  return true
}

export function validateInstagramActionResult(value: unknown): value is { ok: boolean } {
  return isRecord(value) && typeof value.ok === 'boolean'
}

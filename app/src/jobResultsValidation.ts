import type { JobResults } from './types'

const ARTIFACT_STATES = new Set(['available', 'missing', 'invalid', 'outside_managed_root', 'unreadable'])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isNumberRecord(value: unknown): value is Record<string, number> {
  return isRecord(value) && Object.values(value).every(isFiniteNumber)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isAdjustment(value: unknown): boolean {
  return isRecord(value)
    && typeof value.rule === 'string'
    && isFiniteNumber(value.factor)
    && typeof value.reason === 'string'
}

function isClip(value: unknown): boolean {
  if (!isRecord(value)) return false
  const heatmap = value.heatmap_pct
  return isFiniteNumber(value.start)
    && isFiniteNumber(value.end)
    && isFiniteNumber(value.score)
    && typeof value.best_platform === 'string'
    && isNumberRecord(value.platform_scores)
    && isNumberRecord(value.subscores)
    && Array.isArray(value.adjustments)
    && value.adjustments.every(isAdjustment)
    && isStringArray(value.signals_fired)
    && isStringArray(value.signals_missing)
    && typeof value.confidence === 'string'
    && typeof value.summary === 'string'
    && isFiniteNumber(value.arousal_pct)
    && (heatmap === null || isFiniteNumber(heatmap))
    && isFiniteNumber(value.curve_score)
}

function isBorderlineCandidate(value: unknown): boolean {
  return isRecord(value)
    && isFiniteNumber(value.start)
    && isFiniteNumber(value.end)
    && isFiniteNumber(value.recommendation_score)
    && (value.reasons === undefined || isStringArray(value.reasons))
}

function isRenderOutput(value: unknown): boolean {
  if (!isRecord(value)) return false
  const path = value.path
  const artifactStatus = value.artifact_status
  return isFiniteNumber(value.clip)
    && (typeof path === 'string' || path === null)
    && isFiniteNumber(value.score)
    && typeof value.best_platform === 'string'
    && isFiniteNumber(value.duration)
    && isFiniteNumber(value.words)
    && isFiniteNumber(value.event_tags)
    && (artifactStatus === undefined || (typeof artifactStatus === 'string' && ARTIFACT_STATES.has(artifactStatus)))
}

export function validateJobResults(value: unknown): value is JobResults {
  if (!isRecord(value) || typeof value.job_id !== 'string' || !value.job_id) return false
  if (value.score !== undefined && value.score !== null) {
    if (!isRecord(value.score) || !Array.isArray(value.score.clips) || !value.score.clips.every(isClip)) return false
    if (value.score.borderline_candidates !== undefined
      && (!Array.isArray(value.score.borderline_candidates) || !value.score.borderline_candidates.every(isBorderlineCandidate))) return false
  }
  if (value.render !== undefined && value.render !== null) {
    if (!isRecord(value.render) || !Array.isArray(value.render.outputs) || !value.render.outputs.every(isRenderOutput)) return false
  }
  return true
}

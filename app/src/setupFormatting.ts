import type { ManagedAssetRow, SetupProgressEvent } from './types'

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB']
const MIN_MEANINGFUL_ETA_BYTES = 128 * 1024
const MIN_MEANINGFUL_ETA_SECONDS = 2

export function formatBytes(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value) || value < 0) return '—'
  let amount = value
  let unit = 0
  while (amount >= 1024 && unit < BYTE_UNITS.length - 1) {
    amount /= 1024
    unit += 1
  }
  const decimals = unit === 0 ? 0 : amount >= 100 ? 0 : amount >= 10 ? 1 : 2
  return `${amount.toFixed(decimals)} ${BYTE_UNITS[unit]}`
}

export function formatRate(value: number | null | undefined): string | null {
  if (value == null || !Number.isFinite(value) || value <= 0) return null
  return `${formatBytes(value)}/s`
}

export function formatDuration(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value) || value < 0) return '—'
  const total = Math.round(value)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  if (hours > 0) return `${hours} hr ${minutes} min`
  if (minutes > 0) return `${minutes} min ${seconds} sec`
  return `${seconds} sec`
}

export function meaningfulEta(progress: SetupProgressEvent | null | undefined): string | null {
  if (!progress || progress.bytes_total == null || progress.bytes_total <= 0) return null
  const done = progress.bytes_done ?? 0
  const elapsed = progress.elapsed_seconds ?? 0
  const rate = progress.bytes_per_second ?? 0
  if (done < MIN_MEANINGFUL_ETA_BYTES || elapsed < MIN_MEANINGFUL_ETA_SECONDS || rate <= 0) return null
  const remaining = Math.max(0, progress.bytes_total - done)
  return formatDuration(remaining / rate)
}

export function progressPercent(progress: SetupProgressEvent | null | undefined): number | null {
  if (!progress || progress.bytes_total == null || progress.bytes_total <= 0 || progress.fraction == null || progress.fraction < 0) return null
  return Math.max(0, Math.min(100, Math.round(progress.fraction * 100)))
}

export function assetLifecycleLabel(asset: Pick<ManagedAssetRow, 'installed' | 'cached' | 'one_time' | 'status' | 'reused_from_migration'>): string {
  if (asset.installed && asset.reused_from_migration) return 'REUSED FROM EXISTING INSTALLATION'
  if (asset.installed || asset.cached || ['ready', 'installed', 'reused'].includes(String(asset.status))) return 'INSTALLED · REUSED FOR FUTURE JOBS'
  return asset.one_time ? 'ONE-TIME DOWNLOAD' : 'AVAILABLE'
}

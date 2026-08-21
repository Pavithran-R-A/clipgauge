import { describe, expect, it } from 'vitest'
import { assetLifecycleLabel, formatBytes, formatDuration, formatRate, meaningfulEta, progressPercent } from './setupFormatting'

describe('setup formatting', () => {
  it('uses automatic byte units and rates', () => {
    expect(formatBytes(17.4 * 1024 ** 2)).toBe('17.4 MB')
    expect(formatBytes(2.5 * 1024 ** 3)).toBe('2.50 GB')
    expect(formatRate(5.8 * 1024 ** 2)).toBe('5.80 MB/s')
  })

  it('keeps early ETA hidden until enough measured data exists', () => {
    expect(meaningfulEta({ bytes_done: 1024, bytes_total: 1000000, bytes_per_second: 100000, elapsed_seconds: 1 })).toBeNull()
    expect(meaningfulEta({ bytes_done: 200000, bytes_total: 1000000, bytes_per_second: 200000, elapsed_seconds: 3 })).toBe('4 sec')
  })

  it('distinguishes determinate and indeterminate progress', () => {
    expect(progressPercent({ bytes_done: 44, bytes_total: 100, fraction: 0.44 })).toBe(44)
    expect(progressPercent({ bytes_done: 0, bytes_total: null, fraction: null })).toBeNull()
    expect(formatDuration(75)).toBe('1 min 15 sec')
  })

  it('makes one-time and reuse state explicit', () => {
    expect(assetLifecycleLabel({ installed: false, cached: false, one_time: true })).toBe('ONE-TIME DOWNLOAD')
    expect(assetLifecycleLabel({ installed: true, cached: true, one_time: true })).toBe('INSTALLED · REUSED FOR FUTURE JOBS')
    expect(assetLifecycleLabel({ installed: true, cached: true, one_time: true, reused_from_migration: true })).toBe('REUSED FROM EXISTING INSTALLATION')
  })
})

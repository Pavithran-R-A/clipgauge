import { describe, expect, it } from 'vitest'
import { presentPipelineError } from './errorPresentation'

describe('presentPipelineError', () => {
  it('keeps identifiers out of creator-facing copy', () => {
    const result = presentPipelineError('YTDLP_RATE_LIMITED', 'diag-secret-123')
    expect(result.title).toBe('YouTube is temporarily busy')
    expect(result.message).not.toContain('diag-secret-123')
    expect(result.primaryAction).toBe('Retry')
  })

  it('gives stable fallback copy for unknown failures', () => {
    expect(presentPipelineError('UNKNOWN_CODE').message).toBe('ClipGauge could not finish this video.')
  })
})

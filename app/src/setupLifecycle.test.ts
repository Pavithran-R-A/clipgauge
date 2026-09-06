import { describe, expect, it } from 'vitest'
import { loadErrorMessage, setupPhaseLabel } from './setupLifecycle'

describe('setup lifecycle labels', () => {
  it('names loading, ready, and failed inventory states', () => {
    expect(setupPhaseLabel('loading')).toBe('Loading setup information…')
    expect(setupPhaseLabel('ready')).toBe('Setup information ready.')
    expect(setupPhaseLabel('error')).toBe('Setup information unavailable.')
  })

  it('turns structured bridge errors into retryable copy', () => {
    expect(loadErrorMessage({ code: 'PIPELINE_NOT_INITIALIZED', message: 'Environment missing.' }))
      .toBe('ClipGauge is preparing its local runtime. Retry shortly.')
    expect(loadErrorMessage(new Error('bridge failed'))).toBe('Setup information is temporarily unavailable.')
  })
})

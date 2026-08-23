import { beforeEach, describe, expect, it, vi } from 'vitest'
import { traceMedia } from './mediaDiagnostics'

const harness = vi.hoisted(() => ({
  recordMediaEvent: vi.fn()
}))

vi.mock('./api', () => ({
  api: { recordMediaEvent: harness.recordMediaEvent }
}))

function video(overrides: Record<string, unknown> = {}): HTMLVideoElement {
  const element = document.createElement('video')
  const values: Record<string, unknown> = {
    error: null,
    networkState: 1,
    readyState: 4,
    duration: 12.5,
    videoWidth: 1280,
    videoHeight: 720,
    currentSrc: 'http://127.0.0.1:49152/media/secret-token?x=1#fragment',
    ...overrides
  }
  for (const [key, value] of Object.entries(values)) {
    Object.defineProperty(element, key, { configurable: true, value })
  }
  return element
}

describe('traceMedia', () => {
  beforeEach(() => {
    harness.recordMediaEvent.mockReset()
    harness.recordMediaEvent.mockResolvedValue(undefined)
  })

  it('records only the bounded normal loaded-media payload', () => {
    traceMedia('review', 'loadedmetadata', video())
    expect(harness.recordMediaEvent).toHaveBeenCalledWith({
      label: 'review',
      event: 'loadedmetadata',
      error_code: null,
      error_message: null,
      network_state: 1,
      ready_state: 4,
      duration: 12.5,
      video_width: 1280,
      video_height: 720,
      current_src: 'http://127.0.0.1:49152/media/<capability>'
    })
  })

  it('records media error code and bounded message', () => {
    traceMedia('editor', 'error', video({ error: { code: 3, message: 'decode failed' } }))
    expect(harness.recordMediaEvent).toHaveBeenCalledWith(expect.objectContaining({
      error_code: 3,
      error_message: 'decode failed'
    }))
  })

  it('normalizes NaN and Infinity instead of sending invalid JSON numbers', () => {
    traceMedia('review', 'progress', video({ duration: Number.NaN, videoWidth: Number.POSITIVE_INFINITY }))
    expect(harness.recordMediaEvent).toHaveBeenCalledWith(expect.objectContaining({
      duration: null,
      video_width: null,
      video_height: 720
    }))
  })

  it('redacts the capability token and removes query and fragment data', () => {
    traceMedia('review', 'canplaythrough', video())
    const payload = harness.recordMediaEvent.mock.calls[0][0]
    expect(payload.current_src).toBe('http://127.0.0.1:49152/media/<capability>')
    expect(JSON.stringify(payload)).not.toContain('secret-token')
    expect(JSON.stringify(payload)).not.toContain('fragment')
  })

  it('fails closed for malformed, credentialed, non-loopback, and non-media URLs', () => {
    for (const currentSrc of [
      'not a URL with a private path',
      'https://user:password@127.0.0.1:49152/media/token',
      'https://example.test/private/video.mp4',
      'file:///home/user/private.mp4'
    ]) {
      traceMedia('review', 'loadstart', video({ currentSrc }))
    }
    const sources = harness.recordMediaEvent.mock.calls.map(([payload]) => payload.current_src)
    expect(sources).toEqual(['<invalid-source>', '<invalid-source>', '<non-loopback-media>', '<non-loopback-media>'])
  })

  it('swallows recordMediaEvent rejection and never throws into playback', async () => {
    harness.recordMediaEvent.mockRejectedValueOnce(new Error('bridge unavailable'))
    expect(() => traceMedia('review', 'waiting', video())).not.toThrow()
    await Promise.resolve()
  })
})

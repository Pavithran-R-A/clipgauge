import { api } from './api'

type SafeNumber = number | null

type MediaTracePayload = {
  label: string
  event: string
  error_code: number | null
  error_message: string | null
  network_state: SafeNumber
  ready_state: SafeNumber
  duration: SafeNumber
  video_width: SafeNumber
  video_height: SafeNumber
  current_src: string
}

function finiteNumber(value: number): SafeNumber {
  return Number.isFinite(value) ? value : null
}

function boundedText(value: string, maximum: number): string {
  return value.slice(0, maximum)
}

function safeCurrentSource(source: string): string {
  if (!source) return '<empty-source>'
  try {
    const url = new URL(source)
    if (url.username || url.password) return '<invalid-source>'
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return '<non-loopback-media>'
    if (!['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)) return '<non-loopback-media>'
    if (!url.pathname.startsWith('/media/')) return '<invalid-source>'
    return `${url.origin}/media/<capability>`
  } catch {
    return '<invalid-source>'
  }
}

export function traceMedia(label: string, event: string, media: HTMLMediaElement): void {
  const payload: MediaTracePayload = {
    label: boundedText(label, 32),
    event: boundedText(event, 64),
    error_code: media.error?.code ?? null,
    error_message: media.error?.message ? boundedText(media.error.message, 240) : null,
    network_state: finiteNumber(media.networkState),
    ready_state: finiteNumber(media.readyState),
    duration: finiteNumber(media.duration),
    video_width: finiteNumber(media instanceof HTMLVideoElement ? media.videoWidth : 0),
    video_height: finiteNumber(media instanceof HTMLVideoElement ? media.videoHeight : 0),
    current_src: safeCurrentSource(media.currentSrc)
  }

  try {
    Promise.resolve(api.recordMediaEvent(payload)).catch(() => undefined)
  } catch {
    // Diagnostics are strictly best-effort and must never affect playback or React.
  }
}

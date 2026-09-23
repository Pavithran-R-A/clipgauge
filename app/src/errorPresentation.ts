export interface PipelineErrorPresentation {
  title: string
  message: string
  primaryAction: 'Retry' | 'Choose another video' | 'Open Setup'
  secondaryActions: string[]
}

const COPY: Record<string, PipelineErrorPresentation> = {
  YTDLP_ATTESTATION_REQUIRED: { title: 'YouTube rejected this request', message: 'Retry later, or choose a local video.', primaryAction: 'Retry', secondaryActions: ['Choose local video', 'Open YouTube support'] },
  YTDLP_LOGIN_REQUIRED: { title: 'This video needs YouTube sign-in', message: 'Choose an approved browser session, or import the video file.', primaryAction: 'Choose another video', secondaryActions: ['Open YouTube support'] },
  YTDLP_PRIVATE: { title: 'This video is private', message: 'Choose a public video or import a file you can access.', primaryAction: 'Choose another video', secondaryActions: [] },
  YTDLP_AGE_RESTRICTED: { title: 'This video is age-restricted', message: 'Use an approved signed-in session, or import the video file.', primaryAction: 'Choose another video', secondaryActions: ['Open YouTube support'] },
  YTDLP_REGION_RESTRICTED: { title: 'This video is region-restricted', message: 'Choose another video or import a permitted local file.', primaryAction: 'Choose another video', secondaryActions: [] },
  YTDLP_UNAVAILABLE: { title: 'This video is unavailable', message: 'Check the link, then choose another video if needed.', primaryAction: 'Choose another video', secondaryActions: [] },
  YTDLP_DNS_FAILED: { title: 'ClipGauge could not reach YouTube', message: 'Check your connection, then retry.', primaryAction: 'Retry', secondaryActions: ['Choose local video'] },
  YTDLP_NETWORK_FAILED: { title: 'The YouTube connection stopped', message: 'Check your connection, then retry.', primaryAction: 'Retry', secondaryActions: ['Choose local video'] },
  YTDLP_TRANSFER_FAILED: { title: 'YouTube could not finish transfer', message: 'Retry once, or import the video file.', primaryAction: 'Retry', secondaryActions: ['Choose local video'] },
  YTDLP_PROVIDER_FAILED: { title: 'YouTube support needs attention', message: 'Open Setup & Storage, test YouTube support, then retry.', primaryAction: 'Open Setup', secondaryActions: ['Choose local video'] },
  YTDLP_FORMAT_UNAVAILABLE: { title: 'No compatible video format found', message: 'Choose another video or import a local file.', primaryAction: 'Choose another video', secondaryActions: [] },
  YTDLP_RATE_LIMITED: { title: 'YouTube is temporarily busy', message: 'Wait briefly, then retry once.', primaryAction: 'Retry', secondaryActions: ['Choose local video'] },
  YTDLP_UNKNOWN_FAILURE: { title: 'YouTube rejected this request', message: 'Retry once, or import the video file directly.', primaryAction: 'Retry', secondaryActions: ['Choose local video', 'Open YouTube support'] },
  ASR_RESOURCE_HEADROOM_LOW: { title: 'Speech recognition needs more memory', message: 'Close other apps, then retry in Low-memory mode.', primaryAction: 'Retry', secondaryActions: ['Open Setup'] },
  DISK_SPACE_LOW: { title: 'More free disk space is needed', message: 'Open Setup & Storage, then retry.', primaryAction: 'Open Setup', secondaryActions: [] },
}

export function presentPipelineError(code?: string | null, _diagnosticId?: string | null, fallbackMessage?: string): PipelineErrorPresentation {
  const known = code ? COPY[code] : undefined
  if (known) return known
  return {
    title: 'ClipGauge could not finish this video.',
    message: fallbackMessage || 'ClipGauge could not finish this video.',
    primaryAction: 'Retry',
    secondaryActions: ['Choose local video']
  }
}

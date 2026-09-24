import type { JobSummary } from './types'

export interface SessionPresentation {
  title: string
  state: string
  detail: string
  action: 'Open clips' | 'Open analysis' | 'Resume'
  ready: boolean
}

function terminalDetail(job: JobSummary, fallback: string): string {
  const summary = job.terminal_summary?.trim()
  if (!summary) return fallback
  if (/download|transfer|network|yt.?dlp/i.test(`${job.terminal_code ?? ''} ${summary}`)) {
    return `Download failed. ${summary}`
  }
  return summary
}

export function sessionPresentation(job: JobSummary): SessionPresentation {
  const title = job.title?.trim() || job.source_label?.trim() || 'Saved video'
  const noRecommendations = job.outcome === 'SUCCESS_NO_RECOMMENDATIONS'
  if (job.rendered) {
    return { title, state: 'Ready to review', detail: 'Clips are ready.', action: 'Open clips', ready: true }
  }
  if (noRecommendations) {
    return { title, state: 'Analysis complete · no recommended clips', detail: 'The quality bar was not met.', action: 'Open analysis', ready: true }
  }
  if (job.lifecycle_state === 'FAILED') {
    return {
      title,
      state: 'Needs attention',
      detail: terminalDetail(job, 'This session needs attention before it can continue.'),
      action: 'Resume',
      ready: false,
    }
  }
  if (job.lifecycle_state === 'CANCELLED') {
    return {
      title,
      state: 'Cancelled',
      detail: terminalDetail(job, 'This session was cancelled. You can continue from its last safe checkpoint.'),
      action: 'Resume',
      ready: false,
    }
  }
  if (job.lifecycle_state === 'RESUMABLE' || job.lifecycle_state === 'INTERRUPTED' || job.resume_safe) {
    return {
      title,
      state: 'Continue',
      detail: 'Continue from the last safe checkpoint.',
      action: 'Resume',
      ready: false,
    }
  }
  const stage = job.terminal_stage || job.last_stage || 'setup'
  return {
    title,
    state: `Stopped during ${stage}`,
    detail: job.terminal_summary || 'This session can resume from its last safe checkpoint.',
    action: 'Resume',
    ready: false
  }
}

import type { JobSummary } from './types'

export interface SessionPresentation {
  title: string
  state: string
  detail: string
  action: 'Open clips' | 'Open analysis' | 'Resume'
  ready: boolean
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
  const stage = job.terminal_stage || job.last_stage || 'setup'
  return {
    title,
    state: `Stopped during ${stage}`,
    detail: job.terminal_summary || 'This session can resume from its last safe checkpoint.',
    action: 'Resume',
    ready: false
  }
}

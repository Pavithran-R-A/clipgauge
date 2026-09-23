import { describe, expect, it } from 'vitest'
import { sessionPresentation } from './sessionPresentation'

describe('sessionPresentation', () => {
  it('uses stable source identity when ingest has no title', () => {
    const result = sessionPresentation({
      id: 'job-a', title: null, ingested: false, rendered: false,
      source_label: 'YouTube · aqz-KE-bpKQ',
      lifecycle_state: 'FAILED', last_stage: 'ingest',
      terminal_code: 'YTDLP_RATE_LIMITED',
      terminal_summary: 'YouTube is temporarily rate-limiting this request.'
    })

    expect(result.title).toBe('YouTube · aqz-KE-bpKQ')
    expect(result.state).toBe('Needs attention')
    expect(result.detail).toContain('Download failed')
    expect(result.detail).toContain('temporarily rate-limiting')
    expect(result.action).toBe('Resume')
  })

  it('presents cancelled sessions distinctly', () => {
    const result = sessionPresentation({
      id: 'job-c', title: 'Interview', ingested: true, rendered: false,
      lifecycle_state: 'CANCELLED', last_stage: 'asr', resume_safe: true,
      terminal_summary: 'The user stopped this session.'
    })

    expect(result.state).toBe('Cancelled')
    expect(result.detail).toContain('user stopped')
    expect(result.action).toBe('Resume')
  })

  it('presents incomplete jobs as continuable', () => {
    const result = sessionPresentation({
      id: 'job-d', title: 'Draft', ingested: true, rendered: false,
      lifecycle_state: 'RESUMABLE', last_stage: 'scoring'
    })

    expect(result.state).toBe('Continue')
    expect(result.action).toBe('Resume')
  })

  it('separates completed no-recommendation state', () => {
    const result = sessionPresentation({ id: 'job-b', title: 'Talk', ingested: true, rendered: false, outcome: 'SUCCESS_NO_RECOMMENDATIONS' })
    expect(result.state).toBe('Analysis complete · no recommended clips')
    expect(result.action).toBe('Open analysis')
  })
})

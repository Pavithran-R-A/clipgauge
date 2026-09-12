import { describe, expect, it } from 'vitest'
import { validateJobResults } from './jobResultsValidation'

describe('validateJobResults', () => {
  it('accepts the minimal successful job envelope', () => {
    expect(validateJobResults({ job_id: 'job-1' })).toBe(true)
  })

  it('rejects malformed render output arrays', () => {
    expect(validateJobResults({ job_id: 'job-1', render: { outputs: 'not-an-array' } })).toBe(false)
    expect(validateJobResults({ job_id: 'job-1', render: { outputs: [null] } })).toBe(false)
  })

  it('rejects malformed score clip records', () => {
    expect(validateJobResults({ job_id: 'job-1', score: { clips: [null] } })).toBe(false)
    expect(validateJobResults({ job_id: 'job-1', score: { clips: [], borderline_candidates: [{}] } })).toBe(false)
  })

  it('validates enriched Other Moments records', () => {
    const moment = {
      start: 2,
      end: 8,
      recommendation_score: 58,
      candidate_id: 'story-1',
      status: 'OTHER_MOMENT',
      summary: 'A useful moment.',
      story: 'hook_setup_payoff',
      reasons: ['WEAK_SEMANTIC_CLOSURE'],
      quality: {},
    }

    expect(validateJobResults({ job_id: 'job-1', score: { clips: [], borderline_candidates: [moment] } })).toBe(true)
    expect(validateJobResults({ job_id: 'job-1', score: { clips: [], borderline_candidates: [{ ...moment, candidate_id: 7 }] } })).toBe(false)
    expect(validateJobResults({ job_id: 'job-1', score: { clips: [], borderline_candidates: [{ ...moment, status: 7 }] } })).toBe(false)
  })
})

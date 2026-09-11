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
})

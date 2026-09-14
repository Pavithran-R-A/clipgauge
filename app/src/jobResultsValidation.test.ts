import { describe, expect, it } from 'vitest'
import { normalizeJobResults, validateJobResults } from './jobResultsValidation'

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

  it('normalizes historical bait verification adjustments', () => {
    const clip = {
      start: 2,
      end: 8,
      score: 76,
      best_platform: 'tiktok',
      platform_scores: { tiktok: 76 },
      subscores: { hook: 8, funniness: 7, shock: 6, curiosity_gap: 7, value: 8 },
      adjustments: [{ rule: 'bait_verification', factor: 1 }],
      signals_fired: ['story'],
      signals_missing: [],
      confidence: 'high',
      summary: 'A complete moment.',
      arousal_pct: 0.7,
      heatmap_pct: null,
      curve_score: 0.8,
    }

    const value = { job_id: 'job-1', score: { clips: [clip] } }
    expect(validateJobResults(value)).toBe(false)
    const normalized = normalizeJobResults(value)
    expect(normalized?.score?.clips[0]?.adjustments[0]?.reason).toContain('Historical bait verification')
    expect(value.score.clips[0].adjustments[0]).not.toHaveProperty('reason')
  })

  it('accepts preserved additive adjustments and numeric story scores', () => {
    const clip = {
      start: 2,
      end: 8,
      score: 76,
      best_platform: 'tiktok',
      platform_scores: { tiktok: 76 },
      subscores: { hook: 8, funniness: 7, shock: 6, curiosity_gap: 7, value: 8 },
      adjustments: [{ rule: 'candidate_evidence_prior', bonus: 6.6, reason: 'Evidence supports this candidate.' }],
      signals_fired: ['story'],
      signals_missing: [],
      confidence: 'high',
      summary: 'A complete moment.',
      arousal_pct: 0.7,
      heatmap_pct: null,
      curve_score: 0.8,
    }
    const moment = {
      start: 10,
      end: 18,
      recommendation_score: 62,
      status: 'OTHER_MOMENT',
      story: 92,
      reasons: ['WEAK_COLD_HOOK'],
    }

    const value = { job_id: 'job-1', score: { clips: [clip], borderline_candidates: [moment] } }
    expect(validateJobResults(value)).toBe(true)
    expect(normalizeJobResults(value)?.score?.clips[0]?.adjustments[0]).toEqual(clip.adjustments[0])
    expect(normalizeJobResults(value)?.score?.borderline_candidates?.[0]?.story).toBe(92)
  })

  it.each([
    {
      name: 'v0.5.16 factor adjustment',
      adjustment: { rule: 'candidate_evidence_prior', factor: 1, reason: 'Historical factor.' },
      story: 'hook_setup_payoff',
      status: undefined,
    },
    {
      name: 'v0.5.17 additive bonus',
      adjustment: { rule: 'candidate_evidence_prior', bonus: 6.6, reason: 'Current bonus.' },
      story: 92,
      status: undefined,
    },
    {
      name: 'successful no-recommendation result',
      adjustment: { rule: 'candidate_evidence_prior', bonus: 0, reason: 'No qualifying candidate.' },
      story: 'unresolved',
      status: 'SUCCESS_NO_RECOMMENDATIONS',
    },
  ])('opens $name without rerunning processing', ({ adjustment, story, status }) => {
    const value = {
      job_id: 'job-compatibility',
      status,
      diagnostic_metadata: { request_id: 'diagnostic-1', safe_unknown: true },
      score: {
        clips: [{
          start: 2,
          end: 8,
          score: 76,
          best_platform: 'tiktok',
          platform_scores: { tiktok: 76 },
          subscores: { hook: 8, funniness: 7, shock: 6, curiosity_gap: 7, value: 8 },
          adjustments: [adjustment],
          signals_fired: ['story'],
          signals_missing: [],
          confidence: 'high',
          summary: 'A complete moment.',
          arousal_pct: 0.7,
          heatmap_pct: null,
          curve_score: 0.8,
        }],
        borderline_candidates: [{
          start: 10,
          end: 18,
          recommendation_score: 62,
          story,
          reasons: ['WEAK_COLD_HOOK'],
        }],
      },
      render: {
        outputs: [{ clip: 1, path: 'clip.mp4', score: 76, best_platform: 'tiktok', duration: 6, words: 12, event_tags: 2 }],
      },
    }
    const before = structuredClone(value)

    const normalized = normalizeJobResults(value)

    expect(normalized).not.toBeNull()
    expect(normalized?.diagnostic_metadata).toEqual(before.diagnostic_metadata)
    expect(normalized?.score?.clips[0]?.adjustments[0]).toEqual(adjustment)
    expect(normalized?.score?.borderline_candidates?.[0]?.story).toBe(story)
    expect(value).toEqual(before)
  })

  it('rejects malformed compatibility data instead of inventing scores', () => {
    expect(normalizeJobResults({
      job_id: 'job-unsafe',
      score: { clips: [{ score: 'not-a-number' }] },
    })).toBeNull()
  })
})

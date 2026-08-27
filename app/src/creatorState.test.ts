import { describe, expect, it } from 'vitest'
import { creatorHeadline, providerHelperCopy, sourceKind, type CreatorRunState } from './creatorState'

describe('creator state contracts', () => {
  it.each([
    ['IDLE', 'Choose a video to begin.'],
    ['RUNNING', 'Finding the moments worth sharing.'],
    ['SUCCEEDED', 'Your clips are ready to review.'],
    ['FAILED', "We couldn't create clips."],
    ['CANCELLED', 'Clip creation was cancelled.']
  ] as Array<[CreatorRunState, string]>)('uses truthful copy for %s', (state, headline) => {
    expect(creatorHeadline(state)).toBe(headline)
  })

  it('derives helper copy from the selected provider', () => {
    expect(providerHelperCopy('clipgauge-local')).toContain('No API key required')
    expect(providerHelperCopy('openrouter')).toContain('OpenRouter connection')
    expect(providerHelperCopy('gemini')).toContain('Gemini')
    expect(providerHelperCopy('ollama')).toContain('local app')
  })

  it('classifies YouTube URLs without treating local paths as YouTube', () => {
    expect(sourceKind('https://www.youtube.com/watch?v=abc')).toBe('youtube')
    expect(sourceKind('C:\\Videos\\clip.mp4')).toBe('local')
  })
})

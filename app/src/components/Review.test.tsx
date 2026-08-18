import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Review from './Review'
import { api } from '../api'
import type { JobResults, RenderOutput } from '../types'

vi.mock('../api', () => ({
  api: {
    fileUrl: vi.fn((path: string) => `asset://${path}`),
    exportClip: vi.fn().mockResolvedValue('/Downloads/clip.mp4')
  }
}))

vi.mock('./ClipEditor', () => ({
  default: () => <div data-testid="clip-editor" />
}))

const clip = {
  start: 0,
  end: 10,
  score: 80,
  best_platform: 'reels',
  platform_scores: { reels: 80 },
  subscores: { hook: 8 },
  adjustments: [],
  signals_fired: [],
  signals_missing: [],
  confidence: 'standard',
  summary: 'fixture clip',
  arousal_pct: 0.5,
  heatmap_pct: null,
  curve_score: 0.7,
  music: null
}

function results(output: Partial<RenderOutput>): JobResults {
  return {
    job_id: '20260818-155237-c6b118',
    ingest: { title: 'fixture', heatmap: null, probe: { duration_sec: 10, width: 1920, height: 1080 } },
    score: { clips: [clip], llm_mode: 'ollama', model: 'fixture', scored_count: 1 },
    render: {
      outputs: [{ clip: 0, path: null, artifact_status: 'missing', score: 80, best_platform: 'reels', duration: 10, words: 2, event_tags: 0, ...output }],
      emoji_ok: true,
      caption_preset: 'classic'
    },
    events: { counts: {}, timeline: [], arousal_source: 'dsp-proxy' },
    candidates: { count: 1, effective_weights: {}, heatmap_present: false }
  }
}

describe('Review media trust states', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows an explicit artifact diagnostic instead of a blank monitor', () => {
    render(<Review results={results({})} onBack={vi.fn()} onRestyle={vi.fn()} />)
    expect(screen.getByTestId('artifact-error')).toHaveTextContent('RENDER ARTIFACT UNAVAILABLE')
    expect(screen.queryByTestId('review-video')).not.toBeInTheDocument()
  })

  it('shows decode failure diagnostics and supports retry', () => {
    render(
      <Review
        results={results({ path: '/managed/jobs/20260818-155237-c6b118/clips/clip_00.mp4', artifact_status: 'available' })}
        onBack={vi.fn()}
        onRestyle={vi.fn()}
      />
    )
    const video = screen.getByTestId('review-video')
    fireEvent.error(video)
    expect(screen.getByTestId('video-error')).toHaveTextContent('CLIP COULD NOT BE LOADED')
    fireEvent.click(screen.getByRole('button', { name: 'RETRY LOAD' }))
    expect(screen.getByTestId('review-video')).toBeInTheDocument()
  })

  it('exports by job and clip identity, never a source pathname', async () => {
    render(
      <Review
        results={results({ path: '/managed/jobs/20260818-155237-c6b118/clips/clip_00.mp4', artifact_status: 'available' })}
        onBack={vi.fn()}
        onRestyle={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'EXPORT MP4' }))
    expect(api.exportClip).toHaveBeenCalledWith('20260818-155237-c6b118', 0, 'fixture 0:00')
  })
})

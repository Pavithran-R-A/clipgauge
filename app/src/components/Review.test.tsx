import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { waitFor } from '@testing-library/react'
import Review from './Review'
import { api } from '../api'
import type { JobResults, RenderOutput } from '../types'

vi.mock('../api', () => ({
  api: {
    fileUrl: vi.fn((path: string) => `asset://${path}`),
    requestPlaybackUrl: vi.fn().mockResolvedValue('http://127.0.0.1:49152/media/test-token'),
    recordMediaEvent: vi.fn().mockRejectedValue(new Error('diagnostics unavailable')),
    exportClip: vi.fn().mockResolvedValue('/Downloads/clip.mp4')
  }
}))

const { chooseExportDestinationMock } = vi.hoisted(() => ({
  chooseExportDestinationMock: vi.fn(),
}))

vi.mock('../exportDestination', () => ({
  chooseExportDestination: chooseExportDestinationMock,
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

  it('separates score, confidence, quality tier, and platform fit', () => {
    render(<Review results={results({})} onBack={vi.fn()} onRestyle={vi.fn()} />)
    expect(screen.getByText('Recommendation score')).toBeInTheDocument()
    expect(screen.getByText('Recommendation confidence')).toBeInTheDocument()
    expect(screen.getByText('Quality tier')).toBeInTheDocument()
    expect(screen.getByText('Platform fit')).toBeInTheDocument()
    expect(screen.getByText(/0–100 ranking signal, not a probability/)).toBeInTheDocument()
  })

  it('shows an explicit artifact diagnostic instead of a blank monitor', () => {
    render(<Review results={results({})} onBack={vi.fn()} onRestyle={vi.fn()} />)
    expect(screen.getByTestId('artifact-error')).toHaveTextContent('RENDER ARTIFACT UNAVAILABLE')
    expect(screen.queryByTestId('review-video')).not.toBeInTheDocument()
  })

  it('shows ready media controls after successful metadata load', async () => {
    render(
      <Review
        results={results({ path: '/managed/jobs/20260818-155237-c6b118/clips/clip_00.mp4', artifact_status: 'available' })}
        onBack={vi.fn()}
        onRestyle={vi.fn()}
      />
    )
    const video = await waitFor(() => screen.getByTestId('review-video'))
    fireEvent.loadedMetadata(video)
    expect(screen.queryByText('loading clip…')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'EXPORT MP4' })).toBeEnabled()
  })

  it('shows recovery when the playback bridge returns a malformed URL', async () => {
    vi.mocked(api.requestPlaybackUrl).mockResolvedValueOnce(null as never)
    render(
      <Review
        results={results({ path: '/managed/jobs/20260818-155237-c6b118/clips/clip_00.mp4', artifact_status: 'available' })}
        onBack={vi.fn()}
        onRestyle={vi.fn()}
      />
    )

    expect(await screen.findByTestId('video-error')).toHaveTextContent('This clip could not be loaded')
  })

  it('shows decode failure diagnostics and supports retry', async () => {
    render(
      <Review
        results={results({ path: '/managed/jobs/20260818-155237-c6b118/clips/clip_00.mp4', artifact_status: 'available' })}
        onBack={vi.fn()}
        onRestyle={vi.fn()}
      />
    )
    const video = await waitFor(() => screen.getByTestId('review-video'))
    fireEvent.error(video)
    expect(screen.getByTestId('video-error')).toHaveTextContent('CLIP COULD NOT BE LOADED')
    fireEvent.click(screen.getByRole('button', { name: 'RETRY LOAD' }))
    expect(await waitFor(() => screen.getByTestId('review-video'))).toBeInTheDocument()
  })

  it('opens Save As, then exports by job and clip identity', async () => {
    chooseExportDestinationMock.mockResolvedValue('C:/Users/tester/Videos/fixture.mp4')
    render(
      <Review
        results={results({ path: '/managed/jobs/20260818-155237-c6b118/clips/clip_00.mp4', artifact_status: 'available' })}
        onBack={vi.fn()}
        onRestyle={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'EXPORT MP4' }))
    await waitFor(() => expect(chooseExportDestinationMock).toHaveBeenCalledWith({
      jobId: '20260818-155237-c6b118',
      clip: 0,
      suggestedTitle: 'fixture 0:00',
    }))
    expect(api.exportClip).not.toHaveBeenCalled()
  })

  it('does not export when Save As is cancelled', async () => {
    chooseExportDestinationMock.mockResolvedValue(null)
    render(
      <Review
        results={results({ path: '/managed/jobs/20260818-155237-c6b118/clips/clip_00.mp4', artifact_status: 'available' })}
        onBack={vi.fn()}
        onRestyle={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'EXPORT MP4' }))
    await waitFor(() => expect(chooseExportDestinationMock).toHaveBeenCalled())
    expect(api.exportClip).not.toHaveBeenCalled()
  })

  it('surfaces export failures without an unhandled rejection', async () => {
    chooseExportDestinationMock.mockRejectedValue(new Error('export unavailable'))
    render(
      <Review
        results={results({ path: '/managed/jobs/20260818-155237-c6b118/clips/clip_00.mp4', artifact_status: 'available' })}
        onBack={vi.fn()}
        onRestyle={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'EXPORT MP4' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Export could not be completed. Retry the export.')
  })

  it('shows a successful no-recommendations result without export controls', () => {
    const noRecommendations: JobResults = {
      job_id: 'job-no-recommendations',
      outcome: 'SUCCESS_NO_RECOMMENDATIONS',
      ingest: { title: 'fixture', heatmap: null, probe: { duration_sec: 10, width: 1920, height: 1080 } },
      score: { clips: [], llm_mode: 'ollama', model: 'fixture', scored_count: 5, counts: { scored_count: 5 }, borderline_candidates: [{ start: 2, end: 8, recommendation_score: 58, reasons: ['STRONG_RECOMMENDATION_REQUIRED'] }] },
      render: null,
      events: { counts: {}, timeline: [], arousal_source: 'dsp-proxy' },
      candidates: { count: 5, effective_weights: {}, heatmap_present: false },
    }
    render(<Review results={noRecommendations} onBack={vi.fn()} onRestyle={vi.fn()} />)
    expect(screen.getByTestId('no-recommendations')).toHaveTextContent('No recommended clips')
    expect(screen.getByTestId('no-recommendations')).toHaveTextContent('5 moments were evaluated')
    expect(screen.getByText(/Other moments/)).toBeInTheDocument()
    expect(screen.getByText(/Score 58/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'EXPORT MP4' })).not.toBeInTheDocument()
  })

  it('keeps Review open when an other-moment preview fails', async () => {
    const onBack = vi.fn()
    vi.mocked(api.requestPlaybackUrl).mockRejectedValueOnce(new Error('playback unavailable'))
    const noRecommendations: JobResults = {
      job_id: 'job-preview-failure',
      outcome: 'SUCCESS_NO_RECOMMENDATIONS',
      ingest: { title: 'fixture', heatmap: null, probe: { duration_sec: 10, width: 1920, height: 1080 } },
      score: { clips: [], llm_mode: 'ollama', model: 'fixture', scored_count: 1, borderline_candidates: [{ start: 2, end: 8, recommendation_score: 58, reasons: ['Below the recommendation bar'] }] },
      render: null,
      events: { counts: {}, timeline: [], arousal_source: 'dsp-proxy' },
      candidates: { count: 1, effective_weights: {}, heatmap_present: false }
    }
    render(<Review results={noRecommendations} onBack={onBack} onRestyle={vi.fn()} />)

    fireEvent.click(screen.getByText(/Other moments/))
    fireEvent.click(screen.getByRole('button', { name: 'Preview source' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Preview unavailable. Retry the preview.')
    expect(onBack).not.toHaveBeenCalled()
  })

  it('rejects a malformed URL for an other-moment preview', async () => {
    vi.mocked(api.requestPlaybackUrl).mockResolvedValueOnce(null as never)
    const noRecommendations: JobResults = {
      job_id: 'job-preview-malformed',
      outcome: 'SUCCESS_NO_RECOMMENDATIONS',
      ingest: { title: 'fixture', heatmap: null, probe: { duration_sec: 10, width: 1920, height: 1080 } },
      score: { clips: [], llm_mode: 'ollama', model: 'fixture', scored_count: 1, borderline_candidates: [{ start: 2, end: 8, recommendation_score: 58, reasons: ['Below the recommendation bar'] }] },
      render: null,
      events: { counts: {}, timeline: [], arousal_source: 'dsp-proxy' },
      candidates: { count: 1, effective_weights: {}, heatmap_present: false }
    }
    render(<Review results={noRecommendations} onBack={vi.fn()} onRestyle={vi.fn()} />)

    fireEvent.click(screen.getByText(/Other moments/))
    fireEvent.click(screen.getByRole('button', { name: 'Preview source' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Preview unavailable. Retry the preview.')
  })
})

import { act, fireEvent, render, screen } from '@testing-library/react'
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
    exportClip: vi.fn().mockResolvedValue('/Downloads/clip.mp4'),
    getClipTitle: vi.fn().mockResolvedValue({ clip_id: 'clip-fixture', title: 'Generated', title_source: 'model' }),
    setClipTitle: vi.fn().mockResolvedValue({ ok: true, clip_id: 'clip-fixture', title: 'Edited', title_source: 'user' }),
    resetClipTitle: vi.fn().mockResolvedValue({ ok: true, clip_id: 'clip-fixture', title: 'Generated', title_source: 'model' }),
    listCollections: vi.fn().mockResolvedValue({ ok: true, collections: [] }),
    createCollection: vi.fn().mockResolvedValue({ ok: true }),
    updateCollection: vi.fn().mockResolvedValue({ ok: true }),
    deleteCollection: vi.fn().mockResolvedValue({ ok: true }),
    reorderCollection: vi.fn().mockResolvedValue({ ok: true }),
    regenerateCollections: vi.fn().mockResolvedValue({ ok: true, collections: [] }),
    renderCollection: vi.fn().mockResolvedValue({ ok: true, path: '/managed/series.mp4' })
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
  clip_id: 'clip-fixture',
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
  title: 'Generated',
  title_source: 'model' as const,
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

function creatorResults(): JobResults {
  const first = { ...clip, clip_id: 'clip-first', title: 'First generated', start: 0 }
  const second = { ...clip, clip_id: 'clip-second', title: 'Second generated', start: 20 }
  return {
    ...results({}),
    score: { clips: [first, second], llm_mode: 'ollama', model: 'fixture', scored_count: 2 },
    enrich: { clips: [first, second], category: 'knowledge' },
    collections: {
      collections: [{
        id: 'collection-fixture',
        title: 'Suggested series',
        summary: 'Two related clips.',
        clip_ids: ['clip-first', 'clip-second'],
        source: 'ai',
        user_edited: false,
      }]
    },
    render: {
      outputs: [
        { clip: 0, clip_id: 'clip-first', path: null, artifact_status: 'missing', score: 80, best_platform: 'reels', duration: 10, words: 2, event_tags: 0 },
        { clip: 1, clip_id: 'clip-second', path: null, artifact_status: 'missing', score: 80, best_platform: 'reels', duration: 10, words: 2, event_tags: 0 },
      ],
      emoji_ok: true,
      caption_preset: 'classic'
    }
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

  it('pairs reordered outputs by stable clip identity', async () => {
    const first = { ...clip, clip_id: 'clip-alpha', start: 0 }
    const second = { ...clip, clip_id: 'clip-beta', start: 20 }
    const reordered: JobResults = {
      ...results({ path: '/managed/jobs/job/clips/clip_01.mp4', artifact_status: 'available' }),
      score: { clips: [first, second], llm_mode: 'ollama', model: 'fixture', scored_count: 2 },
      render: {
        outputs: [
          { clip: 1, clip_id: 'clip-alpha', path: '/managed/jobs/job/clips/clip_01.mp4', artifact_status: 'available', score: 80, best_platform: 'reels', duration: 10, words: 2, event_tags: 0 },
          { clip: 0, clip_id: 'clip-beta', path: '/managed/jobs/job/clips/clip_00.mp4', artifact_status: 'available', score: 80, best_platform: 'reels', duration: 10, words: 2, event_tags: 0 },
        ],
        emoji_ok: true,
        caption_preset: 'classic',
      },
    }
    render(<Review results={reordered} onBack={vi.fn()} onRestyle={vi.fn()} />)

    expect(await waitFor(() => screen.getByText('0:00'))).toBeInTheDocument()
    chooseExportDestinationMock.mockResolvedValue('C:/Users/tester/Videos/alpha.mp4')
    fireEvent.click(screen.getByRole('button', { name: 'EXPORT MP4' }))
    await waitFor(() => expect(chooseExportDestinationMock).toHaveBeenCalledWith({
      jobId: reordered.job_id,
      clip: 1,
      suggestedTitle: 'fixture 0:00',
    }))
  })

  it('uses render clip numbers for playback and export', async () => {
    const alpha = { ...clip, clip_id: 'clip-alpha', start: 0 }
    const beta = { ...clip, clip_id: 'clip-beta', start: 20 }
    const reordered: JobResults = {
      ...results({}),
      score: { clips: [alpha, beta], llm_mode: 'clipgauge-local', model: 'fixture', scored_count: 2 },
      render: {
        outputs: [
          { clip: 7, clip_id: 'clip-alpha', path: '/managed/jobs/job/clips/clip_07.mp4', artifact_status: 'available', score: 80, best_platform: 'reels', duration: 10, words: 2, event_tags: 0 },
          { clip: 3, clip_id: 'clip-beta', path: '/managed/jobs/job/clips/clip_03.mp4', artifact_status: 'available', score: 80, best_platform: 'reels', duration: 10, words: 2, event_tags: 0 },
        ],
        emoji_ok: true,
        caption_preset: 'classic',
      },
    }
    chooseExportDestinationMock.mockResolvedValue('C:/Users/tester/Videos/alpha.mp4')

    render(<Review results={reordered} onBack={vi.fn()} onRestyle={vi.fn()} />)

    await waitFor(() => expect(api.requestPlaybackUrl).toHaveBeenCalledWith(reordered.job_id, 'render', 7))
    fireEvent.click(screen.getByRole('button', { name: 'EXPORT MP4' }))
    await waitFor(() => expect(chooseExportDestinationMock).toHaveBeenCalledWith({
      jobId: reordered.job_id,
      clip: 7,
      suggestedTitle: 'fixture 0:00',
    }))
  })

  it.each([
    ['clipgauge-local', 'scored locally'],
    ['ollama', 'scored locally'],
    ['lmstudio', 'scored locally'],
    ['groq', 'AI-assisted scoring'],
    ['openrouter', 'AI-assisted scoring'],
  ])('labels %s scoring locality truthfully', (provider, label) => {
    const localized = results({})
    localized.score = { ...localized.score!, llm_mode: provider, provider_kind: provider }
    render(<Review results={localized} onBack={vi.fn()} onRestyle={vi.fn()} />)
    expect(screen.getByText(new RegExp(label))).toBeInTheDocument()
  })

  it('uses singular grammar for one rendered clip', () => {
    render(<Review results={results({})} onBack={vi.fn()} onRestyle={vi.fn()} />)
    expect(screen.getByText(/1 clip ·/)).toBeInTheDocument()
    expect(screen.queryByText(/1 clips ·/)).not.toBeInTheDocument()
  })

  it('does not numerically pair an unknown output identity', () => {
    const stale: JobResults = {
      ...results({ path: '/managed/jobs/job/clips/clip_00.mp4', artifact_status: 'available', clip_id: 'clip-stale' }),
      score: { clips: [{ ...clip, clip_id: 'clip-current' }], llm_mode: 'ollama', model: 'fixture', scored_count: 1 },
    }
    render(<Review results={stale} onBack={vi.fn()} onRestyle={vi.fn()} />)

    expect(screen.getByText('Unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'EXPORT MP4' })).not.toBeInTheDocument()
  })

  it('edits, saves, cancels, and resets a title by stable clip ID', async () => {
    render(<Review results={results({})} onBack={vi.fn()} onRestyle={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Edit title' }))
    const input = screen.getByRole('textbox', { name: 'Publishing title' })
    fireEvent.change(input, { target: { value: 'Edited title' } })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(api.setClipTitle).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Edit title' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Publishing title' }), { target: { value: 'Edited title' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.setClipTitle).toHaveBeenCalledWith('20260818-155237-c6b118', 'clip-fixture', 'Edited title'))
    expect(await screen.findByText('Edited by you')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Reset to generated' }))
    await waitFor(() => expect(api.resetClipTitle).toHaveBeenCalledWith('20260818-155237-c6b118', 'clip-fixture'))
  })

  it('shows category and functional collection controls', () => {
    render(<Review results={creatorResults()} onBack={vi.fn()} onRestyle={vi.fn()} />)

    expect(screen.getByText('Content type · Knowledge')).toBeInTheDocument()
    expect(screen.getByText('Suggested')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Create collection' }))
    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled()
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[0])
    fireEvent.click(checkboxes[1])
    expect(screen.getByRole('button', { name: 'Create' })).toBeEnabled()
  })

  it('uses enriched creator clips when score clips are legacy', () => {
    const legacy = creatorResults()
    legacy.score = {
      ...legacy.score!,
      clips: legacy.score!.clips.map(({ clip_id: _clipId, ...clipWithoutId }) => clipWithoutId),
    }
    render(<Review results={legacy} onBack={vi.fn()} onRestyle={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Create collection' }))

    expect(screen.getByLabelText('First generated')).toBeInTheDocument()
    expect(screen.getByLabelText('Second generated')).toBeInTheDocument()
  })

  it('surfaces a missing collection render path', async () => {
    vi.mocked(api.renderCollection).mockResolvedValueOnce({ ok: true } as never)
    render(<Review results={creatorResults()} onBack={vi.fn()} onRestyle={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Render series' }))

    expect(await screen.findByText('Collection render could not be completed.')).toBeInTheDocument()
  })

  it('surfaces typed collection render failures', async () => {
    vi.mocked(api.renderCollection).mockRejectedValueOnce(new Error('render collection failed'))
    render(<Review results={creatorResults()} onBack={vi.fn()} onRestyle={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Render series' }))

    expect(await screen.findByText('Collection render could not be completed.')).toBeInTheDocument()
  })

  it('rejects duplicate output identities instead of choosing one clip', () => {
    const duplicate: JobResults = {
      ...results({ path: '/managed/jobs/job/clips/clip_00.mp4', artifact_status: 'available', clip_id: 'clip-duplicate' }),
      score: {
        clips: [{ ...clip, clip_id: 'clip-duplicate' }, { ...clip, clip_id: 'clip-duplicate', start: 20 }],
        llm_mode: 'ollama',
        model: 'fixture',
        scored_count: 2,
      },
    }
    render(<Review results={duplicate} onBack={vi.fn()} onRestyle={vi.fn()} />)

    expect(screen.getAllByText('Unavailable')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'EXPORT MP4' })).not.toBeInTheDocument()
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

  it('does not open a stale other-moment preview after unmount', async () => {
    let resolvePlayback: ((value: string) => void) | undefined
    vi.mocked(api.requestPlaybackUrl).mockImplementationOnce(() => new Promise((resolve) => { resolvePlayback = resolve }))
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    const noRecommendations: JobResults = {
      job_id: 'job-preview-unmount',
      outcome: 'SUCCESS_NO_RECOMMENDATIONS',
      ingest: { title: 'fixture', heatmap: null, probe: { duration_sec: 10, width: 1920, height: 1080 } },
      score: { clips: [], llm_mode: 'ollama', model: 'fixture', scored_count: 1, borderline_candidates: [{ start: 2, end: 8, recommendation_score: 58, reasons: ['Below the recommendation bar'] }] },
      render: null,
      events: { counts: {}, timeline: [], arousal_source: 'dsp-proxy' },
      candidates: { count: 1, effective_weights: {}, heatmap_present: false }
    }
    const view = render(<Review results={noRecommendations} onBack={vi.fn()} onRestyle={vi.fn()} />)

    fireEvent.click(screen.getByText(/Other moments/))
    fireEvent.click(screen.getByRole('button', { name: 'Preview source' }))
    expect(resolvePlayback).toBeDefined()
    view.unmount()

    await act(async () => {
      resolvePlayback?.('http://127.0.0.1:49152/media/test-token')
      await new Promise((resolve) => setTimeout(resolve, 0))
    })

    expect(openSpy).not.toHaveBeenCalled()
    openSpy.mockRestore()
  })
})

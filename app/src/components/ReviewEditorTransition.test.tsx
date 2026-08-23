import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { invoke } from '@tauri-apps/api/core'
import { api } from '../api'
import Review from './Review'
import type { JobResults } from '../types'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn()
}))

vi.mock('@tauri-apps/api/event', () => ({
  listen: vi.fn(() => Promise.resolve(vi.fn()))
}))

vi.mock('../api', () => ({
  api: {
    requestPlaybackUrl: vi.fn(),
    recordMediaEvent: vi.fn().mockRejectedValue(new Error('diagnostics unavailable')),
    exportClip: vi.fn().mockResolvedValue('/Downloads/clip.mp4'),
    fileUrl: vi.fn((path: string) => `asset://${path}`)
  }
}))

const context = {
  ok: true,
  window: { start: 0, end: 10 },
  media_path: '/managed/jobs/job-transition/media.mp4',
  probe: { width: 1280, height: 720 },
  trajectory: null,
  edit: {
    start: 0,
    end: 10,
    caption_preset: 'classic',
    camera_mode: 'cut',
    remove_dead_space: false,
    disabled_cuts: [],
    overlays: []
  },
  words: [{ word: 'hello', start: 0, end: 1 }],
  rms: [0.1, 0.5, 0.2],
  rms_grid: 0.5,
  events: [],
  auto_cuts: [],
  run_caption_preset: 'classic'
}

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

function results(): JobResults {
  return {
    job_id: 'job-transition',
    ingest: { title: 'transition fixture', heatmap: null, probe: { duration_sec: 10, width: 1920, height: 1080 } },
    score: { clips: [clip], llm_mode: 'ollama', model: 'fixture', scored_count: 1 },
    render: {
      outputs: [{ clip: 0, path: '/managed/jobs/job-transition/clips/clip_00.mp4', artifact_status: 'available', score: 80, best_platform: 'reels', duration: 10, words: 2, event_tags: 0 }],
      emoji_ok: true,
      caption_preset: 'classic'
    },
    events: { counts: {}, timeline: [], arousal_source: 'dsp-proxy' },
    candidates: { count: 1, effective_weights: {}, heatmap_present: false }
  }
}

describe('Review to Editor recovery contract', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.requestPlaybackUrl).mockImplementation((_jobId, artifactType) =>
      Promise.resolve(artifactType === 'render' ? 'http://127.0.0.1:49152/media/render-token' : 'http://127.0.0.1:49152/media/source-token')
    )
    vi.mocked(api.recordMediaEvent).mockRejectedValue(new Error('diagnostics unavailable'))
    vi.mocked(invoke).mockResolvedValue(context as never)
  })

  it('transitions from completed Review to a ready Editor and safely back', async () => {
    render(<Review results={results()} onBack={vi.fn()} onRestyle={vi.fn()} />)
    expect(await screen.findByTestId('review-video')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Edit clip' }))
    expect(screen.getByText('loading timeline…')).toBeInTheDocument()

    expect(await screen.findByTestId('editor-source-video')).toBeInTheDocument()
    expect(invoke).toHaveBeenCalledWith('edit_tool', { args: ['context', 'job-transition', '0'] })
    expect(api.requestPlaybackUrl).toHaveBeenCalledWith('job-transition', 'source')
    expect(screen.getByText(/CLIP 0/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Render updated clip' })).toBeInTheDocument()
    expect(screen.getByText('captions')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'beast' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'pan' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove dead space' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '← clips' }))
    await waitFor(() => expect(screen.getByTestId('review-video')).toBeInTheDocument())
  })

  it('shows a recoverable error instead of a blank window when edit context rejects', async () => {
    vi.mocked(invoke).mockRejectedValueOnce(new Error('context unavailable'))
    render(<Review results={results()} onBack={vi.fn()} onRestyle={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edit clip' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('context unavailable')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to clips' })).toBeInTheDocument()
  })

  it('keeps the Editor shell usable when source playback URL rejects', async () => {
    vi.mocked(api.requestPlaybackUrl).mockImplementation((_jobId, artifactType) =>
      artifactType === 'render'
        ? Promise.resolve('http://127.0.0.1:49152/media/render-token')
        : Promise.reject(new Error('source playback unavailable'))
    )
    render(<Review results={results()} onBack={vi.fn()} onRestyle={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edit clip' }))
    expect(await screen.findByText(/source playback unavailable/)).toBeInTheDocument()
    expect(screen.getByText('captions')).toBeInTheDocument()
  })
})

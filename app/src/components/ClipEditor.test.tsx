import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { invoke } from '@tauri-apps/api/core'
import { api } from '../api'
import ClipEditor from './ClipEditor'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn()
}))

const eventHarness = vi.hoisted(() => ({
  callback: null as ((event: { payload: { event: string; message?: string; ok?: boolean; error?: string } }) => void) | null
}))

vi.mock('@tauri-apps/api/event', () => ({
  listen: vi.fn((_name: string, callback: (event: { payload: { event: string; message?: string; ok?: boolean; error?: string } }) => void) => {
    eventHarness.callback = callback
    return Promise.resolve(vi.fn())
  })
}))

vi.mock('../api', () => ({
  api: {
    fileUrl: vi.fn((path: string) => `asset://${path}`),
    requestPlaybackUrl: vi.fn().mockResolvedValue('http://127.0.0.1:49152/media/source-token'),
    recordMediaEvent: vi.fn().mockRejectedValue(new Error('diagnostics unavailable'))
  }
}))

const validContext = {
  ok: true,
  window: { start: 0, end: 10 },
  media_path: '/managed/jobs/job-1/media.mp4',
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

function renderEditor(onClose = vi.fn(), onRendered = vi.fn()) {
  return render(
    <ClipEditor
      jobId="job-1"
      clipIndex={0}
      onClose={onClose}
      onRendered={onRendered}
    />
  )
}

describe('ClipEditor loading, recovery, and ready states', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.requestPlaybackUrl).mockResolvedValue('http://127.0.0.1:49152/media/source-token')
  })

  it('shows a non-blank loading state while context is pending', () => {
    vi.mocked(invoke).mockReturnValue(new Promise(() => {}) as never)
    renderEditor()
    expect(screen.getByText('loading timeline…')).toBeInTheDocument()
  })

  it('shows diagnostic text and actionable retry/back controls for context failure', async () => {
    vi.mocked(invoke).mockResolvedValue({
      ok: false,
      error: 'Editor data is unavailable for this clip.',
      diagnostic_id: 'diag-editor-123'
    } as never)
    const onClose = vi.fn()
    renderEditor(onClose)

    expect(await screen.findByRole('alert')).toHaveTextContent('Diagnostic ID: diag-editor-123.')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to clips' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(invoke).toHaveBeenCalledTimes(2))
    fireEvent.click(screen.getByRole('button', { name: 'Back to clips' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('transitions to a ready source-monitor DOM after valid context and media URL', async () => {
    vi.mocked(invoke).mockResolvedValue(validContext as never)
    renderEditor()

    const video = await screen.findByTestId('editor-source-video')
    expect(video).toHaveAttribute('src', 'http://127.0.0.1:49152/media/source-token')
    expect(screen.getByText(/CLIP 0/)).toBeInTheDocument()
    fireEvent.loadedMetadata(video)
    expect(screen.getByRole('button', { name: 'Render updated clip' })).toBeEnabled()
  })

  it('clears Rendering and reports success when the native bridge emits a terminal event', async () => {
    vi.mocked(invoke).mockResolvedValue(validContext as never)
    const onRendered = vi.fn()
    renderEditor(vi.fn(), onRendered)

    const video = await screen.findByTestId('editor-source-video')
    fireEvent.loadedMetadata(video)
    const renderButton = screen.getByRole('button', { name: 'Render updated clip' })
    fireEvent.click(renderButton)
    await waitFor(() => expect(invoke).toHaveBeenCalledWith('run_edit_render', { jobId: 'job-1', clip: 0 }))
    expect(screen.getByRole('button', { name: 'Rendering…' })).toBeDisabled()

    eventHarness.callback?.({ payload: { event: 'terminal', ok: true } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Render updated clip' })).toBeEnabled())
    expect(screen.queryByRole('button', { name: 'Rendering…' })).not.toBeInTheDocument()
    expect(onRendered).toHaveBeenCalledOnce()
  })
})

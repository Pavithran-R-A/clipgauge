import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const mocks = vi.hoisted(() => ({
  pipelineHandler: undefined as ((event: { payload: Record<string, unknown> }) => void) | undefined,
  api: {
    setupState: vi.fn(),
    listJobs: vi.fn(),
    igStatus: vi.fn(),
    igSync: vi.fn(),
    jobResults: vi.fn(),
    runJob: vi.fn(),
    resumeJob: vi.fn(),
    cancelJob: vi.fn()
  }
}))

vi.mock('@tauri-apps/api/event', () => ({
  listen: vi.fn(async (_name: string, callback: (event: { payload: Record<string, unknown> }) => void) => {
    mocks.pipelineHandler = callback
    return () => undefined
  })
}))

vi.mock('./api', () => ({ api: mocks.api }))
vi.mock('./components/Onboarding', () => ({ default: () => <div data-testid="onboarding" /> }))
vi.mock('./components/Loop', () => ({ default: () => <div data-testid="loop" /> }))
vi.mock('./components/Review', () => ({ default: ({ results }: { results: { job_id: string } }) => <div data-testid="review">{results.job_id}</div> }))
vi.mock('./components/Studio', () => ({
  default: ({ error, notice, onCancel }: { error: string | null; notice: string | null; onCancel: () => void }) => (
    <>
      <div data-testid="studio-error">{error}</div>
      <div data-testid="studio-notice">{notice}</div>
      <button data-testid="cancel-job" onClick={onCancel}>cancel</button>
    </>
  )
}))

beforeEach(() => {
  mocks.pipelineHandler = undefined
  mocks.api.setupState.mockResolvedValue({ onboarded: true, gemini_key: false })
  mocks.api.listJobs.mockResolvedValue([])
  mocks.api.igStatus.mockResolvedValue({ connected: false })
  mocks.api.igSync.mockResolvedValue({})
  mocks.api.jobResults.mockResolvedValue({ job_id: '20260818-155237-c6b118' })
  mocks.api.cancelJob.mockResolvedValue(undefined)
  vi.clearAllMocks()
})

describe('structured pipeline terminal events', () => {
  it('renders a typed actionable failure with its diagnostic identifier', async () => {
    render(<App />)
    await waitFor(() => expect(mocks.pipelineHandler).toBeDefined())
    mocks.pipelineHandler?.({
      payload: {
        event: 'terminal',
        protocol_version: 1,
        ok: false,
        code: 'YTDLP_METADATA_FAILED',
        message: 'yt-dlp could not process this video.',
        retryable: true,
        diagnostic_id: 'diag-test-123'
      }
    })
    expect(await screen.findByTestId('studio-error')).toHaveTextContent('yt-dlp could not process this video.')
    expect(screen.getByTestId('studio-error')).not.toHaveTextContent('YTDLP_METADATA_FAILED')
    expect(screen.getByTestId('studio-error')).toHaveTextContent('diag-test-123')
  })

  it('sends the active job ID through the cancellation command', async () => {
    render(<App />)
    await waitFor(() => expect(mocks.pipelineHandler).toBeDefined())
    mocks.pipelineHandler?.({ payload: { event: 'job', job_id: '20260818-155237-c6b118' } })
    fireEvent.click(await screen.findByTestId('cancel-job'))
    await waitFor(() => expect(mocks.api.cancelJob).toHaveBeenCalledWith('20260818-155237-c6b118'))
  })

  it('renders cancellation as resumable status rather than an error', async () => {
    render(<App />)
    await waitFor(() => expect(mocks.pipelineHandler).toBeDefined())
    mocks.pipelineHandler?.({
      payload: {
        event: 'terminal',
        protocol_version: 1,
        ok: false,
        code: 'CANCELLED',
        message: 'The job was cancelled. Completed checkpoints remain available for resume.',
        retryable: true
      }
    })
    expect(await screen.findByTestId('studio-notice')).toHaveTextContent('Completed checkpoints remain available for resume')
    expect(screen.getByTestId('studio-error')).toHaveTextContent('')
  })

  it('renders a safe fallback for a synthesized missing-terminal failure', async () => {
    render(<App />)
    await waitFor(() => expect(mocks.pipelineHandler).toBeDefined())
    mocks.pipelineHandler?.({
      payload: {
        event: 'terminal',
        protocol_version: 1,
        ok: false,
        code: 'PIPELINE_EXIT_WITHOUT_TERMINAL',
        message: 'The local pipeline stopped before reporting a complete result.',
        retryable: true,
        diagnostic_id: 'diag-synthesized'
      }
    })
    expect(await screen.findByTestId('studio-error')).toHaveTextContent('stopped before reporting')
    expect(screen.getByTestId('studio-error')).not.toHaveTextContent('/home/ubuntu')
  })
})

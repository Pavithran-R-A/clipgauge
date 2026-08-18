import { render, screen, waitFor } from '@testing-library/react'
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
    resumeJob: vi.fn()
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
  default: ({ error }: { error: string | null }) => <div data-testid="studio-error">{error}</div>
}))

beforeEach(() => {
  mocks.pipelineHandler = undefined
  mocks.api.setupState.mockResolvedValue({ onboarded: true, gemini_key: false })
  mocks.api.listJobs.mockResolvedValue([])
  mocks.api.igStatus.mockResolvedValue({ connected: false })
  mocks.api.igSync.mockResolvedValue({})
  mocks.api.jobResults.mockResolvedValue({ job_id: '20260818-155237-c6b118' })
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
    expect(screen.getByTestId('studio-error')).toHaveTextContent('YTDLP_METADATA_FAILED')
    expect(screen.getByTestId('studio-error')).toHaveTextContent('diag-test-123')
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

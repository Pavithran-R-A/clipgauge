import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
    setupInventory: vi.fn(),
    preflight: vi.fn(),
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
  default: ({ error, notice, running, onRun, onCancel }: { error: string | null; notice: string | null; running: boolean; onRun: (...args: string[]) => void; onCancel: () => void }) => (
    <>
      <div data-testid="studio-error">{error}</div>
      <div data-testid="studio-notice">{notice}</div>
      <button data-testid="create-job" disabled={running} onClick={() => onRun('C:\\Videos\\source.mp4', 'clipgauge-local', 'classic')}>create</button>
      <button data-testid="cancel-job" onClick={onCancel}>cancel</button>
    </>
  )
}))
vi.mock('./components/SetupCenter', () => ({
  default: ({ onUseLocal, onBack }: { onUseLocal?: () => void; onBack: () => void }) => (
    <div data-testid="setup-center">
      <button onClick={onUseLocal}>Use ClipGauge Local</button>
      <button onClick={onBack}>Back to Create</button>
    </div>
  )
}))
vi.mock('./components/ProviderCenter', () => ({
  default: ({ onOpenSetup, onBack }: { onOpenSetup?: () => void; onBack: () => void }) => (
    <div data-testid="provider-center">
      <button onClick={onOpenSetup}>Set up local AI</button>
      <button onClick={onBack}>Back to Create</button>
    </div>
  )
}))

beforeEach(() => {
  mocks.pipelineHandler = undefined
  mocks.api.setupState.mockResolvedValue({ onboarded: true, gemini_key: false })
  mocks.api.listJobs.mockResolvedValue([])
  mocks.api.igStatus.mockResolvedValue({ connected: false })
  mocks.api.igSync.mockResolvedValue({})
  mocks.api.jobResults.mockResolvedValue({ job_id: '20260818-155237-c6b118' })
  mocks.api.setupInventory.mockResolvedValue({})
  mocks.api.preflight.mockResolvedValue({ state: 'blocked', checks: [{ state: 'blocked', message: 'setup required' }] })
  mocks.api.cancelJob.mockResolvedValue(undefined)
  vi.clearAllMocks()
})

describe('application navigation handoffs', () => {
  it('routes Setup to Create and selects ClipGauge Local', async () => {
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Setup & Storage' }))
    expect(await screen.findByTestId('setup-center')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Use ClipGauge Local' }))
    expect(await screen.findByTestId('cancel-job')).toBeInTheDocument()
  })

  it('routes Provider Center to Setup for local installation', async () => {
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'AI Providers' }))
    expect(await screen.findByTestId('provider-center')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Set up local AI' }))
    expect(await screen.findByTestId('setup-center')).toBeInTheDocument()
  })
})

describe('structured pipeline terminal events', () => {
  it('prevents a second creator launch while preflight is pending', async () => {
    let releasePreflight: (value: { state: string; checks: never[] }) => void = () => undefined
    mocks.api.preflight.mockImplementation(() => new Promise((resolve) => { releasePreflight = resolve }))
    render(<App />)

    const create = await screen.findByTestId('create-job')
    await userEvent.click(create)
    expect(create).toBeDisabled()
    await userEvent.click(create)
    expect(mocks.api.preflight).toHaveBeenCalledTimes(1)
    releasePreflight({ state: 'blocked', checks: [] })
  })

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
    await waitFor(() => expect(screen.getByTestId('studio-error')).toHaveTextContent('stopped before reporting'))
    expect(screen.getByTestId('studio-error')).not.toHaveTextContent('/home/ubuntu')
  })
})

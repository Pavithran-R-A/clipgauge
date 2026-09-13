import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const mocks = vi.hoisted(() => ({
  pipelineHandler: undefined as ((event: { payload: Record<string, unknown> }) => void) | undefined,
  listen: vi.fn(),
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
    cancelJob: vi.fn(),
    repairGpu: vi.fn(),
    recordMediaEvent: vi.fn()
  }
}))

vi.mock('@tauri-apps/api/event', () => ({
  listen: mocks.listen
}))

vi.mock('./api', () => ({ api: mocks.api }))
vi.mock('./components/Onboarding', () => ({ default: () => <div data-testid="onboarding" /> }))
vi.mock('./components/Loop', () => ({ default: () => <div data-testid="loop" /> }))
vi.mock('./components/Review', () => ({ default: ({ results }: { results: { job_id: string } }) => <div data-testid="review">{results.job_id}</div> }))
vi.mock('./components/Studio', () => ({
  default: ({ error, notice, running, runState, stages, onRun, onCancel, onContinueCpu, onRepairGpu, onResume }: { error: string | null; notice: string | null; running: boolean; runState?: string; stages?: Record<string, { message: string }>; onRun: (...args: Array<string | undefined>) => void; onCancel: () => void; onContinueCpu?: () => void; onRepairGpu?: () => void; onResume?: (id: string) => void }) => (
    <>
      <div data-testid="studio-error">{error}</div>
      <div data-testid="studio-notice">{notice}</div>
      <div data-testid="studio-state">{runState}</div>
      <div data-testid="stage-asr">{stages?.asr?.message}</div>
      <button data-testid="create-job" disabled={running} onClick={() => onRun('C:\\Videos\\source.mp4', 'clipgauge-local', 'classic')}>create</button>
      <button data-testid="create-custom-job" disabled={running} onClick={() => onRun('C:\\Videos\\source.mp4', 'custom', 'classic', undefined, undefined, undefined, undefined, undefined, 'best', 'recommended')}>custom</button>
      <button data-testid="create-cloudflare-job" disabled={running} onClick={() => onRun('C:\\Videos\\source.mp4', 'cloudflare', 'classic')}>cloudflare</button>
      <button data-testid="cancel-job" onClick={onCancel}>cancel</button>
      <button data-testid="continue-cpu" onClick={onContinueCpu}>continue cpu</button>
      <button data-testid="repair-gpu" onClick={onRepairGpu}>repair gpu</button>
      <button data-testid="resume-job" onClick={() => onResume?.('job-a')}>resume</button>
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
  mocks.listen.mockImplementation(async (_name: string, callback: (event: { payload: Record<string, unknown> }) => void) => {
    mocks.pipelineHandler = callback
    return () => undefined
  })
  mocks.api.setupState.mockResolvedValue({ onboarded: true, has_gemini_key: false, provider_keys: {} })
  mocks.api.listJobs.mockResolvedValue([])
  mocks.api.igStatus.mockResolvedValue({ connected: false })
  mocks.api.igSync.mockResolvedValue({})
  mocks.api.jobResults.mockResolvedValue({ job_id: '20260818-155237-c6b118' })
  mocks.api.setupInventory.mockResolvedValue({})
  mocks.api.preflight.mockResolvedValue({ state: 'blocked', selected_llm: 'local', checks: [{ state: 'blocked', message: 'setup required' }] })
  mocks.api.cancelJob.mockResolvedValue(undefined)
  mocks.api.resumeJob.mockResolvedValue(undefined)
  mocks.api.repairGpu.mockResolvedValue(undefined)
  mocks.api.recordMediaEvent.mockResolvedValue(undefined)
  const localValues = new Map<string, string>()
  Object.defineProperty(window, 'localStorage', { configurable: true, value: {
    getItem: (key: string) => localValues.get(key) ?? null,
    setItem: (key: string, value: string) => { localValues.set(key, value) }
  } })
  vi.clearAllMocks()
})

describe('application navigation handoffs', () => {
  it('does not create an unhandled rejection when error telemetry fails', async () => {
    mocks.api.recordMediaEvent.mockRejectedValueOnce(new Error('telemetry unavailable'))
    render(<App />)

    window.dispatchEvent(new Event('unhandledrejection'))

    await waitFor(() => expect(mocks.api.recordMediaEvent).toHaveBeenCalledWith({
      label: 'app',
      event: 'runtime_error',
      error_message: 'undefined'
    }))
  })

  it('uses cached setup state for immediate shell rendering', async () => {
    window.localStorage.setItem('clipgauge.setup.state.v1', JSON.stringify({ onboarded: true, has_gemini_key: false, provider_keys: {} }))
    mocks.api.setupState.mockImplementation(() => new Promise(() => undefined))
    render(<App />)

    expect(await screen.findByRole('button', { name: 'Setup & Storage' })).toBeInTheDocument()
  })

  it('reuses the cached local model without another inventory scan', async () => {
    window.localStorage.setItem('clipgauge.setup.inventory.v1', JSON.stringify({
      schema_version: 1,
      app_version: '0.5.16',
      platform: 'windows-x86_64',
      runtime_manifest_digest: 'manifest-a',
      last_verified_at: 1_700_000_000,
      value: {
        state: 'ready',
        local_ai: { selected_model_id: 'clipgauge-local/balanced' },
        models: [{ asset_id: 'clipgauge-local/balanced' }],
        runtime: {},
        core_assets: [],
        storage: {},
        catalog: []
      }
    }))
    mocks.api.preflight.mockResolvedValue({ state: 'ready', selected_llm: 'local', checks: [] })
    render(<App />)

    await userEvent.click(await screen.findByTestId('create-job'))

    await waitFor(() => expect(mocks.api.preflight).toHaveBeenCalledWith(
      'clipgauge-local',
      'clipgauge-local/balanced',
      undefined,
      undefined,
      undefined,
      'C:\\Videos\\source.mp4',
      'private',
    ))
    expect(mocks.api.setupInventory).not.toHaveBeenCalled()
  })

  it('does not reuse a local model from an incomplete inventory envelope', async () => {
    window.localStorage.setItem('clipgauge.setup.inventory.v1', JSON.stringify({
      schema_version: 1,
      app_version: '0.5.16',
      value: {
        state: 'ready',
        local_ai: { selected_model_id: 'clipgauge-local/balanced' },
        models: [{ asset_id: 'clipgauge-local/balanced' }],
        runtime: {},
        core_assets: [],
        storage: {},
        catalog: []
      }
    }))
    mocks.api.preflight.mockResolvedValue({ state: 'ready', selected_llm: 'local', checks: [] })
    render(<App />)

    await userEvent.click(await screen.findByTestId('create-job'))

    await waitFor(() => expect(mocks.api.setupInventory).toHaveBeenCalledTimes(1))
  })

  it('retains a natively discovered local model for later runs', async () => {
    mocks.api.setupInventory.mockResolvedValue({
      state: 'ready',
      platform: 'windows-x86_64',
      runtime_manifest_digest: 'manifest-a',
      local_ai: { selected_model_id: 'clipgauge-local/balanced' },
      models: [{ asset_id: 'clipgauge-local/balanced' }],
      runtime: {},
      core_assets: [],
      storage: {},
      catalog: []
    })
    mocks.api.preflight.mockResolvedValue({ state: 'ready', selected_llm: 'local', checks: [] })
    render(<App />)

    await userEvent.click(await screen.findByTestId('create-job'))
    await waitFor(() => expect(mocks.api.runJob).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(JSON.parse(window.localStorage.getItem('clipgauge.setup.inventory.v1') ?? '{}')).toMatchObject({
      schema_version: 1,
      app_version: '0.5.16',
      platform: 'windows-x86_64',
      runtime_manifest_digest: 'manifest-a',
      value: { local_ai: { selected_model_id: 'clipgauge-local/balanced' } },
    }))
    mocks.pipelineHandler?.({ payload: { event: 'terminal', ok: false, message: 'retry' } })
    await waitFor(() => expect(screen.getByTestId('create-job')).not.toBeDisabled())

    await userEvent.click(screen.getByTestId('create-job'))
    await waitFor(() => expect(mocks.api.runJob).toHaveBeenCalledTimes(2))
    expect(mocks.api.setupInventory).toHaveBeenCalledTimes(1)
    expect(mocks.api.preflight).toHaveBeenLastCalledWith(
      'clipgauge-local',
      'clipgauge-local/balanced',
      undefined,
      undefined,
      undefined,
      'C:\\Videos\\source.mp4',
      'private',
    )
  })

  it('does not sync Instagram when status data is malformed', async () => {
    mocks.api.igStatus.mockResolvedValueOnce({ connected: 'yes' })
    render(<App />)

    await waitFor(() => expect(mocks.api.igStatus).toHaveBeenCalledTimes(1))
    expect(mocks.api.igSync).not.toHaveBeenCalled()
  })

  it('ignores cached setup state with malformed provider flags', () => {
    window.localStorage.setItem('clipgauge.setup.state.v1', JSON.stringify({ onboarded: true, has_gemini_key: false, provider_keys: [] }))
    mocks.api.setupState.mockImplementation(() => new Promise(() => undefined))
    render(<App />)

    expect(document.querySelector('.boot')).toBeInTheDocument()
  })

  it('surfaces pipeline listener registration failures', async () => {
    mocks.listen.mockRejectedValueOnce(new Error('pipeline bridge unavailable'))
    render(<App />)

    expect(await screen.findByTestId('studio-error')).toHaveTextContent('Pipeline events are unavailable. Restart ClipGauge and retry.')
  })

  it('does not expose raw bridge errors in pipeline failure copy', async () => {
    mocks.listen.mockRejectedValueOnce(new Error("TypeError: Cannot read properties of undefined (reading 'transformCallback')"))
    render(<App />)

    const error = await screen.findByTestId('studio-error')
    expect(error).toHaveTextContent('Pipeline events are unavailable. Restart ClipGauge and retry.')
    expect(error).not.toHaveTextContent('transformCallback')
  })

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

  it('surfaces saved-session load failures instead of leaving the action silent', async () => {
    mocks.api.listJobs.mockResolvedValue([{ id: 'job-a', title: 'Saved clip', ingested: true, rendered: true }])
    mocks.api.jobResults.mockRejectedValueOnce(new Error('session unavailable'))
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Sessions' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Open clips' }))
    expect(await screen.findByTestId('studio-error')).toHaveTextContent('This session could not be opened. Retry from Sessions.')
  })

  it('surfaces malformed saved-session results instead of rendering unsafe data', async () => {
    mocks.api.listJobs.mockResolvedValue([{ id: 'job-a', title: 'Saved clip', ingested: true, rendered: true }])
    mocks.api.jobResults.mockResolvedValueOnce({ job_id: 'job-a', render: { outputs: 'not-an-array' } })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Sessions' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Open clips' }))
    expect(await screen.findByTestId('studio-error')).toHaveTextContent('This session could not be opened. Retry from Sessions.')
  })

  it('surfaces saved-session listing failures instead of showing an empty history', async () => {
    mocks.api.listJobs.mockRejectedValueOnce(new Error('history unavailable'))
    render(<App />)

    expect(await screen.findByText('Sessions unavailable. Open Sessions and retry.')).toBeInTheDocument()
  })

  it('retries saved-session loading when the user opens Sessions', async () => {
    mocks.api.listJobs
      .mockRejectedValueOnce(new Error('history unavailable'))
      .mockResolvedValueOnce([{ id: 'job-a', title: 'Recovered session', ingested: true, rendered: true, outcome: null }])
    render(<App />)

    expect(await screen.findByText('Sessions unavailable. Open Sessions and retry.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Sessions' }))
    expect((await screen.findAllByText('Recovered session')).length).toBeGreaterThanOrEqual(2)
  })

  it('surfaces malformed saved-session listings instead of rendering unsafe data', async () => {
    mocks.api.listJobs.mockResolvedValueOnce([{ id: 'job-a', title: 'Saved clip', ingested: 'yes', rendered: true }])
    render(<App />)

    expect(await screen.findByText('Sessions unavailable. Open Sessions and retry.')).toBeInTheDocument()
  })
})

describe('structured pipeline terminal events', () => {
  it('surfaces malformed preflight responses safely', async () => {
    mocks.api.preflight.mockResolvedValueOnce({ state: 'ready', checks: null })
    render(<App />)
    await userEvent.click(await screen.findByTestId('create-job'))
    expect(await screen.findByTestId('studio-error')).toHaveTextContent('The video could not be processed. Retry the job.')
  })

  it('prevents a second creator launch while preflight is pending', async () => {
    let releasePreflight: (value: { state: string; selected_llm: string; checks: never[] }) => void = () => undefined
    mocks.api.preflight.mockImplementation(() => new Promise((resolve) => { releasePreflight = resolve }))
    render(<App />)

    const create = await screen.findByTestId('create-job')
    await userEvent.click(create)
    expect(create).toBeDisabled()
    await userEvent.click(create)
    expect(mocks.api.preflight).toHaveBeenCalledTimes(1)
    releasePreflight({ state: 'blocked', selected_llm: 'local', checks: [] })
  })

  it('does not launch a job after preflight resolves post-unmount', async () => {
    let releasePreflight: (value: { state: string; selected_llm: string; checks: never[] }) => void = () => undefined
    mocks.api.preflight.mockImplementation(() => new Promise((resolve) => { releasePreflight = resolve }))
    const { unmount } = render(<App />)

    await userEvent.click(await screen.findByTestId('create-job'))
    unmount()

    await act(async () => {
      releasePreflight({ state: 'ready', selected_llm: 'local', checks: [] })
      await new Promise((resolve) => setTimeout(resolve, 0))
    })

    expect(mocks.api.runJob).not.toHaveBeenCalled()
  })

  it('forwards persisted custom model and endpoint settings', async () => {
    const values = new Map<string, string>()
    Object.defineProperty(window, 'localStorage', { configurable: true, value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value) }
    } })
    window.localStorage.setItem('clipgauge.provider-model.custom', 'manual-model')
    window.localStorage.setItem('clipgauge.provider-endpoint.custom', 'https://custom.example/v1')
    mocks.api.preflight.mockResolvedValue({ state: 'ready', selected_llm: 'local', checks: [] })
    render(<App />)

    await userEvent.click(await screen.findByTestId('create-custom-job'))
    await waitFor(() => expect(mocks.api.preflight).toHaveBeenCalledWith(
      'custom',
      'manual-model',
      'https://custom.example/v1',
      'bearer',
      undefined,
      'C:\\Videos\\source.mp4',
      'best',
    ))
    await waitFor(() => expect(mocks.api.runJob).toHaveBeenCalledWith(
      'C:\\Videos\\source.mp4',
      'custom',
      'classic',
      'manual-model',
      'https://custom.example/v1',
      'bearer',
      undefined,
      undefined,
      'best',
      'recommended',
    ))
  })

  it('forwards persisted Cloudflare endpoint settings', async () => {
    const values = new Map<string, string>()
    Object.defineProperty(window, 'localStorage', { configurable: true, value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value) }
    } })
    window.localStorage.setItem('clipgauge.provider-endpoint.cloudflare', 'https://account.example/v1')
    mocks.api.preflight.mockResolvedValue({ state: 'ready', selected_llm: 'local', checks: [] })
    render(<App />)

    await userEvent.click(await screen.findByTestId('create-cloudflare-job'))
    await waitFor(() => expect(mocks.api.preflight).toHaveBeenCalledWith(
      'cloudflare',
      undefined,
      'https://account.example/v1',
      'bearer',
      undefined,
      'C:\\Videos\\source.mp4',
      'private',
    ))
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
    await waitFor(() => expect(screen.getByTestId('studio-error')).toHaveTextContent('yt-dlp could not process this video.'))
    expect(screen.getByTestId('studio-error')).not.toHaveTextContent('YTDLP_METADATA_FAILED')
    expect(screen.getByTestId('studio-error')).toHaveTextContent('diag-test-123')
  })

  it('explains CPU speech memory failures with an actionable retry', async () => {
    render(<App />)
    await waitFor(() => expect(mocks.pipelineHandler).toBeDefined())
    mocks.pipelineHandler?.({
      payload: {
        event: 'terminal',
        ok: false,
        code: 'ASR_TRANSCRIPTION_RESOURCE_EXHAUSTED',
        message: 'Speech recognition needs more working memory.',
        retryable: true,
        diagnostic_id: 'diag-asr-memory',
      },
    })

    await waitFor(() => expect(screen.getByTestId('studio-error')).toHaveTextContent('Close other applications'))
    expect(screen.getByTestId('studio-error')).toHaveTextContent('diag-asr-memory')
  })

  it('sends the active job ID through the cancellation command', async () => {
    render(<App />)
    await waitFor(() => expect(mocks.pipelineHandler).toBeDefined())
    mocks.pipelineHandler?.({ payload: { event: 'job', job_id: '20260818-155237-c6b118' } })
    fireEvent.click(await screen.findByTestId('cancel-job'))
    await waitFor(() => expect(mocks.api.cancelJob).toHaveBeenCalledWith('20260818-155237-c6b118'))
  })

  it('ignores cancellation failures after App unmounts', async () => {
    let rejectCancel: (reason?: unknown) => void = () => undefined
    mocks.api.cancelJob.mockImplementationOnce(() => new Promise<void>((_, reject) => { rejectCancel = reject }))
    const { unmount } = render(<App />)
    await waitFor(() => expect(mocks.pipelineHandler).toBeDefined())
    mocks.pipelineHandler?.({ payload: { event: 'job', job_id: '20260818-155237-c6b118' } })
    fireEvent.click(await screen.findByTestId('cancel-job'))
    unmount()

    await act(async () => {
      rejectCancel(new Error('cancel bridge unavailable'))
      await Promise.resolve()
    })
    expect(mocks.api.cancelJob).toHaveBeenCalledWith('20260818-155237-c6b118')
  })

  it('runs GPU repair from the recovery surface', async () => {
    render(<App />)
    await userEvent.click(await screen.findByTestId('repair-gpu'))
    await waitFor(() => expect(mocks.api.repairGpu).toHaveBeenCalledTimes(1))
    expect(screen.getByTestId('studio-notice')).toHaveTextContent('GPU speech acceleration repair completed')
  })

  it('restores async liveness after StrictMode effect cleanup', async () => {
    let resolveRepair: (() => void) | undefined
    mocks.api.repairGpu.mockImplementationOnce(() => new Promise<void>((resolve) => { resolveRepair = resolve }))
    render(<StrictMode><App /></StrictMode>)
    await userEvent.click(await screen.findByTestId('repair-gpu'))

    await act(async () => {
      resolveRepair?.()
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    expect(screen.getByTestId('studio-notice')).toHaveTextContent('GPU speech acceleration repair completed')
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

  it('routes CPU recovery to a fresh attempt and ignores late events', async () => {
    render(<App />)
    await waitFor(() => expect(mocks.pipelineHandler).toBeDefined())
    mocks.pipelineHandler?.({ payload: { event: 'job', job_id: 'job-a', attempt_id: 'attempt-a' } })
    mocks.pipelineHandler?.({ payload: { event: 'terminal', job_id: 'job-a', attempt_id: 'attempt-a', ok: false, code: 'ASR_GPU_FALLBACK_REQUIRES_APPROVAL', message: 'GPU failed' } })

    await userEvent.click(await screen.findByTestId('continue-cpu'))
    await waitFor(() => expect(mocks.api.resumeJob).toHaveBeenCalledWith('job-a', undefined, undefined, undefined, undefined, undefined, undefined, undefined, true, undefined, undefined))

    mocks.pipelineHandler?.({ payload: { event: 'job', job_id: 'job-a', attempt_id: 'attempt-b' } })
    mocks.pipelineHandler?.({ payload: { event: 'progress', job_id: 'job-a', attempt_id: 'attempt-b', stage: 'asr', message: 'CPU recovery running' } })
    await waitFor(() => expect(screen.getByTestId('stage-asr')).toHaveTextContent('CPU recovery running'))

    mocks.pipelineHandler?.({ payload: { event: 'progress', job_id: 'job-a', attempt_id: 'attempt-a', stage: 'asr', message: 'late GPU attempt' } })
    expect(screen.getByTestId('stage-asr')).not.toHaveTextContent('late GPU attempt')
    mocks.pipelineHandler?.({ payload: { event: 'terminal', job_id: 'job-a', attempt_id: 'attempt-b', ok: true } })
    expect(await screen.findByTestId('review')).toHaveTextContent('20260818-155237-c6b118')
  })

  it('routes zero recommendations as successful analysis', async () => {
    mocks.api.jobResults.mockResolvedValueOnce({
      job_id: 'job-no-recommendations',
      outcome: 'SUCCESS_NO_RECOMMENDATIONS',
      score: { clips: [], scored_count: 5 },
      render: null,
    })
    render(<App />)
    await waitFor(() => expect(mocks.pipelineHandler).toBeDefined())
    mocks.pipelineHandler?.({ payload: { event: 'job', job_id: 'job-no-recommendations', attempt_id: 'attempt-no-recommendations' } })
    mocks.pipelineHandler?.({
      payload: {
        event: 'terminal',
        job_id: 'job-no-recommendations',
        attempt_id: 'attempt-no-recommendations',
        ok: true,
        code: 'NO_RECOMMENDED_CLIPS',
        message: 'We analyzed this video but did not find a moment that met ClipGauge\'s quality bar.',
      },
    })
    expect(await screen.findByTestId('review')).toHaveTextContent('job-no-recommendations')
  })

  it('surfaces rejected resume actions instead of silently staying busy', async () => {
    mocks.api.resumeJob.mockRejectedValueOnce(new Error('resume rejected'))
    render(<App />)
    await userEvent.click(await screen.findByTestId('resume-job'))
    expect(await screen.findByTestId('studio-error')).toHaveTextContent('The session could not be resumed. Retry the job.')
    expect(screen.getByTestId('studio-state')).toHaveTextContent('FAILED')
  })
})

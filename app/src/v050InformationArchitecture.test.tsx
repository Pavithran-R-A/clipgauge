import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProviderCenter from './components/ProviderCenter'
import SetupCenter from './components/SetupCenter'

const mocks = vi.hoisted(() => ({
  setupState: vi.fn(),
  setupInventory: vi.fn(),
  saveLocalModel: vi.fn(),
  youtubeReadiness: vi.fn(),
  setupToolYouTubeTest: vi.fn(),
  startSetup: vi.fn(),
  cancelSetup: vi.fn(),
  gpuDiagnostics: vi.fn(),
  repairGpu: vi.fn(),
  storagePreview: vi.fn(),
  storageCleanup: vi.fn(),
  saveProviderKey: vi.fn(),
  removeProviderKey: vi.fn(),
  listProviderModels: vi.fn(),
  testConnection: vi.fn(),
  listen: vi.fn()
}))

vi.mock('./api', () => ({ api: mocks }))
vi.mock('@tauri-apps/api/event', () => ({ listen: mocks.listen }))
vi.mock('@tauri-apps/plugin-dialog', () => ({ confirm: (message: string) => window.confirm(message) }))

beforeEach(() => {
  vi.clearAllMocks()
  const localValues = new Map<string, string>()
  Object.defineProperty(window, 'localStorage', { configurable: true, value: {
    getItem: (key: string) => localValues.get(key) ?? null,
    setItem: (key: string, value: string) => { localValues.set(key, value) },
    removeItem: (key: string) => { localValues.delete(key) }
  } })
  mocks.setupState.mockResolvedValue({ has_gemini_key: false, onboarded: true, provider_keys: { openrouter: true } })
  mocks.setupInventory.mockResolvedValue({
    state: 'setup-required',
    video_tools: { ready: true, source: 'system', executable: '/usr/bin/ffmpeg', version: 'ffmpeg version test', capabilities: { starts: true, subtitles: true }, managed_download_needed: false, reason: 'Compatible caption-capable FFmpeg.' },
    local_ai: { state: 'model-download-required', runtime_ready: true, model_ready: false, selected_model_id: 'clipgauge-local/balanced', required_bytes: 2300000000, action: 'Download Balanced' },
    runtime: { installed: true },
    models: [
      { asset_id: 'clipgauge-local/light', display_name: 'Lightweight', size_bytes: 0 },
      { asset_id: 'clipgauge-local/balanced', display_name: 'Balanced', size_bytes: 2300000000 }
    ],
    core_assets: [],
    managed_assets: [
      { asset_id: 'runtime:ffmpeg:test', display_name: 'FFmpeg', purpose: 'Video tools', size_bytes: 0, installed: true, source: 'system', status: 'reused-system', license: 'LGPL' },
      { asset_id: 'model:asr:test', display_name: 'Speech', purpose: 'Speech recognition', size_bytes: 1800000000, installed: false, license: 'MIT' },
      { asset_id: 'model:panns:test', display_name: 'Audio analysis', purpose: 'Audio analysis', size_bytes: 1, installed: true, license: 'MIT' }
    ],
    storage: { required_bytes: 1800000000, installed_bytes: 1000000, available_bytes: null, assets: [], consent_required: true },
    catalog: []
  })
  mocks.youtubeReadiness.mockResolvedValue({ state: 'DEPENDENCIES_READY', ready: true, public_download_verified: false, reason: 'YouTube tools are ready.', actions: ['Test'], checks: [] })
  mocks.setupToolYouTubeTest.mockResolvedValue({ state: 'DEPENDENCIES_READY', ready: true, public_download_verified: false, reason: 'YouTube tools are ready.', actions: ['Test'], checks: [] })
  mocks.gpuDiagnostics.mockResolvedValue({
    environment: { state: 'READY' },
    hardware: { nvidia: { verified: false, gpus: [] }, cuda_ctranslate2: { verified: false, compute_types: [] }, pytorch_cuda: { verified: false } },
    cuda_runtime_ready: true,
    cudnn_runtime_ready: true
  })
  mocks.repairGpu.mockResolvedValue({ ok: true })
  mocks.listProviderModels.mockResolvedValue({ state: 'PASS', provider: 'openrouter', models: [] })
  mocks.listen.mockResolvedValue(() => undefined)
})

describe('v0.5 information architecture', () => {
  it('surfaces setup progress listener failures', async () => {
    mocks.listen.mockRejectedValueOnce(new Error('setup bridge unavailable'))
    render(<SetupCenter onBack={vi.fn()} />)

    expect(await screen.findByText(/Setup progress events are unavailable\. Restart ClipGauge and retry\./)).toBeInTheDocument()
  })

  it('keeps every supported provider discoverable in Provider Center', async () => {
    render(<ProviderCenter selectedProvider="clipgauge-local" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('Custom OpenAI-compatible')).toBeInTheDocument())
    for (const name of ['ClipGauge Local', 'OpenRouter Free', 'Gemini', 'Groq', 'Cloudflare Workers AI', 'Hugging Face', 'Cerebras', 'Ollama', 'LM Studio']) {
      expect(screen.getAllByText(name).length).toBeGreaterThan(0)
    }
  })

  it('follows a provider selection changed by the parent', async () => {
    const view = render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: 'Groq' })).toBeInTheDocument()

    view.rerender(<ProviderCenter selectedProvider="gemini" onSelectProvider={vi.fn()} onBack={vi.fn()} />)

    expect(await screen.findByRole('heading', { name: 'Gemini' })).toBeInTheDocument()
  })

  it('renders cached provider inventory before native refresh completes', () => {
    window.localStorage.setItem('clipgauge.setup.inventory.v1', JSON.stringify({
      schema_version: 1,
      app_version: '0.5.16',
      platform: 'windows-x86_64',
      runtime_manifest_digest: 'manifest-a',
      last_verified_at: 1_700_000_000,
      value: {
        state: 'ready',
        local_ai: { state: 'ready', runtime_ready: true, model_ready: true, selected_model_id: 'clipgauge-local/balanced', required_bytes: 0, action: 'Ready' },
        models: [{ asset_id: 'clipgauge-local/balanced' }],
        runtime: {},
        core_assets: [],
        storage: {},
        catalog: []
      }
    }))
    mocks.setupInventory.mockImplementation(() => new Promise(() => undefined))

    render(<ProviderCenter selectedProvider="clipgauge-local" onSelectProvider={vi.fn()} onBack={vi.fn()} />)

    expect(screen.getAllByText('Ready').length).toBeGreaterThan(0)
  })

  it('persists a verified provider inventory refresh for the next launch', async () => {
    const setItem = vi.fn()
    Object.defineProperty(window, 'localStorage', { configurable: true, value: {
      getItem: vi.fn(() => null),
      setItem,
      removeItem: vi.fn(),
    } })
    mocks.setupInventory.mockResolvedValue({
      state: 'ready',
      platform: 'windows-x86_64',
      runtime_manifest_digest: 'manifest-a',
      runtime: {},
      models: [],
      core_assets: [],
      managed_assets: [],
      storage: {},
      catalog: [],
    })

    render(<ProviderCenter selectedProvider="clipgauge-local" onSelectProvider={vi.fn()} onBack={vi.fn()} />)

    await waitFor(() => expect(setItem).toHaveBeenCalledWith('clipgauge.setup.inventory.v1', expect.any(String)))
  })

  it('keeps cached provider readiness when native refresh fails', async () => {
    window.localStorage.setItem('clipgauge.setup.inventory.v1', JSON.stringify({
      schema_version: 1,
      app_version: '0.5.16',
      platform: 'windows-x86_64',
      runtime_manifest_digest: 'manifest-a',
      last_verified_at: 1_700_000_000,
      value: {
        state: 'ready',
        local_ai: { state: 'ready', runtime_ready: true, model_ready: true, selected_model_id: 'clipgauge-local/balanced', required_bytes: 0, action: 'Ready' },
        models: [{ asset_id: 'clipgauge-local/balanced' }],
        runtime: {},
        core_assets: [],
        storage: {},
        catalog: []
      }
    }))
    mocks.setupInventory.mockRejectedValueOnce(new Error('native refresh unavailable'))

    render(<ProviderCenter selectedProvider="clipgauge-local" onSelectProvider={vi.fn()} onBack={vi.fn()} />)

    await waitFor(() => expect(mocks.setupInventory).toHaveBeenCalled())
    expect(screen.getAllByText('Ready').length).toBeGreaterThan(0)
  })

  it('uses grouped setup language and treats a capable system FFmpeg as ready without managed bytes', async () => {
    render(<SetupCenter onBack={vi.fn()} />)
    expect(await screen.findByText('Ready · System')).toBeInTheDocument()
    expect(screen.getByText('Speech recognition')).toBeInTheDocument()
    expect(screen.getAllByText('Size calculated during setup').length).toBeGreaterThan(0)
    expect(screen.queryByText('0 B download')).not.toBeInTheDocument()
    expect(screen.getByText('Optional local AI')).toBeInTheDocument()
    expect(screen.getAllByText('Download Balanced').length).toBeGreaterThan(0)
  })

  it('surfaces local model persistence failures', async () => {
    mocks.saveLocalModel.mockRejectedValueOnce(new Error('vault unavailable'))
    render(<SetupCenter onBack={vi.fn()} />)

    await screen.findByText('Choose one model')
    await userEvent.click(screen.getByRole('radio', { name: /Lightweight/ }))

    expect(await screen.findByText('Local model choice could not be saved. Retry before installing.')).toBeInTheDocument()
  })

  it('ignores stale local model persistence failures', async () => {
    let rejectFirst: (reason?: unknown) => void = () => undefined
    const firstSave = new Promise<void>((_, reject) => { rejectFirst = reject })
    mocks.saveLocalModel.mockReturnValueOnce(firstSave).mockResolvedValueOnce(undefined)
    render(<SetupCenter onBack={vi.fn()} />)

    await screen.findByText('Choose one model')
    await userEvent.click(screen.getByRole('radio', { name: /Lightweight/ }))
    await userEvent.click(screen.getByRole('radio', { name: /Balanced/ }))
    await act(async () => { rejectFirst(new Error('stale vault failure')) })

    expect(screen.queryByText('Local model choice could not be saved. Retry before installing.')).not.toBeInTheDocument()
  })

  it('clears the active progress tray after successful setup termination', async () => {
    const handlers: Array<(event: { payload: Record<string, unknown> }) => void> = []
    mocks.listen.mockImplementation(async (_event: string, handler: (event: { payload: Record<string, unknown> }) => void) => { handlers.push(handler); return () => undefined })
    render(<SetupCenter onBack={vi.fn()} />)
    expect(await screen.findByText('Video tools')).toBeInTheDocument()
    await act(async () => { handlers[0]?.({ payload: { event: 'terminal', ok: true, code: 'OK', message: 'Setup complete.' } }) })
    expect(screen.queryByText('Download progress')).not.toBeInTheDocument()
  })

  it('keeps a failed component retryable without a live timer', async () => {
    const handlers: Array<(event: { payload: Record<string, unknown> }) => void> = []
    mocks.listen.mockImplementation(async (_event: string, handler: (event: { payload: Record<string, unknown> }) => void) => { handlers.push(handler); return () => undefined })
    render(<SetupCenter onBack={vi.fn()} />)
    expect(await screen.findByText('Video tools')).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText(/I approve these one-time downloads/i))
    await userEvent.click(screen.getByRole('button', { name: /Install required components/i }))
    await act(async () => { handlers[0]?.({ payload: { event: 'terminal', ok: false, code: 'SETUP_FAILED', message: 'Component failed.' } }) })
    expect(screen.getByRole('button', { name: /Retry component/i })).toBeInTheDocument()
  })

  it('recovers when setup returns an invalid operation id', async () => {
    mocks.startSetup.mockResolvedValueOnce(null)
    render(<SetupCenter onBack={vi.fn()} />)
    await screen.findByText('Video tools')
    await userEvent.click(screen.getByLabelText(/I approve these one-time downloads/i))
    await userEvent.click(screen.getByRole('button', { name: /Install required components/i }))

    expect(await screen.findByText('Setup could not start. Retry the setup.')).toBeInTheDocument()
  })

  it('recovers from malformed cleanup preview data', async () => {
    mocks.storagePreview.mockResolvedValueOnce({ paths: 'invalid' })
    render(<SetupCenter onBack={vi.fn()} />)
    await screen.findByText('Video tools')
    await userEvent.click(screen.getByRole('button', { name: 'Clear safe cache' }))

    expect(await screen.findByText('Cleanup could not run: Setup information is temporarily unavailable.')).toBeInTheDocument()
  })

  it('retains the last verified GPU state when refresh fails', async () => {
    const verified = {
      environment: { state: 'READY' },
      hardware: {
        nvidia: { available: true, verified: true, gpus: [{ name: 'Test GPU', driver: '1.0' }] },
        cuda_ctranslate2: { available: true, verified: true, compute_types: ['float16'] },
        pytorch_cuda: { available: true, verified: true, compiled_cuda: '12.4' }
      },
      cuda_runtime_ready: true,
      cudnn_runtime_ready: true
    }
    mocks.gpuDiagnostics.mockResolvedValueOnce(verified).mockRejectedValueOnce(new Error('probe unavailable'))
    render(<SetupCenter onBack={vi.fn()} />)
    expect((await screen.findAllByText('READY')).length).toBeGreaterThan(0)
    await userEvent.click(screen.getByRole('button', { name: 'Refresh diagnostics' }))
    expect(await screen.findByText(/using last verified state/i)).toBeInTheDocument()
    expect(screen.getAllByText('READY').length).toBeGreaterThan(0)
  })

  it('keeps first-time GPU probe failure optional and CPU-safe', async () => {
    mocks.gpuDiagnostics.mockRejectedValueOnce(new Error('probe unavailable'))
    render(<SetupCenter onBack={vi.fn()} />)

    expect(await screen.findByText(/GPU diagnostics unavailable\. CPU processing remains available\./i)).toBeInTheDocument()
    expect(screen.getByText('UNAVAILABLE', { exact: true })).toHaveClass('tone-neutral')
    expect(screen.getByText(/GPU diagnostics unavailable\. CPU processing remains available\./i)).toHaveAttribute('role', 'status')
    expect(screen.queryByText('PROBE_FAILED')).not.toBeInTheDocument()
  })

  it('recovers from malformed fresh GPU diagnostics', async () => {
    mocks.gpuDiagnostics.mockResolvedValueOnce({ hardware: { nvidia: { gpus: 'invalid' } } })
    render(<SetupCenter onBack={vi.fn()} />)

    expect(await screen.findByText(/GPU diagnostics unavailable\. CPU processing remains available\./i)).toBeInTheDocument()
  })

  it('keeps optional GPU details collapsed by default', async () => {
    render(<SetupCenter onBack={vi.fn()} />)
    expect(await screen.findByText('GPU diagnostics')).toBeInTheDocument()
    const details = screen.getByText('Show GPU details').closest('details')
    expect(details).not.toHaveAttribute('open')
  })

  it('makes critical storage prominent and pauses setup downloads', async () => {
    mocks.setupInventory.mockResolvedValue({
      state: 'setup-required',
      runtime: {},
      models: [],
      core_assets: [],
      storage: { required_bytes: 2 * 1024 ** 3, installed_bytes: 0, available_bytes: 700 * 1024 ** 2 },
      catalog: []
    })
    render(<SetupCenter onBack={vi.fn()} />)
    expect(await screen.findByText('Critical free space')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Install required components/i })).toBeDisabled()
  })

  it('pauses optional downloads during critical storage conditions', async () => {
    mocks.setupInventory.mockResolvedValue({
      state: 'setup-required',
      video_tools: { ready: true, source: 'system', managed_download_needed: false },
      local_ai: { state: 'model-download-required', runtime_ready: true, model_ready: false, selected_model_id: 'clipgauge-local/balanced', required_bytes: 2 * 1024 ** 3, action: 'Download Balanced' },
      runtime: { installed: true },
      models: [{ asset_id: 'clipgauge-local/balanced', display_name: 'Balanced', size_bytes: 2 * 1024 ** 3 }],
      core_assets: [],
      managed_assets: [],
      storage: { required_bytes: 2 * 1024 ** 3, installed_bytes: 0, available_bytes: 700 * 1024 ** 2 },
      catalog: []
    })
    mocks.youtubeReadiness.mockResolvedValue({ state: 'DEPENDENCIES_READY', ready: true, reason: 'Support needs installation.', actions: ['Install'], checks: [] })

    render(<SetupCenter onBack={vi.fn()} />)

    expect(await screen.findByText('Critical free space')).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText(/I approve this optional local-AI download/i))
    expect(screen.getByRole('button', { name: 'Download Balanced' })).toBeDisabled()
    await userEvent.click(screen.getByLabelText(/I approve YouTube support installation/i))
    expect(await screen.findByRole('button', { name: 'Install YouTube support' })).toBeDisabled()
  })

  it('uses cached YouTube readiness without retesting on setup mount', async () => {
    window.localStorage.setItem('clipgauge.setup.youtube.v1', JSON.stringify({
      schema_version: 1,
      app_version: '0.5.16',
      value: { state: 'DEPENDENCIES_READY', ready: true, reason: 'Cached tools are ready.', actions: ['Test'], checks: [] },
      verifiedAt: new Date(Date.now() - 1000).toISOString()
    }))
    render(<SetupCenter onBack={vi.fn()} />)
    expect(await screen.findByText(/Last public compatibility test/i)).toBeInTheDocument()
    expect(mocks.youtubeReadiness).not.toHaveBeenCalled()
  })

  it('keeps cached YouTube actions when a manual test fails', async () => {
    window.localStorage.setItem('clipgauge.setup.youtube.v1', JSON.stringify({
      schema_version: 1,
      app_version: '0.5.16',
      value: { state: 'DEPENDENCIES_READY', ready: true, reason: 'Cached YouTube support needs installation.', actions: ['Install'], checks: [] },
      verifiedAt: new Date().toISOString()
    }))
    mocks.setupToolYouTubeTest.mockRejectedValueOnce(new Error('compatibility probe unavailable'))
    render(<SetupCenter onBack={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Install YouTube support' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Test YouTube support' }))
    await waitFor(() => expect(mocks.setupToolYouTubeTest).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: 'Install YouTube support' })).toBeInTheDocument()
  })

  it('does not trust YouTube readiness cached by another app version', async () => {
    const current = { state: 'DEPENDENCIES_READY', ready: true, reason: 'Current tools are ready.', actions: ['Test'], checks: [] }
    window.localStorage.setItem('clipgauge.setup.youtube.v1', JSON.stringify({
      schema_version: 1,
      app_version: '0.5.15',
      value: current,
      verifiedAt: new Date().toISOString()
    }))
    mocks.youtubeReadiness.mockResolvedValue(current)
    render(<SetupCenter onBack={vi.fn()} />)
    await waitFor(() => expect(mocks.youtubeReadiness).toHaveBeenCalled())
  })

  it('uses fresh cached GPU diagnostics until explicitly refreshed', () => {
    const cachedGpu = {
      environment: { state: 'READY' },
      hardware: { nvidia: { available: true, verified: true, gpus: [{ name: 'Cached GPU', driver: '1.0' }] }, cuda_ctranslate2: { available: true, verified: true, compute_types: ['float16'] }, pytorch_cuda: { available: true, verified: true, compiled_cuda: '12.4' } },
      cuda_runtime_ready: true,
      cudnn_runtime_ready: true
    }
    window.localStorage.setItem('clipgauge.setup.gpu.v1', JSON.stringify({ schema_version: 1, app_version: '0.5.16', identity: { gpu_identity: ['Cached GPU'], driver_version: ['1.0'], cuda_runtime_fingerprint: '{}', cudnn_runtime_fingerprint: '{}', pipeline_environment_fingerprint: null }, value: cachedGpu, verifiedAt: new Date().toISOString() }))
    mocks.gpuDiagnostics.mockImplementation(() => new Promise(() => undefined))
    render(<SetupCenter onBack={vi.fn()} />)
    expect(screen.getByText('Cached GPU')).toBeInTheDocument()
    expect(mocks.gpuDiagnostics).not.toHaveBeenCalled()
  })

  it('does not trust GPU diagnostics cached by another app version', async () => {
    const cachedGpu = {
      environment: { state: 'READY' },
      hardware: { nvidia: { available: true, verified: true, gpus: [{ name: 'Old GPU', driver: '1.0' }] } },
      cuda_runtime_ready: true,
      cudnn_runtime_ready: true
    }
    window.localStorage.setItem('clipgauge.setup.gpu.v1', JSON.stringify({
      schema_version: 1,
      app_version: '0.5.15',
      value: cachedGpu,
      verifiedAt: new Date().toISOString()
    }))
    mocks.gpuDiagnostics.mockResolvedValue(cachedGpu)
    render(<SetupCenter onBack={vi.fn()} />)
    await waitFor(() => expect(mocks.gpuDiagnostics).toHaveBeenCalled())
  })

  it('persists GPU identity and runtime fingerprints with fresh diagnostics', async () => {
    mocks.gpuDiagnostics.mockResolvedValue({
      environment: { state: 'READY', expected_fingerprint: 'environment-a' },
      hardware: {
        nvidia: { available: true, verified: true, gpus: [{ name: 'Test GPU', driver: '555.1' }] },
        cuda_ctranslate2: { available: true, verified: true, device_count: 1, compute_types: ['float16'] }
      },
      cuda_runtime_ready: true,
      cudnn_runtime_ready: true
    })
    render(<SetupCenter onBack={vi.fn()} />)
    await waitFor(() => expect(mocks.gpuDiagnostics).toHaveBeenCalled())

    const cached = JSON.parse(window.localStorage.getItem('clipgauge.setup.gpu.v1') ?? '{}')
    expect(cached.schema_version).toBe(1)
    expect(cached.app_version).toBe('0.5.16')
    expect(cached.identity).toMatchObject({
      gpu_identity: ['Test GPU'],
      driver_version: ['555.1'],
      pipeline_environment_fingerprint: 'environment-a'
    })
    expect(typeof cached.identity.cuda_runtime_fingerprint).toBe('string')
    expect(typeof cached.identity.cudnn_runtime_fingerprint).toBe('string')
  })

  it('renders cached setup inventory before the native refresh completes', () => {
    window.localStorage.setItem('clipgauge.setup.inventory.v1', JSON.stringify({
      schema_version: 1,
      app_version: '0.5.16',
      platform: 'windows-x86_64',
      runtime_manifest_digest: 'cached-manifest',
      last_verified_at: Date.now() / 1000 - 60,
      value: {
      state: 'ready',
      video_tools: { ready: true, source: 'system', capabilities: { starts: true, subtitles: true }, managed_download_needed: false, reason: 'Cached video tools.' },
      local_ai: { state: 'ready', runtime_ready: true, model_ready: true, selected_model_id: 'clipgauge-local/light' },
      runtime: { installed: true },
      models: [],
      core_assets: [],
      managed_assets: [],
      storage: { required_bytes: 0, installed_bytes: 1, available_bytes: 1, breakdown: [] },
      catalog: []
      }
    }))
    mocks.setupInventory.mockImplementation(() => new Promise(() => undefined))
    render(<SetupCenter onBack={vi.fn()} />)
    expect(screen.getByText('Ready · System')).toBeInTheDocument()
    expect(screen.getByText('ClipGauge Local is ready')).toBeInTheDocument()
    expect(screen.getByText(/Last verified:/)).toBeInTheDocument()
  })

  it('does not trust setup inventory cached by another app version', async () => {
    window.localStorage.setItem('clipgauge.setup.inventory.v1', JSON.stringify({
      schema_version: 1,
      app_version: '0.5.15',
      platform: 'windows-x86_64',
      runtime_manifest_digest: 'old-manifest',
      last_verified_at: Date.now() / 1000,
      value: { state: 'ready', runtime: {}, models: [], core_assets: [], storage: {}, catalog: [] }
    }))
    render(<SetupCenter onBack={vi.fn()} />)

    expect(await screen.findByText('Ready · System')).toBeInTheDocument()
    expect(mocks.setupInventory).toHaveBeenCalled()
  })

  it('ignores malformed cached setup inventory', async () => {
    window.localStorage.setItem('clipgauge.setup.inventory.v1', JSON.stringify({ managed_assets: {} }))
    render(<SetupCenter onBack={vi.fn()} />)

    expect(await screen.findByText('Video tools')).toBeInTheDocument()
    expect(mocks.setupInventory).toHaveBeenCalled()
  })

  it('ignores cached inventory with malformed storage breakdown rows', async () => {
    window.localStorage.setItem('clipgauge.setup.inventory.v1', JSON.stringify({
      schema_version: 1,
      app_version: '0.5.16',
      platform: 'windows-x86_64',
      runtime_manifest_digest: 'manifest-a',
      last_verified_at: Date.now() / 1000,
      value: { state: 'ready', runtime: {}, models: [], core_assets: [], managed_assets: [], storage: { required_bytes: 0, installed_bytes: 0, available_bytes: 1, breakdown: [null] }, catalog: [] }
    }))
    render(<SetupCenter onBack={vi.fn()} />)

    expect(await screen.findByText('Video tools')).toBeInTheDocument()
    expect(mocks.setupInventory).toHaveBeenCalled()
  })

  it('ignores cached inventory with managed assets missing identifiers', async () => {
    window.localStorage.setItem('clipgauge.setup.inventory.v1', JSON.stringify({
      schema_version: 1,
      app_version: '0.5.16',
      platform: 'windows-x86_64',
      runtime_manifest_digest: 'manifest-a',
      last_verified_at: Date.now() / 1000,
      value: { state: 'ready', runtime: {}, models: [], core_assets: [], managed_assets: [{}], storage: {}, catalog: [] }
    }))
    render(<SetupCenter onBack={vi.fn()} />)

    expect(await screen.findByText('Video tools')).toBeInTheDocument()
    expect(mocks.setupInventory).toHaveBeenCalled()
  })

  it('ignores malformed nested cached diagnostics', async () => {
    window.localStorage.setItem('clipgauge.setup.gpu.v1', JSON.stringify({
      value: { hardware: { cuda_ctranslate2: { compute_types: {} } } },
      verifiedAt: new Date().toISOString()
    }))
    window.localStorage.setItem('clipgauge.setup.youtube.v1', JSON.stringify({
      value: { state: 'DEPENDENCIES_READY', ready: true, actions: {} },
      verifiedAt: new Date().toISOString()
    }))
    render(<SetupCenter onBack={vi.fn()} />)

    expect(await screen.findByText('Video tools')).toBeInTheDocument()
  })

  it('ignores malformed nested cached inventory rows', async () => {
    window.localStorage.setItem('clipgauge.setup.inventory.v1', JSON.stringify({
      state: 'ready',
      runtime: {},
      models: [null],
      core_assets: [],
      managed_assets: [],
      storage: { breakdown: [null] },
      catalog: []
    }))
    render(<SetupCenter onBack={vi.fn()} />)

    expect(await screen.findByText('Video tools')).toBeInTheDocument()
  })

  it('offers saved sessions through a picker', async () => {
    render(<SetupCenter jobs={[{ id: 'job-1', title: 'Landing review', ingested: true, rendered: false }]} onBack={vi.fn()} />)
    expect(await screen.findByRole('option', { name: 'Landing review — job-1' })).toBeInTheDocument()
  })


  it('keeps raw session IDs out of the primary cleanup UI', async () => {
    render(<SetupCenter jobs={[{ id: 'job-1', title: 'Landing review', ingested: true, rendered: false }]} onBack={vi.fn()} />)
    expect(await screen.findByRole('combobox', { name: 'Session' })).toBeVisible()
    expect(screen.queryByPlaceholderText('20260818-155237-c6b118')).not.toBeInTheDocument()
  })

  it('shows saved provider credentials as unverified and supports removal', async () => {
    const confirm = vi.fn(async () => true)
    vi.stubGlobal('confirm', confirm)
    mocks.removeProviderKey.mockResolvedValue(true)
    render(<ProviderCenter selectedProvider="openrouter" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    expect((await screen.findAllByText('Credential saved')).length).toBeGreaterThan(0)
    expect(await screen.findByText('API key saved in your operating-system credential vault.')).toBeInTheDocument()
    mocks.testConnection.mockResolvedValue({ state: 'PASS', provider: 'openrouter', message: 'Verified.' })
    await userEvent.click(screen.getByRole('button', { name: /Test connection/i }))
    expect((await screen.findAllByText('Connected')).length).toBeGreaterThan(0)
    const remove = await screen.findByRole('button', { name: 'Remove' })
    await userEvent.click(remove)
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('does not revoke the provider key'))
    await waitFor(() => expect(mocks.removeProviderKey).toHaveBeenCalledWith('preset-openrouter'))
    vi.unstubAllGlobals()
  })

  it('does not claim a provider credential was saved when native storage returns false', async () => {
    mocks.saveProviderKey.mockResolvedValue(false)
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)

    const credential = await screen.findByLabelText('API key')
    await userEvent.type(credential, 'rejected-key')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText(/credential could not be saved/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Saved' })).not.toBeInTheDocument()
  })

  it('does not apply a stale credential save after switching providers', async () => {
    let resolveSave: (value: boolean) => void = () => undefined
    mocks.saveProviderKey.mockImplementationOnce(() => new Promise((resolve) => { resolveSave = resolve }))
    render(<ProviderCenter selectedProvider="openrouter" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    const credential = await screen.findByLabelText('API key')
    await userEvent.type(credential, 'pending-key')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await userEvent.click(screen.getByRole('button', { name: /Groq/ }))
    resolveSave(true)
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(screen.queryByRole('button', { name: 'Saved' })).not.toBeInTheDocument()
    expect(screen.queryByText('API key saved in your operating-system credential vault.')).not.toBeInTheDocument()
  })

  it('waits for asynchronous credential-removal confirmation before removing', async () => {
    let resolveConfirm: (value: boolean) => void = () => undefined
    const confirmation = new Promise<boolean>((resolve) => { resolveConfirm = resolve })
    const confirm = vi.fn(() => confirmation)
    vi.stubGlobal('confirm', confirm)
    mocks.removeProviderKey.mockResolvedValue(true)
    render(<ProviderCenter selectedProvider="openrouter" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    expect((await screen.findAllByText('Credential saved')).length).toBeGreaterThan(0)
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))
    expect(mocks.removeProviderKey).not.toHaveBeenCalled()
    resolveConfirm(true)
    await waitFor(() => expect(mocks.removeProviderKey).toHaveBeenCalledWith('preset-openrouter'))
    vi.unstubAllGlobals()
  })

  it('surfaces credential-removal confirmation failures', async () => {
    vi.stubGlobal('confirm', vi.fn(() => Promise.reject(new Error('confirmation unavailable'))))
    render(<ProviderCenter selectedProvider="openrouter" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    expect((await screen.findAllByText('Credential saved')).length).toBeGreaterThan(0)
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))
    expect(await screen.findByText(/credential could not be removed/)).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('shows a migrated Gemini credential as saved until a real connection test passes', async () => {
    mocks.setupState.mockResolvedValue({ has_gemini_key: true, onboarded: true, provider_keys: {} })
    render(<ProviderCenter selectedProvider="gemini" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    expect((await screen.findAllByText('Credential saved')).length).toBeGreaterThan(0)
    expect(screen.queryByText('Connected')).not.toBeInTheDocument()
    mocks.testConnection.mockResolvedValue({ state: 'FAIL', provider: 'gemini', message: 'Rejected.' })
    await userEvent.click(screen.getByRole('button', { name: /Test connection/i }))
    expect((await screen.findAllByText('Connection failed')).length).toBeGreaterThan(0)
  })

  it('shows typed provider status after a rate limit', async () => {
    mocks.testConnection.mockResolvedValue({ state: 'FAIL', provider: 'groq', code: 'RATE_LIMITED', message: 'Try again later.' })
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Test connection' }))

    expect((await screen.findAllByText('Rate limited')).length).toBeGreaterThan(0)
    expect(screen.getByText('Try again later.')).toBeInTheDocument()
  })

  it('shows Testing while the connection request is pending', async () => {
    let resolveTest: (value: { state: 'PASS'; provider: string }) => void = () => undefined
    mocks.testConnection.mockImplementation(() => new Promise((resolve) => { resolveTest = resolve }))
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Test connection' }))

    expect((await screen.findAllByText('Testing')).length).toBeGreaterThan(0)
    resolveTest({ state: 'PASS', provider: 'groq' })
  })

  it('shows an actionable status for typed provider failures', async () => {
    mocks.testConnection.mockResolvedValue({
      state: 'FAIL',
      provider: 'groq',
      code: 'VISION_UNSUPPORTED',
      message: 'The selected model does not support vision.'
    })
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Test connection' }))

    expect((await screen.findAllByText('Vision unsupported')).length).toBeGreaterThan(0)
  })

  it('tests the exact selected local model identity', async () => {
    mocks.setupInventory.mockResolvedValue({
      local_ai: { state: 'ready', runtime_ready: true, model_ready: true, selected_model_id: 'clipgauge-local/light' },
      models: [
        { asset_id: 'clipgauge-local/light', display_name: 'Lightweight', size_bytes: 1 },
        { asset_id: 'clipgauge-local/balanced', display_name: 'Balanced', size_bytes: 2 }
      ]
    })
    mocks.testConnection.mockResolvedValue({ state: 'PASS', provider: 'clipgauge-local', message: 'Verified.' })
    render(<ProviderCenter selectedProvider="clipgauge-local" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: /Test connection/i }))
    await waitFor(() => expect(mocks.testConnection).toHaveBeenCalledWith('clipgauge-local', 'clipgauge-local/light', 'http://127.0.0.1:8080/v1', 'none'))
  })

  it('refreshes and persists a compatible provider model selection', async () => {
    const storedModels = new Map<string, string>()
    const storage = {
      getItem: vi.fn((key: string) => storedModels.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => { storedModels.set(key, value) })
    }
    Object.defineProperty(window, 'localStorage', { configurable: true, value: storage })
    mocks.listProviderModels.mockResolvedValue({
      state: 'PASS',
      provider: 'groq',
      models: [
        { id: 'openai/gpt-oss-20b', compatibility: 'FULL' },
        { id: 'qwen/qwen3-32b', compatibility: 'TEXT-ONLY' }
      ]
    })
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Refresh models' }))
    expect(await screen.findByRole('option', { name: 'openai/gpt-oss-20b — FULL' })).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Model' }), 'qwen/qwen3-32b')
    expect(storage.setItem).toHaveBeenCalledWith('clipgauge.provider-model.groq', 'qwen/qwen3-32b')
  })

  it('persists a local provider model selection through native setup state', async () => {
    mocks.setupInventory.mockResolvedValue({
      state: 'ready',
      local_ai: { state: 'ready', runtime_ready: true, model_ready: true, selected_model_id: 'clipgauge-local/balanced', required_bytes: 0, action: 'Ready' },
      models: [
        { asset_id: 'clipgauge-local/light', display_name: 'Lightweight', size_bytes: 1 },
        { asset_id: 'clipgauge-local/balanced', display_name: 'Balanced', size_bytes: 2 }
      ],
      runtime: {},
      core_assets: [],
      storage: {},
      catalog: []
    })
    mocks.listProviderModels.mockResolvedValue({
      state: 'PASS',
      provider: 'clipgauge-local',
      models: [
        { id: 'clipgauge-local/light', compatibility: 'FULL' },
        { id: 'clipgauge-local/balanced', compatibility: 'FULL' }
      ]
    })
    mocks.saveLocalModel.mockResolvedValue(undefined)
    const onSelectLocalModel = vi.fn()
    render(<ProviderCenter selectedProvider="clipgauge-local" onSelectProvider={vi.fn()} onSelectLocalModel={onSelectLocalModel} onBack={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Refresh models' }))
    const modelPicker = screen.getByRole('combobox', { name: 'Model' })
    await userEvent.selectOptions(modelPicker, 'clipgauge-local/light')

    expect(modelPicker).toHaveValue('clipgauge-local/light')
    await waitFor(() => expect(mocks.saveLocalModel).toHaveBeenCalledWith('clipgauge-local/light'))
    expect(onSelectLocalModel).toHaveBeenCalledWith('clipgauge-local/light')
    await userEvent.click(screen.getByText('Advanced settings'))
    expect(screen.getByText('clipgauge-local/light', { selector: 'code' })).toBeInTheDocument()
  })

  it('does not notify the parent after local model save unmounts', async () => {
    mocks.setupInventory.mockResolvedValue({
      state: 'ready',
      local_ai: { state: 'ready', runtime_ready: true, model_ready: true, selected_model_id: 'clipgauge-local/balanced', required_bytes: 0, action: 'Ready' },
      models: [
        { asset_id: 'clipgauge-local/light', display_name: 'Lightweight', size_bytes: 1 },
        { asset_id: 'clipgauge-local/balanced', display_name: 'Balanced', size_bytes: 2 }
      ],
      runtime: {},
      core_assets: [],
      storage: {},
      catalog: []
    })
    mocks.listProviderModels.mockResolvedValue({
      state: 'PASS',
      provider: 'clipgauge-local',
      models: [
        { id: 'clipgauge-local/light', compatibility: 'FULL' },
        { id: 'clipgauge-local/balanced', compatibility: 'FULL' }
      ]
    })
    let resolveSave: (() => void) | undefined
    mocks.saveLocalModel.mockImplementation(() => new Promise<void>((resolve) => { resolveSave = resolve }))
    const onSelectLocalModel = vi.fn()
    const view = render(<ProviderCenter selectedProvider="clipgauge-local" onSelectProvider={vi.fn()} onSelectLocalModel={onSelectLocalModel} onBack={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Refresh models' }))
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Model' }), 'clipgauge-local/light')
    view.unmount()

    await act(async () => {
      resolveSave?.()
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    expect(onSelectLocalModel).not.toHaveBeenCalled()
  })

  it('serializes rapid local model changes in selection order', async () => {
    mocks.setupInventory.mockResolvedValue({
      state: 'ready',
      local_ai: { state: 'ready', runtime_ready: true, model_ready: true, selected_model_id: 'clipgauge-local/balanced', required_bytes: 0, action: 'Ready' },
      models: [
        { asset_id: 'clipgauge-local/light', display_name: 'Lightweight', size_bytes: 1 },
        { asset_id: 'clipgauge-local/balanced', display_name: 'Balanced', size_bytes: 2 }
      ],
      runtime: {},
      core_assets: [],
      storage: {},
      catalog: []
    })
    mocks.listProviderModels.mockResolvedValue({
      state: 'PASS',
      provider: 'clipgauge-local',
      models: [
        { id: 'clipgauge-local/light', compatibility: 'FULL' },
        { id: 'clipgauge-local/balanced', compatibility: 'FULL' }
      ]
    })
    const resolvers: Array<() => void> = []
    const savedModels: string[] = []
    mocks.saveLocalModel.mockImplementation((model: string) => {
      savedModels.push(model)
      return new Promise<void>((resolve) => { resolvers.push(resolve) })
    })
    render(<ProviderCenter selectedProvider="clipgauge-local" onSelectProvider={vi.fn()} onBack={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Refresh models' }))
    const modelPicker = screen.getByRole('combobox', { name: 'Model' })
    await userEvent.selectOptions(modelPicker, 'clipgauge-local/light')
    await userEvent.selectOptions(modelPicker, 'clipgauge-local/balanced')

    expect(savedModels).toEqual(['clipgauge-local/light'])
    resolvers[0]()
    await waitFor(() => expect(savedModels).toEqual(['clipgauge-local/light', 'clipgauge-local/balanced']))
    resolvers[1]()
  })

  it('shows the selected provider model in advanced diagnostics', async () => {
    mocks.listProviderModels.mockResolvedValue({
      state: 'PASS',
      provider: 'groq',
      models: [
        { id: 'openai/gpt-oss-20b', compatibility: 'FULL' },
        { id: 'qwen/qwen3-32b', compatibility: 'FULL' }
      ]
    })
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Refresh models' }))
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Model' }), 'qwen/qwen3-32b')
    await userEvent.click(screen.getByText('Advanced settings'))

    expect(screen.getByText('qwen/qwen3-32b', { selector: 'code' })).toBeInTheDocument()
  })

  it('ignores malformed provider model-list entries', async () => {
    mocks.listProviderModels.mockResolvedValue({
      state: 'PASS',
      provider: 'groq',
      models: [null, { id: 'missing-compatibility' }, { id: 'valid-model', compatibility: 'FULL' }]
    })
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Refresh models' }))

    expect(await screen.findByRole('option', { name: 'valid-model — FULL' })).toBeInTheDocument()
    expect(screen.queryByText('missing-compatibility — undefined')).not.toBeInTheDocument()
  })

  it('surfaces a malformed provider model-list envelope', async () => {
    mocks.listProviderModels.mockResolvedValue({ state: 'CONNECTED', models: [] })
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Refresh models' }))

    expect(await screen.findByText('Model list unavailable. Retry the refresh.')).toBeInTheDocument()
  })

  it('surfaces provider model persistence failures', async () => {
    const storage = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(() => { throw new Error('storage quota exceeded') })
    }
    Object.defineProperty(window, 'localStorage', { configurable: true, value: storage })
    mocks.listProviderModels.mockResolvedValue({
      state: 'PASS',
      provider: 'groq',
      models: [{ id: 'qwen/qwen3-32b', compatibility: 'FULL' }]
    })
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Refresh models' }))
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Model' }), 'qwen/qwen3-32b')

    expect(await screen.findByText('Model selection could not be saved. Restore browser storage before restarting.')).toBeInTheDocument()
  })

  it('surfaces provider settings read failures', async () => {
    const storage = {
      getItem: vi.fn(() => { throw new Error('storage unavailable') }),
      setItem: vi.fn()
    }
    Object.defineProperty(window, 'localStorage', { configurable: true, value: storage })
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)

    expect(await screen.findByText('Saved provider settings could not be read. Restore browser storage before restarting.')).toBeInTheDocument()
  })

  it('shows the selected model capability contract', async () => {
    mocks.listProviderModels.mockResolvedValue({
      state: 'PASS',
      provider: 'groq',
      models: [{
        id: 'openai/gpt-oss-20b',
        compatibility: 'FULL',
        capabilities: { text: true, vision: false, structured_json: true, json_schema: true, context_window: 128000 },
        available: true,
        deprecated: true,
        local: false,
        price: { prompt: '0.000001', completion: '0.000002' }
      }]
    })
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Refresh models' }))
    expect(await screen.findByRole('heading', { name: 'Model capability contract' })).toBeInTheDocument()
    expect(screen.getByText('Vision / image input')).toBeInTheDocument()
    expect(screen.getByText('Visual scoring will use deterministic/local fallback for this model.')).toBeInTheDocument()
    expect(screen.getByText('128,000 tokens')).toBeInTheDocument()
    expect(screen.getByText('Deprecated')).toBeInTheDocument()
    expect(screen.getByText(/prompt: 0.000001/)).toBeInTheDocument()
    expect(screen.getByText('In the cloud')).toBeInTheDocument()
  })

  it('shows and persists the endpoint required by Cloudflare', async () => {
    const stored = new Map<string, string>()
    Object.defineProperty(window, 'localStorage', { configurable: true, value: {
      getItem: (key: string) => stored.get(key) ?? null,
      setItem: (key: string, value: string) => { stored.set(key, value) }
    } })
    render(<ProviderCenter selectedProvider="cloudflare" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    const endpoint = await screen.findByLabelText('Endpoint')
    expect(screen.getByRole('button', { name: 'Test connection' })).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a Cloudflare endpoint')
    await userEvent.type(endpoint, 'https://account.example/v1')
    expect(screen.getByRole('button', { name: 'Test connection' })).toBeEnabled()
    expect(stored.get('clipgauge.provider-endpoint.cloudflare')).toBe('https://account.example/v1')
  })

  it('persists custom model selection across Provider Center mounts', async () => {
    const storedModels = new Map<string, string>()
    const storage = {
      getItem: vi.fn((key: string) => storedModels.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => { storedModels.set(key, value) })
    }
    Object.defineProperty(window, 'localStorage', { configurable: true, value: storage })
    const first = render(<ProviderCenter selectedProvider="custom" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    const endpoint = await screen.findByLabelText('Endpoint')
    await userEvent.type(endpoint, 'https://custom.example/v1')
    expect(storage.setItem).toHaveBeenCalledWith('clipgauge.provider-endpoint.custom', 'https://custom.example/v1')
    const model = await screen.findByLabelText('Model')
    await userEvent.type(model, 'custom-model')
    expect(storage.setItem).toHaveBeenCalledWith('clipgauge.provider-model.custom', 'custom-model')
    first.unmount()

    render(<ProviderCenter selectedProvider="custom" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Model')).toHaveValue('custom-model'))
    expect(screen.getByLabelText('Endpoint')).toHaveValue('https://custom.example/v1')
  })

  it('does not let a stale model refresh overwrite a newly selected provider', async () => {
    let resolveModels: (value: { state: 'PASS'; provider: string; models: Array<{ id: string; compatibility: 'FULL' }> }) => void = () => undefined
    mocks.listProviderModels.mockImplementation(() => new Promise((resolve) => { resolveModels = resolve }))
    const onSelectProvider = vi.fn()
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={onSelectProvider} onBack={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Refresh models' }))
    await userEvent.click(screen.getByRole('button', { name: /^Gemini/ }))
    resolveModels({ state: 'PASS', provider: 'groq', models: [{ id: 'stale/model', compatibility: 'FULL' }] })
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Gemini' })).toBeInTheDocument())
    expect(screen.queryByText('stale/model — FULL')).not.toBeInTheDocument()
  })

  it('does not let a stale connection test overwrite a newly selected provider', async () => {
    let resolveTest: (value: { state: 'PASS'; provider: string; message: string }) => void = () => undefined
    mocks.testConnection.mockImplementation(() => new Promise((resolve) => { resolveTest = resolve }))
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Test connection' }))
    await userEvent.click(screen.getByRole('button', { name: /^Gemini/ }))
    resolveTest({ state: 'PASS', provider: 'groq', message: 'Stale result.' })
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Gemini' })).toBeInTheDocument())
    expect(screen.queryByText('Stale result.')).not.toBeInTheDocument()
  })

  it('blocks testing when the selected model disappears', async () => {
    mocks.listProviderModels
      .mockResolvedValueOnce({ state: 'PASS', provider: 'groq', models: [{ id: 'openai/gpt-oss-20b', compatibility: 'FULL' }] })
      .mockResolvedValueOnce({ state: 'PASS', provider: 'groq', models: [{ id: 'qwen/qwen3-32b', compatibility: 'FULL' }] })
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Refresh models' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Refresh models' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Selected model unavailable')
    expect(screen.getByRole('button', { name: 'Test connection' })).toBeDisabled()
  })

  it('blocks models marked unsafe by the capability contract', async () => {
    mocks.listProviderModels.mockResolvedValue({
      state: 'PASS',
      provider: 'openrouter',
      models: [{ id: 'openrouter/free', compatibility: 'UNSUPPORTED' }]
    })
    render(<ProviderCenter selectedProvider="openrouter" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Refresh models' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('cannot safely score')
    expect(screen.getByRole('button', { name: 'Test connection' })).toBeDisabled()
  })

  it('keeps OpenRouter Auto Free usable when discovery omits the route alias', async () => {
    mocks.listProviderModels.mockResolvedValue({ state: 'PASS', provider: 'openrouter', models: [{ id: 'openai/gpt-oss-20b', compatibility: 'FULL' }] })
    render(<ProviderCenter selectedProvider="openrouter" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Refresh models' }))
    expect(screen.getByRole('option', { name: 'Auto Free' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Test connection' })).not.toBeDisabled()
  })

  it('updates the picker from models returned by connection testing', async () => {
    mocks.testConnection.mockResolvedValue({
      state: 'PASS',
      provider: 'groq',
      models: ['openai/gpt-oss-120b']
    })
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Test connection' }))
    expect(await screen.findByRole('option', { name: 'openai/gpt-oss-120b — TEXT-ONLY' })).toBeInTheDocument()
  })

  it('recovers from a malformed provider connection response', async () => {
    mocks.testConnection.mockResolvedValue({ state: null })
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Test connection' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Connection failed. Retry the selected model.')
  })

  it('requires a fresh model list after the bounded discovery TTL', async () => {
    const now = vi.spyOn(Date, 'now').mockReturnValue(1_000_000)
    mocks.listProviderModels.mockResolvedValue({ state: 'PASS', provider: 'groq', models: [{ id: 'openai/gpt-oss-20b', compatibility: 'FULL' }] })
    render(<ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Refresh models' }))
    now.mockReturnValue(1_000_000 + 10 * 60 * 1000 + 1)
    await userEvent.click(screen.getByRole('button', { name: /^Gemini/ }))
    await userEvent.click(screen.getByRole('button', { name: /^Groq/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Model list expired')
    expect(screen.getByRole('button', { name: 'Test connection' })).toBeDisabled()
    now.mockRestore()
  })

  it('keeps YouTube installation explicit and separate from core readiness', async () => {
    mocks.setupInventory.mockResolvedValue({
      state: 'ready',
      video_tools: { ready: true, source: 'system', managed_download_needed: false },
      local_ai: { state: 'ready', runtime_ready: true, model_ready: true, selected_model_id: 'clipgauge-local/light' },
      models: [{ asset_id: 'clipgauge-local/light', display_name: 'Lightweight', size_bytes: 1 }],
      managed_assets: [
        { asset_id: 'model:asr:test', display_name: 'Speech', purpose: 'Speech recognition', size_bytes: 1, installed: true, license: 'MIT' },
        { asset_id: 'model:panns:test', display_name: 'Audio analysis', purpose: 'Audio analysis', size_bytes: 1, installed: true, license: 'MIT' }
      ],
      runtime: { installed: true },
      core_assets: [],
      storage: { required_bytes: 0, installed_bytes: 1, available_bytes: null, assets: [], consent_required: false },
      catalog: []
    })
    mocks.youtubeReadiness.mockResolvedValue({ state: 'NOT_INSTALLED', ready: false, reason: 'Install the verified YouTube runtime before testing public links.', actions: ['Install'], checks: [] })
    mocks.startSetup.mockResolvedValue('setup:test-youtube')
    render(<SetupCenter onBack={vi.fn()} />)
    expect(await screen.findByText(/Install the verified YouTube runtime/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Ready to create clips' })).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText(/I approve YouTube support installation/i))
    await userEvent.click(screen.getByRole('button', { name: 'Install YouTube support' }))
    await waitFor(() => expect(mocks.startSetup).toHaveBeenCalledWith(['install-group', '--group', 'core:youtube']))
  })

  it('keeps the original failed component retryable when a later queued component succeeds', async () => {
    const handlers: Array<(event: { payload: Record<string, unknown> }) => void> = []
    mocks.listen.mockImplementation(async (_event: string, handler: (event: { payload: Record<string, unknown> }) => void) => { handlers.push(handler); return () => undefined })
    render(<SetupCenter onBack={vi.fn()} />)
    expect(await screen.findByText('Video tools')).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText(/I approve these one-time downloads/i))
    await userEvent.click(screen.getByRole('button', { name: /Install required components/i }))
    await act(async () => { handlers[0]?.({ payload: { event: 'terminal', ok: false, code: 'SETUP_FAILED', message: 'Speech failed.' } }) })
    await act(async () => { handlers[0]?.({ payload: { event: 'terminal', ok: true, code: 'OK', message: 'Analysis installed.' } }) })
    expect(screen.getByText(/Setup needs attention/)).toBeInTheDocument()
    expect(screen.getByText(/Speech recognition/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Retry component/i })).toBeInTheDocument()
  })

  it('keeps required readiness independent from optional local AI in cloud-only, local-only, and mixed states', async () => {
    const readyAssets = [
      { asset_id: 'runtime:ffmpeg:test', display_name: 'FFmpeg', purpose: 'Video tools', size_bytes: 163000000, installed: false, source: 'system', status: 'not-installed', license: 'LGPL' },
      { asset_id: 'model:asr:test', display_name: 'Speech', purpose: 'Speech recognition', size_bytes: 0, installed: true, license: 'MIT' },
      { asset_id: 'model:panns:test', display_name: 'Audio analysis', purpose: 'Audio analysis', size_bytes: 0, installed: true, license: 'MIT' }
    ]
    const inventory = { state: 'ready', video_tools: { ready: true, source: 'system', managed_download_needed: false }, local_ai: { state: 'setup-required', runtime_ready: false, model_ready: false, selected_model_id: 'clipgauge-local/balanced', required_bytes: 2300000000, action: 'Install ClipGauge Local' }, runtime: { installed: false }, models: [{ asset_id: 'clipgauge-local/balanced', display_name: 'Balanced', size_bytes: 2300000000 }], core_assets: [], managed_assets: readyAssets, storage: { required_bytes: 0, installed_bytes: 0, available_bytes: null, assets: [], consent_required: false }, catalog: [] }
    mocks.setupInventory.mockResolvedValue(inventory)
    const { unmount: unmountSetup } = render(<SetupCenter onBack={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: 'Ready to create clips' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Install ClipGauge Local' })).toBeInTheDocument()
    unmountSetup()
    mocks.setupState.mockResolvedValue({ has_gemini_key: false, onboarded: true, provider_keys: {} })
    const onOpenSetup = vi.fn()
    const onBack = vi.fn()
    const { unmount } = render(<ProviderCenter selectedProvider="clipgauge-local" onSelectProvider={vi.fn()} onBack={onBack} onOpenSetup={onOpenSetup} />)
    expect((await screen.findAllByText('Setup required')).length).toBeGreaterThan(0)
    await userEvent.click(screen.getByRole('button', { name: /Set up local AI/i }))
    expect(onOpenSetup).toHaveBeenCalledOnce()
    expect(onBack).not.toHaveBeenCalled()
    unmount()
    const mixedInventory = { ...inventory, local_ai: { ...inventory.local_ai, state: 'ready', runtime_ready: true, model_ready: true, action: 'Ready' } }
    mocks.setupInventory.mockResolvedValue(mixedInventory)
    render(<ProviderCenter selectedProvider="clipgauge-local" onSelectProvider={vi.fn()} onBack={vi.fn()} onOpenSetup={vi.fn()} />)
    expect((await screen.findAllByText('Ready')).length).toBeGreaterThan(0)
  })

  it('shows an explicit loading state before inventory resolves', async () => {
    let resolveInventory: (value: Record<string, unknown>) => void = () => undefined
    mocks.setupInventory.mockImplementation(() => new Promise((resolve) => { resolveInventory = resolve }))
    render(<SetupCenter onBack={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'Loading setup information…' })).toBeInTheDocument()
    expect(screen.getAllByText('Checking…').length).toBeGreaterThan(0)
    resolveInventory({ state: 'ready', models: [], core_assets: [], managed_assets: [], runtime: {}, storage: {}, catalog: [] })
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Core setup needed' })).toBeInTheDocument())
  })

  it('keeps the newest YouTube compatibility result during overlapping checks', async () => {
    let resolveInitial: (value: Record<string, unknown>) => void = () => undefined
    let resolveManual: (value: Record<string, unknown>) => void = () => undefined
    mocks.youtubeReadiness.mockImplementationOnce(() => new Promise((resolve) => { resolveInitial = resolve }))
    mocks.setupToolYouTubeTest.mockImplementationOnce(() => new Promise((resolve) => { resolveManual = resolve }))
    render(<SetupCenter onBack={vi.fn()} />)
    await screen.findByText('YouTube support')
    await userEvent.click(screen.getByRole('button', { name: 'Test YouTube support' }))
    await act(async () => { resolveManual({ state: 'PUBLIC_DOWNLOAD_VERIFIED', ready: true, public_download_verified: true, reason: 'Live public download verified.', actions: [], checks: [] }) })
    expect(await screen.findByText(/Live public download verified/)).toBeInTheDocument()
    await act(async () => { resolveInitial({ state: 'DEPENDENCIES_READY', ready: true, public_download_verified: false, reason: 'Stale result.', actions: ['Test'], checks: [] }) })
    expect(screen.getByText(/Live public download verified/)).toBeInTheDocument()
    expect(screen.queryByText('Stale result.')).not.toBeInTheDocument()
  })

  it('keeps the newest GPU diagnostics during overlapping probes', async () => {
    let resolveInitial: (value: Record<string, unknown>) => void = () => undefined
    let resolveManual: (value: Record<string, unknown>) => void = () => undefined
    mocks.gpuDiagnostics.mockImplementationOnce(() => new Promise((resolve) => { resolveInitial = resolve }))
    mocks.gpuDiagnostics.mockImplementationOnce(() => new Promise((resolve) => { resolveManual = resolve }))
    render(<SetupCenter onBack={vi.fn()} />)
    await screen.findByRole('heading', { name: 'GPU diagnostics' })
    await userEvent.click(screen.getByRole('button', { name: 'Refresh diagnostics' }))
    await act(async () => { resolveManual({ environment: { state: 'READY' }, hardware: { nvidia: { available: true, verified: true, gpus: [{ name: 'Newest GPU', driver: '1.0' }] }, cuda_ctranslate2: { available: true, verified: true, compute_types: ['float16'] }, pytorch_cuda: { available: true, verified: true, compiled_cuda: '12.4' } }, cuda_runtime_ready: true, cudnn_runtime_ready: true }) })
    expect(await screen.findByText(/CUDA speech transcription and alignment verified/)).toBeInTheDocument()
    await act(async () => { resolveInitial({ environment: { state: 'CPU_ONLY' }, hardware: { nvidia: { available: false, verified: false, gpus: [] }, cuda_ctranslate2: { available: false, verified: false, compute_types: [] }, pytorch_cuda: { available: false, verified: false } }, cuda_runtime_ready: false, cudnn_runtime_ready: false }) })
    expect(screen.getByText(/CUDA speech transcription and alignment verified/)).toBeInTheDocument()
    expect(screen.queryByText('No supported GPU was detected. CPU processing remains available.')).not.toBeInTheDocument()
  })

  it('serializes rapid local model changes in Setup Center', async () => {
    mocks.setupInventory.mockResolvedValue({
      state: 'ready',
      local_ai: { state: 'ready', runtime_ready: true, model_ready: true, selected_model_id: 'clipgauge-local/balanced', required_bytes: 0, action: 'Ready' },
      models: [
        { asset_id: 'clipgauge-local/light', display_name: 'Lightweight', size_bytes: 1 },
        { asset_id: 'clipgauge-local/balanced', display_name: 'Balanced', size_bytes: 2 }
      ],
      runtime: {},
      core_assets: [],
      storage: {},
      catalog: []
    })
    const resolvers: Array<() => void> = []
    const savedModels: string[] = []
    mocks.saveLocalModel.mockImplementation((model: string) => {
      savedModels.push(model)
      return new Promise<void>((resolve) => { resolvers.push(resolve) })
    })
    render(<SetupCenter onBack={vi.fn()} />)

    const light = await screen.findByRole('radio', { name: /Lightweight/ })
    const balanced = screen.getByRole('radio', { name: /Balanced/ })
    await userEvent.click(light)
    await userEvent.click(balanced)

    expect(savedModels).toEqual(['clipgauge-local/light'])
    resolvers[0]?.()
    await waitFor(() => expect(savedModels).toEqual(['clipgauge-local/light', 'clipgauge-local/balanced']))
    resolvers[1]?.()
  })

  it('shows a retryable error state when inventory fails', async () => {
    mocks.setupInventory.mockRejectedValue({ code: 'PIPELINE_NOT_INITIALIZED' })
    render(<SetupCenter onBack={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: 'Setup information unavailable' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('preparing its local runtime')
    expect(screen.getByRole('button', { name: 'Retry setup check' })).toBeInTheDocument()
  })

  it('shows a retryable error when native inventory is malformed', async () => {
    mocks.setupInventory.mockResolvedValueOnce({ state: 'ready', runtime: {}, models: [null], core_assets: [], storage: {}, catalog: [] })
    render(<SetupCenter onBack={vi.fn()} />)

    expect(await screen.findByRole('heading', { name: 'Setup information unavailable' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Setup information is temporarily unavailable.')
  })

  it('disables local installation when the platform lacks support', async () => {
    mocks.setupInventory.mockResolvedValue({
      state: 'ready',
      video_tools: { ready: true, source: 'system', managed_download_needed: false },
      local_ai: { state: 'unavailable', runtime_ready: false, model_ready: false, selected_model_id: null, required_bytes: 0, action: 'Install ClipGauge Local' },
      runtime: { installed: false },
      models: [],
      core_assets: [],
      managed_assets: [],
      storage: { required_bytes: 0, installed_bytes: 0, available_bytes: null, assets: [], consent_required: false },
      catalog: []
    })
    render(<SetupCenter onBack={vi.fn()} />)
    expect((await screen.findAllByText('Unavailable')).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Install ClipGauge Local' })).toBeDisabled()
  })
})

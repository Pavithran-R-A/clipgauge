import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProviderCenter from './components/ProviderCenter'
import SetupCenter from './components/SetupCenter'

const mocks = vi.hoisted(() => ({
  setupState: vi.fn(),
  setupInventory: vi.fn(),
  startSetup: vi.fn(),
  cancelSetup: vi.fn(),
  saveProviderKey: vi.fn(),
  removeProviderKey: vi.fn(),
  testConnection: vi.fn(),
  listen: vi.fn()
}))

vi.mock('./api', () => ({ api: mocks }))
vi.mock('@tauri-apps/api/event', () => ({ listen: mocks.listen }))

beforeEach(() => {
  vi.clearAllMocks()
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
  mocks.listen.mockResolvedValue(() => undefined)
})

describe('v0.5 information architecture', () => {
  it('keeps every supported provider discoverable in Provider Center', async () => {
    render(<ProviderCenter selectedProvider="clipgauge-local" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('Custom OpenAI-compatible')).toBeInTheDocument())
    for (const name of ['ClipGauge Local', 'OpenRouter Free', 'Gemini', 'Groq', 'Cloudflare Workers AI', 'Hugging Face', 'Cerebras', 'Ollama', 'LM Studio']) {
      expect(screen.getAllByText(name).length).toBeGreaterThan(0)
    }
  })

  it('uses grouped setup language and treats a capable system FFmpeg as ready without managed bytes', async () => {
    render(<SetupCenter onBack={vi.fn()} />)
    expect(await screen.findByText('Video tools')).toBeInTheDocument()
    expect(screen.getByText('Ready · System')).toBeInTheDocument()
    expect(screen.getByText('Speech recognition')).toBeInTheDocument()
    expect(screen.getAllByText('Size calculated during setup').length).toBeGreaterThan(0)
    expect(screen.queryByText('0 B download')).not.toBeInTheDocument()
    expect(screen.getByText('Optional local AI')).toBeInTheDocument()
    expect(screen.getAllByText('Download Balanced').length).toBeGreaterThan(0)
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

  it('shows saved provider credentials as unverified and supports removal', async () => {
    const confirm = vi.fn(() => true)
    vi.stubGlobal('confirm', confirm)
    mocks.removeProviderKey.mockResolvedValue(true)
    render(<ProviderCenter selectedProvider="openrouter" onSelectProvider={vi.fn()} onBack={vi.fn()} />)
    expect((await screen.findAllByText('Credential saved')).length).toBeGreaterThan(0)
    mocks.testConnection.mockResolvedValue({ state: 'PASS', provider: 'openrouter', message: 'Verified.' })
    await userEvent.click(screen.getByRole('button', { name: /Test connection/i }))
    expect((await screen.findAllByText('Connected')).length).toBeGreaterThan(0)
    const remove = await screen.findByRole('button', { name: 'Remove' })
    await userEvent.click(remove)
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('does not revoke the provider key'))
    await waitFor(() => expect(mocks.removeProviderKey).toHaveBeenCalledWith('preset-openrouter'))
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
      { asset_id: 'runtime:ffmpeg:test', display_name: 'FFmpeg', purpose: 'Video tools', size_bytes: 0, installed: true, source: 'system', status: 'reused-system', license: 'LGPL' },
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
})

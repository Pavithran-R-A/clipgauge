import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProviderCenter from './components/ProviderCenter'
import SetupCenter from './components/SetupCenter'

const mocks = vi.hoisted(() => ({
  setupState: vi.fn(),
  setupInventory: vi.fn(),
  startSetup: vi.fn(),
  cancelSetup: vi.fn(),
  listen: vi.fn()
}))

vi.mock('./api', () => ({ api: mocks }))
vi.mock('@tauri-apps/api/event', () => ({ listen: mocks.listen }))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.setupState.mockResolvedValue({ has_gemini_key: false, onboarded: true, provider_keys: {} })
  mocks.setupInventory.mockResolvedValue({
    state: 'setup-required',
    runtime: { installed: true },
    models: [
      { asset_id: 'clipgauge-local/light', display_name: 'Lightweight', size_bytes: 0 },
      { asset_id: 'clipgauge-local/balanced', display_name: 'Balanced', size_bytes: 2300000000 }
    ],
    core_assets: [],
    managed_assets: [
      { asset_id: 'runtime:ffmpeg:test', display_name: 'FFmpeg', purpose: 'Video tools', size_bytes: 0, installed: true, license: 'LGPL' },
      { asset_id: 'model:asr:test', display_name: 'Speech', purpose: 'Speech recognition', size_bytes: 1800000000, installed: false, license: 'MIT' }
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

  it('uses grouped setup language and never presents unknown size as zero bytes', async () => {
    render(<SetupCenter onBack={vi.fn()} />)
    expect(await screen.findByText('Video tools')).toBeInTheDocument()
    expect(screen.getByText('Speech recognition')).toBeInTheDocument()
    expect(screen.getAllByText('Size calculated during setup').length).toBeGreaterThan(0)
    expect(screen.queryByText('0 B download')).not.toBeInTheDocument()
    expect(screen.getByText('Optional local AI')).toBeInTheDocument()
  })
})

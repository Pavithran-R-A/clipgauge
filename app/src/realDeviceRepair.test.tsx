import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ProviderCenter from './components/ProviderCenter'
import Studio from './components/Studio'
import { normalizeLocalModelState } from './localModelState'

const inventory = {
  state: 'ready',
  platform: 'windows-x86_64',
  runtime_manifest_digest: 'repair-test',
  local_ai: {
    state: 'ready',
    runtime_ready: true,
    model_ready: true,
    preferred_model_id: 'clipgauge-local/qwen3-1.7b-q8_0',
    runnable_model_id: 'clipgauge-local/qwen3-1.7b-q8_0',
  },
  runtime: {},
  models: [
    { asset_id: 'clipgauge-local/qwen3-1.7b-q8_0', installed: true, lifecycle_state: 'VERIFIED', readiness: { verified: true, usable: true } },
    { asset_id: 'clipgauge-local/qwen3-4b-q4_k_m', installed: false, lifecycle_state: 'DOWNLOAD_REQUIRED', readiness: { verified: false, usable: false } },
  ],
  core_assets: [],
  storage: {},
  catalog: [],
}

const studioProps = {
  jobs: [], running: false, runState: 'IDLE' as const, cancelling: false, startedAt: null,
  stages: {}, error: null, errorCode: null, notice: null, onRun: vi.fn(), onCancel: vi.fn(),
  onContinueCpu: vi.fn(), onNavigate: vi.fn(), selectedProvider: 'clipgauge-local', onSelectProvider: vi.fn(),
  onOpenJob: vi.fn(), onResume: vi.fn(),
}

describe('real-device UI repairs', () => {
  it('shows both managed local models from canonical inventory', () => {
    render(<ProviderCenter selectedProvider="clipgauge-local" localModelState={normalizeLocalModelState(inventory as never)} onSelectProvider={vi.fn()} onBack={vi.fn()} />)

    expect(screen.getByRole('radio', { name: /Lightweight.*Qwen3 1\.7B/i })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Balanced.*Qwen3 4B/i })).toBeInTheDocument()
    expect(screen.getByText('Installed · Verified')).toBeInTheDocument()
    expect(screen.getByText('Download required')).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Model' })).not.toBeInTheDocument()
  })

  it('keeps scoring modes clickable with visible cloud remediation', async () => {
    const user = userEvent.setup()
    render(<Studio {...studioProps} qualityMode="private" localModelId="clipgauge-local/qwen3-1.7b-q8_0" localModelReady selectedCloudModel={null} cloudConfigured={false} onQualityModeChange={vi.fn()} />)

    await user.type(screen.getByLabelText('Video link'), 'C:\\Videos\\source.mp4')
    const hybrid = screen.getByRole('radio', { name: /Hybrid/i })
    const best = screen.getByRole('radio', { name: /Best Quality/i })
    expect(hybrid).not.toBeDisabled()
    expect(best).not.toBeDisabled()
    await user.click(hybrid)
    expect(screen.getAllByText('Choose a cloud provider for Hybrid scoring.', { exact: false })[0]).toBeInTheDocument()
  })
})

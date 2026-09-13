import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axe from 'axe-core'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import About from './components/About'
import AppShell from './components/AppShell'
import IgModal from './components/IgModal'
import Integrations from './components/Integrations'
import Onboarding from './components/Onboarding'
import PrivacyPanel from './components/PrivacyPanel'
import ProviderCenter from './components/ProviderCenter'
import Review from './components/Review'
import Studio from './components/Studio'
import SupportPage from './components/SupportPage'

const mocks = vi.hoisted(() => ({
  setupInventory: vi.fn(),
  setupState: vi.fn(),
  igStatus: vi.fn(),
  privacySummary: vi.fn(),
  preflight: vi.fn(),
  youtubeReadiness: vi.fn(),
  savePexelsKey: vi.fn(),
  generateSupportBundle: vi.fn(),
  invoke: vi.fn(),
  listen: vi.fn()
}))

vi.mock('./api', () => ({ api: mocks }))
vi.mock('@tauri-apps/api/event', () => ({ listen: mocks.listen }))
vi.mock('@tauri-apps/plugin-dialog', () => ({ open: vi.fn() }))
vi.mock('@tauri-apps/api/core', () => ({ invoke: mocks.invoke }))
vi.mock('./displayDiagnostics', () => ({
  readDisplayDiagnostics: vi.fn().mockResolvedValue(null)
}))

async function expectAccessible(container: HTMLElement) {
  const result = await axe.run(container)
  expect(result.violations).toEqual([])
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.setupInventory.mockResolvedValue({
    runtime: { installed: true },
    models: [{ display_name: 'Balanced local model', installed: true, asset_id: 'balanced-model' }],
    local_ai: { runtime_ready: true, model_ready: true }
  })
  mocks.setupState.mockResolvedValue({ provider_keys: {}, has_gemini_key: false })
  mocks.igStatus.mockResolvedValue({ connected: false })
  mocks.privacySummary.mockResolvedValue({
    local_first: false,
    telemetry: 'No default telemetry.',
    llm: { mode: 'balanced', device: ['Source stays local.'], network: ['Candidate text.'], provider: 'Groq', model: 'test-model', endpoint: 'provider-managed' },
    instagram: 'Only when connected.',
    source: 'provider'
  })
  mocks.preflight.mockResolvedValue({ checks: [] })
  mocks.youtubeReadiness.mockResolvedValue({ ready: true, state: 'READY', reason: 'Tools ready.', actions: [], checks: [] })
  mocks.generateSupportBundle.mockResolvedValue('support.zip')
  mocks.invoke.mockResolvedValue({ connected: false })
  mocks.listen.mockResolvedValue(() => undefined)
})

describe('screen accessibility', () => {
  it('keeps first-run onboarding free from axe violations', async () => {
    const { container } = render(<Onboarding onDone={vi.fn()} />)
    await expectAccessible(container)
  })

  it('keeps the provider panel free from axe violations', async () => {
    const { container } = render(
      <ProviderCenter selectedProvider="groq" onSelectProvider={vi.fn()} onBack={vi.fn()} />
    )
    await expectAccessible(container)
  })

  it('keeps the navigation shell free from axe violations', async () => {
    const { container } = render(
      <AppShell
        active="create"
        onNavigate={vi.fn()}
        jobs={[]}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
        onSupport={vi.fn()}
      >
        <h1>Create</h1>
      </AppShell>
    )
    await expectAccessible(container)
  })

  it('keeps the mobile navigation keyboard accessible', async () => {
    const user = userEvent.setup()
    render(
      <AppShell
        active="create"
        onNavigate={vi.fn()}
        jobs={[]}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
        onSupport={vi.fn()}
      >
        <h1>Create</h1>
      </AppShell>
    )

    const menu = screen.getByRole('button', { name: 'Menu' })
    await user.tab()
    expect(menu).toHaveFocus()
    expect(menu).toHaveAttribute('aria-expanded', 'false')
    await user.click(menu)
    expect(menu).toHaveAttribute('aria-expanded', 'true')
    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(menu).toHaveAttribute('aria-expanded', 'false')
  })

  it('keeps the about screen free from axe violations', async () => {
    const { container } = render(<About onBack={vi.fn()} />)
    await expectAccessible(container)
  })

  it('keeps the privacy screen free from axe violations', async () => {
    const { container } = render(<PrivacyPanel provider="groq" onBack={vi.fn()} />)
    await expectAccessible(container)
  })

  it('keeps the support screen free from axe violations', async () => {
    const { container } = render(<SupportPage onBack={vi.fn()} />)
    await expectAccessible(container)
  })

  it('keeps the empty review screen free from axe violations', async () => {
    const { container } = render(
      <Review
        results={{ job_id: 'job-1', outcome: 'SUCCESS_NO_RECOMMENDATIONS' } as never}
        onBack={vi.fn()}
        onRestyle={vi.fn()}
      />
    )
    await expectAccessible(container)
  })

  it('keeps the create screen free from axe violations', async () => {
    const { container } = render(
      <Studio
        jobs={[]}
        running={false}
        runState="IDLE"
        cancelling={false}
        startedAt={null}
        stages={{}}
        error={null}
        errorCode={null}
        notice={null}
        onRun={vi.fn()}
        onCancel={vi.fn()}
        onContinueCpu={vi.fn()}
        onNavigate={vi.fn()}
        selectedProvider="clipgauge-local"
        onSelectProvider={vi.fn()}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
      />
    )
    await expectAccessible(container)
  })

  it('keeps the Instagram dialog free from axe violations', async () => {
    const { container } = render(<IgModal onClose={vi.fn()} />)
    await expectAccessible(container)
  })

  it('keeps the integrations screen free from axe violations', async () => {
    const { container } = render(<Integrations onBack={vi.fn()} onOpenLoop={vi.fn()} />)
    await expectAccessible(container)
  })
})

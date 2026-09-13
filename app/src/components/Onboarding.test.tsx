import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Onboarding from './Onboarding'

const mocks = vi.hoisted(() => ({
  setupInventory: vi.fn(),
  startSetup: vi.fn(),
  cancelSetup: vi.fn(),
  listen: vi.fn()
}))

vi.mock('../api', () => ({ api: mocks }))
vi.mock('@tauri-apps/api/event', () => ({ listen: mocks.listen }))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.setupInventory.mockResolvedValue({
    runtime: { installed: false },
    models: [{ display_name: 'Balanced local model', installed: false, asset_id: 'balanced-model' }]
  })
  mocks.startSetup.mockResolvedValue('operation-1')
  mocks.cancelSetup.mockRejectedValue(new Error('bridge offline'))
  mocks.listen.mockResolvedValue(() => undefined)
})

describe('onboarding setup controls', () => {
  it('surfaces setup progress listener failures', async () => {
    mocks.listen.mockRejectedValueOnce(new Error('bridge offline'))
    const user = userEvent.setup()
    render(<Onboarding onDone={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /Set up ClipGauge/i }))
    expect(await screen.findByText(/Setup progress events are unavailable\. Restart ClipGauge and retry\./)).toBeInTheDocument()
  })

  it('does not expose raw bridge errors in setup failure copy', async () => {
    mocks.listen.mockRejectedValueOnce(new Error("TypeError: Cannot read properties of undefined (reading 'transformCallback')"))
    const user = userEvent.setup()
    render(<Onboarding onDone={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /Set up ClipGauge/i }))
    const message = await screen.findByText(/Setup progress events are unavailable\. Restart ClipGauge and retry\./)
    expect(message).not.toHaveTextContent('transformCallback')
  })

  it('surfaces cancellation failures instead of leaving a rejected promise', async () => {
    const user = userEvent.setup()
    render(<Onboarding onDone={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /Set up ClipGauge/i }))
    await user.click(screen.getByRole('checkbox', { name: /Approve the local download plan/i }))
    await user.click(screen.getByRole('button', { name: /Install required components/i }))
    const cancel = await screen.findByRole('button', { name: /Cancel/i })
    await waitFor(() => expect(cancel).toBeEnabled())
    await user.click(cancel)

    expect(await screen.findByRole('status')).toHaveTextContent('Setup could not be cancelled. Retry the action.')
  })

  it('surfaces setup inventory failures during first-run setup', async () => {
    mocks.setupInventory.mockRejectedValueOnce(new Error('inventory unavailable'))
    const user = userEvent.setup()
    render(<Onboarding onDone={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /Set up ClipGauge/i }))
    expect(await screen.findByText(/Setup information is unavailable\. Retry the setup check\./)).toBeInTheDocument()
  })

  it('recovers when setup returns an invalid operation id', async () => {
    mocks.startSetup.mockResolvedValueOnce(null)
    const user = userEvent.setup()
    render(<Onboarding onDone={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /Set up ClipGauge/i }))
    await user.click(screen.getByRole('checkbox', { name: /Approve the local download plan/i }))
    await user.click(screen.getByRole('button', { name: /Install required components/i }))

    expect(await screen.findByRole('status')).toHaveTextContent('Setup could not start. Retry the setup.')
  })

  it('surfaces malformed inventory during first-run setup', async () => {
    mocks.setupInventory.mockResolvedValueOnce({ runtime: {}, models: [null] })
    const user = userEvent.setup()
    render(<Onboarding onDone={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /Set up ClipGauge/i }))
    expect(await screen.findByText(/Setup information is unavailable\. Retry the setup check\./)).toBeInTheDocument()
  })

  it('renders cached setup state before the first native refresh completes', async () => {
    const values = new Map<string, string>()
    Object.defineProperty(window, 'localStorage', { configurable: true, value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value) }
    } })
    window.localStorage.setItem('clipgauge.setup.inventory.v1', JSON.stringify({
      schema_version: 1,
      app_version: '0.5.16',
      platform: 'windows-x86_64',
      runtime_manifest_digest: 'manifest-a',
      last_verified_at: 1_700_000_000,
      value: {
        state: 'ready',
        runtime: { installed: true },
        models: [{ display_name: 'Balanced local model', installed: true, asset_id: 'clipgauge-local/balanced' }],
        core_assets: [],
        storage: {},
        catalog: []
      }
    }))
    mocks.setupInventory.mockImplementation(() => new Promise(() => undefined))
    const user = userEvent.setup()
    render(<Onboarding onDone={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /Set up ClipGauge/i }))

    expect(screen.getByText('Already ready')).toBeInTheDocument()
  })

  it('keeps cached setup state when native refresh fails', async () => {
    const values = new Map<string, string>()
    Object.defineProperty(window, 'localStorage', { configurable: true, value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value) }
    } })
    window.localStorage.setItem('clipgauge.setup.inventory.v1', JSON.stringify({
      schema_version: 1,
      app_version: '0.5.16',
      platform: 'windows-x86_64',
      runtime_manifest_digest: 'manifest-a',
      last_verified_at: 1_700_000_000,
      value: {
        state: 'ready',
        runtime: { installed: true },
        models: [{ display_name: 'Balanced local model', installed: true, asset_id: 'clipgauge-local/balanced' }],
        core_assets: [],
        storage: {},
        catalog: []
      }
    }))
    mocks.setupInventory.mockRejectedValueOnce(new Error('native refresh unavailable'))
    const user = userEvent.setup()
    render(<Onboarding onDone={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /Set up ClipGauge/i }))
    await waitFor(() => expect(mocks.setupInventory).toHaveBeenCalled())
    expect(screen.getByText('Already ready')).toBeInTheDocument()
  })

  it('keeps the newest inventory after setup completion refreshes overlap', async () => {
    let resolveInitial: (value: unknown) => void = () => undefined
    let resolveCompletion: (value: unknown) => void = () => undefined
    let emitTerminal: ((event: { payload: { event: 'terminal'; ok: boolean; code: string; message: string } }) => void) | undefined
    mocks.setupInventory
      .mockImplementationOnce(() => new Promise((resolve) => { resolveInitial = resolve }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveCompletion = resolve }))
    mocks.listen.mockImplementationOnce(async (_event, handler) => {
      emitTerminal = handler
      return () => undefined
    })
    render(<Onboarding onDone={vi.fn()} />)
    await userEvent.setup().click(screen.getByRole('button', { name: /Set up ClipGauge/i }))

    await act(async () => {
      emitTerminal?.({ payload: { event: 'terminal', ok: true, code: 'OK', message: 'Setup complete.' } })
    })
    await act(async () => {
      resolveCompletion({ runtime: { installed: true }, models: [{ display_name: 'Balanced local model', installed: true, asset_id: 'balanced-model' }] })
    })
    expect(await screen.findByText('Already ready')).toBeInTheDocument()

    await act(async () => {
      resolveInitial({ runtime: { installed: false }, models: [{ display_name: 'Balanced local model', installed: false, asset_id: 'balanced-model' }] })
    })
    await waitFor(() => expect(screen.getByText('Already ready')).toBeInTheDocument())
  })
})

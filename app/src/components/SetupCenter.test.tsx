import userEvent from '@testing-library/user-event'
import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SetupCenter from './SetupCenter'

const mocks = vi.hoisted(() => ({
  setupInventory: vi.fn(),
  youtubeReadiness: vi.fn(),
  gpuDiagnostics: vi.fn(),
  repairGpu: vi.fn(),
  storagePreview: vi.fn(),
  storageCleanup: vi.fn(),
  listen: vi.fn()
}))

vi.mock('../api', () => ({ api: mocks }))
vi.mock('@tauri-apps/api/event', () => ({ listen: mocks.listen }))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.setupInventory.mockResolvedValue({ runtime: { installed: true }, models: [], state: 'READY', core_assets: [], storage: { free_bytes: 1_000_000_000 }, catalog: [] })
  mocks.youtubeReadiness.mockResolvedValue(null)
  mocks.gpuDiagnostics.mockResolvedValue({})
  mocks.repairGpu.mockResolvedValue(undefined)
  mocks.storagePreview.mockResolvedValue({ target: 'safe-cache', paths: [], bytes: 0, requires_confirmation: false })
  mocks.storageCleanup.mockResolvedValue({ target: 'safe-cache', paths: [], bytes: 0, requires_confirmation: false, removed: [] })
  mocks.listen.mockResolvedValue(() => undefined)
})

describe('setup progress error presentation', () => {
  it('does not expose raw bridge errors in setup failure copy', async () => {
    mocks.listen.mockRejectedValueOnce(new Error("TypeError: Cannot read properties of undefined (reading 'transformCallback')"))
    render(<SetupCenter onBack={vi.fn()} />)

    const message = await screen.findByText(/Setup progress events are unavailable\. Restart ClipGauge and retry\./)
    expect(message).not.toHaveTextContent('transformCallback')
  })

  it('does not refresh setup state after GPU repair unmounts', async () => {
    let resolveRepair: (() => void) | undefined
    mocks.repairGpu.mockReturnValueOnce(new Promise<void>((resolve) => { resolveRepair = resolve }))
    const user = userEvent.setup()
    const { unmount } = render(<SetupCenter onBack={vi.fn()} />)

    await user.click(await screen.findByRole('button', { name: 'Repair GPU acceleration' }))
    const initialInventoryCalls = mocks.setupInventory.mock.calls.length
    const initialGpuCalls = mocks.gpuDiagnostics.mock.calls.length
    unmount()

    await act(async () => { resolveRepair?.() })

    expect(mocks.setupInventory).toHaveBeenCalledTimes(initialInventoryCalls)
    expect(mocks.gpuDiagnostics).toHaveBeenCalledTimes(initialGpuCalls)
  })

  it('does not confirm storage cleanup after unmount', async () => {
    let resolvePreview: ((value: { target: string; paths: string[]; bytes: number; requires_confirmation: boolean }) => void) | undefined
    mocks.storagePreview.mockReturnValueOnce(new Promise((resolve) => { resolvePreview = resolve }))
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    const { unmount } = render(<SetupCenter onBack={vi.fn()} />)

    await user.click(await screen.findByRole('button', { name: 'Clear safe cache' }))
    expect(mocks.storagePreview).toHaveBeenCalledTimes(1)
    expect(resolvePreview).toBeDefined()
    unmount()

    await act(async () => {
      resolvePreview?.({ target: 'safe-cache', paths: ['cache-entry'], bytes: 1024, requires_confirmation: true })
      await new Promise((resolve) => setTimeout(resolve, 0))
    })

    expect(confirmSpy).not.toHaveBeenCalled()
    expect(mocks.storageCleanup).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })
})

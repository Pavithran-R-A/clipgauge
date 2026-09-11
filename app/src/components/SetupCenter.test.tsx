import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SetupCenter from './SetupCenter'

const mocks = vi.hoisted(() => ({
  setupInventory: vi.fn(),
  youtubeReadiness: vi.fn(),
  gpuDiagnostics: vi.fn(),
  listen: vi.fn()
}))

vi.mock('../api', () => ({ api: mocks }))
vi.mock('@tauri-apps/api/event', () => ({ listen: mocks.listen }))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.setupInventory.mockResolvedValue({ runtime: { installed: true }, models: [], state: 'READY', core_assets: [], storage: { free_bytes: 1_000_000_000 }, catalog: [] })
  mocks.youtubeReadiness.mockResolvedValue(null)
  mocks.gpuDiagnostics.mockResolvedValue({})
  mocks.listen.mockResolvedValue(() => undefined)
})

describe('setup progress error presentation', () => {
  it('does not expose raw bridge errors in setup failure copy', async () => {
    mocks.listen.mockRejectedValueOnce(new Error("TypeError: Cannot read properties of undefined (reading 'transformCallback')"))
    render(<SetupCenter onBack={vi.fn()} />)

    const message = await screen.findByText(/Setup progress events are unavailable\. Restart ClipGauge and retry\./)
    expect(message).not.toHaveTextContent('transformCallback')
  })
})

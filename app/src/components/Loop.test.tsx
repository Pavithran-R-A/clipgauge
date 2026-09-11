import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Loop from './Loop'
import { api } from '../api'

vi.mock('../api', () => ({
  api: {
    igOverview: vi.fn(),
    igSync: vi.fn(),
    igLink: vi.fn(),
    igReject: vi.fn(),
    igUnlink: vi.fn(),
    fileUrl: vi.fn((path: string) => `asset://${path}`),
  }
}))

vi.mock('./IgModal', () => ({ default: ({ onClose }: { onClose: () => void }) => <button data-testid="close-modal" onClick={onClose}>close</button> }))
vi.mock('@tauri-apps/plugin-opener', () => ({ openUrl: vi.fn() }))

const overview = {
  connected: true,
  username: 'creator',
  last_synced_at: Date.now() / 1000,
  linked: [],
  unlinked: [{
    media_id: 'media-1',
    thumb: null,
    permalink: null,
    caption: 'A reel',
    posted_at: null,
    duration_s: 10,
    copyright_flagged: false,
    suggestion: {
      media_id: 'media-1',
      job_id: 'job-1',
      clip_index: 0,
      confidence: 0.9,
      clip_summary: 'A suggested clip',
      clip_duration: 10,
      clip_thumb: null,
      clip_reels_score: 82,
    }
  }],
  clip_library: [],
  report: { pairs: 0, ready: false },
  calibration: { active: { version: 1, constants: {} }, history: [], qualifying_outcomes: 0, recomputable_outcomes: 0, threshold: 0.8 }
}

describe('Instagram loop recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.igOverview).mockResolvedValue(overview)
    vi.mocked(api.igLink).mockRejectedValue(new Error('bridge unavailable'))
  })

  it('surfaces link failures without an unhandled rejection', async () => {
    render(<Loop onBack={vi.fn()} />)
    await screen.findByText('A reel')
    fireEvent.click(screen.getByRole('button', { name: 'Confirm suggested clip' }))
    await waitFor(() => expect(screen.getByText('This clip could not be linked. Retry the action.')).toBeInTheDocument())
  })

  it('surfaces unsuccessful link responses without closing the picker', async () => {
    vi.mocked(api.igLink).mockResolvedValueOnce({ ok: false })
    render(<Loop onBack={vi.fn()} />)
    await screen.findByText('A reel')
    fireEvent.click(screen.getByRole('button', { name: 'Confirm suggested clip' }))

    expect(await screen.findByText('This clip could not be linked. Retry the action.')).toBeInTheDocument()
  })

  it('surfaces malformed overview data instead of rendering unsafe arrays', async () => {
    vi.mocked(api.igOverview).mockResolvedValueOnce({ connected: true, linked: 'not-an-array' } as never)
    render(<Loop onBack={vi.fn()} />)

    expect(await screen.findByText('Instagram feedback data is malformed. Restart ClipGauge and retry.')).toBeInTheDocument()
  })

  it('surfaces malformed sync responses safely', async () => {
    vi.mocked(api.igSync).mockResolvedValueOnce({ ok: 'yes' } as never)
    render(<Loop onBack={vi.fn()} />)
    await screen.findByText('A reel')
    fireEvent.click(screen.getByRole('button', { name: 'SYNC NOW' }))

    expect(await screen.findByText('Instagram sync could not complete. Retry the sync.')).toBeInTheDocument()
  })

  it('keeps the newest overview when refreshes resolve out of order', async () => {
    let resolveOlder: (value: typeof overview) => void = () => undefined
    let resolveNewer: (value: typeof overview) => void = () => undefined
    const disconnected = { ...overview, connected: false, username: null, unlinked: [] }
    vi.mocked(api.igOverview)
      .mockResolvedValueOnce(disconnected)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOlder = resolve }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveNewer = resolve }))
    render(<Loop onBack={vi.fn()} />)
    await screen.findByRole('button', { name: 'CONNECT INSTAGRAM' })

    fireEvent.click(screen.getByRole('button', { name: 'CONNECT INSTAGRAM' }))
    fireEvent.click(screen.getByTestId('close-modal'))
    fireEvent.click(screen.getByRole('button', { name: 'CONNECT INSTAGRAM' }))
    fireEvent.click(screen.getByTestId('close-modal'))

    resolveNewer({ ...overview, username: 'newer' })
    expect(await screen.findByText(/@newer/)).toBeInTheDocument()
    resolveOlder({ ...overview, username: 'older' })
    await waitFor(() => expect(screen.getByText(/@newer/)).toBeInTheDocument())
    expect(screen.queryByText(/@older/)).not.toBeInTheDocument()
  })
})

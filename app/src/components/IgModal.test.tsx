import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import IgModal from './IgModal'
import { invoke } from '@tauri-apps/api/core'

vi.mock('@tauri-apps/api/core', () => ({ invoke: vi.fn() }))

describe('Instagram connection diagnostics', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(invoke).mockRejectedValue(new Error('Instagram bridge unavailable'))
  })

  it('shows when Instagram status cannot be loaded', async () => {
    render(<IgModal onClose={() => undefined} />)

    expect(await screen.findByText(/Instagram status is unavailable\. Retry the connection check\./)).toBeInTheDocument()
  })

  it('shows recovery when Instagram status is malformed', async () => {
    vi.mocked(invoke).mockResolvedValueOnce({ connected: 'yes' })
    render(<IgModal onClose={() => undefined} />)

    expect(await screen.findByText(/Instagram status is unavailable\. Retry the connection check\./)).toBeInTheDocument()
  })

  it('labels the Instagram credential fields', async () => {
    render(<IgModal onClose={() => undefined} />)

    expect(await screen.findByLabelText('Instagram App ID')).toBeInTheDocument()
    expect(screen.getByLabelText('App Secret')).toBeInTheDocument()
  })
})

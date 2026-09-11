import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Integrations from './Integrations'
import { api } from '../api'

vi.mock('../api', () => ({
  api: {
    setupState: vi.fn(),
    igStatus: vi.fn(),
    savePexelsKey: vi.fn()
  }
}))

describe('integrations diagnostics', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.setupState).mockRejectedValue(new Error('setup bridge unavailable'))
    vi.mocked(api.igStatus).mockResolvedValue({ connected: false })
  })

  it('shows when setup state cannot be loaded', async () => {
    render(<Integrations onBack={() => undefined} onOpenLoop={() => undefined} />)

    expect(await screen.findByText(/Integration status is unavailable\. Restart ClipGauge and retry\./)).toBeInTheDocument()
  })

  it('labels the Pexels credential field', () => {
    render(<Integrations onBack={() => undefined} onOpenLoop={() => undefined} />)

    expect(screen.getByLabelText('Pexels API key')).toBeInTheDocument()
  })

  it('surfaces malformed Instagram status safely', async () => {
    vi.mocked(api.igStatus).mockResolvedValueOnce(null as never)
    render(<Integrations onBack={() => undefined} onOpenLoop={() => undefined} />)

    expect(await screen.findByText(/Instagram status is unavailable\. Retry the connection check\./)).toBeInTheDocument()
  })

  it('does not claim a Pexels key was saved when native storage returns false', async () => {
    vi.mocked(api.savePexelsKey).mockResolvedValue(false)
    render(<Integrations onBack={() => undefined} onOpenLoop={() => undefined} />)

    await userEvent.type(screen.getByLabelText('Pexels API key'), 'rejected-key')
    await userEvent.click(screen.getByRole('button', { name: 'Connect' }))

    expect(await screen.findByText('Pexels could not be connected. Retry the action.')).toBeInTheDocument()
    expect(screen.getByLabelText('Pexels API key')).toHaveValue('rejected-key')
  })
})

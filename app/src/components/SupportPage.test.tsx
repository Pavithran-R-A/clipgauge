import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SupportPage from './SupportPage'
import { api } from '../api'

vi.mock('../api', () => ({
  api: {
    generateSupportBundle: vi.fn(),
    preflight: vi.fn(),
    youtubeReadiness: vi.fn()
  }
}))

vi.mock('../displayDiagnostics', () => ({
  readDisplayDiagnostics: vi.fn().mockResolvedValue(null)
}))

describe('support bundle context', () => {
  beforeEach(() => {
    vi.mocked(api.generateSupportBundle).mockResolvedValue('support.zip')
    vi.mocked(api.preflight).mockResolvedValue({ state: 'ready', checks: [] } as never)
    vi.mocked(api.youtubeReadiness).mockResolvedValue({ ready: true, state: 'READY', reason: '', actions: [] } as never)
  })

  it('passes the active failed job and diagnostic to support bundle creation', async () => {
    render(<SupportPage onBack={() => undefined} currentJobId="job-123" currentDiagnosticId="diag-X" />)
    fireEvent.click(await screen.findByRole('button', { name: /Create support bundle/i }))
    await waitFor(() => expect(api.generateSupportBundle).toHaveBeenCalledWith('job-123', 'diag-X'))
  })

  it('shows when health checks cannot be loaded', async () => {
    vi.mocked(api.preflight).mockRejectedValueOnce(new Error('preflight unavailable'))
    vi.mocked(api.youtubeReadiness).mockRejectedValueOnce(new Error('YouTube check unavailable'))
    render(<SupportPage onBack={() => undefined} />)

    expect(await screen.findByText(/Health checks are unavailable\. Open Setup and retry\./)).toBeInTheDocument()
  })

  it('surfaces malformed preflight data safely', async () => {
    vi.mocked(api.preflight).mockResolvedValueOnce({ checks: null } as never)
    render(<SupportPage onBack={() => undefined} />)

    expect(await screen.findByText(/Health checks are malformed\. Open Setup and retry\./)).toBeInTheDocument()
  })

  it('surfaces malformed YouTube status safely', async () => {
    vi.mocked(api.preflight).mockResolvedValueOnce({ state: 'ready', selected_llm: 'local', checks: [] } as never)
    vi.mocked(api.youtubeReadiness).mockResolvedValueOnce({ ready: true } as never)
    render(<SupportPage onBack={() => undefined} />)

    expect(await screen.findByText(/YouTube status is malformed\. Open Setup and retry\./)).toBeInTheDocument()
  })
})

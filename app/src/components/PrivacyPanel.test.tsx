import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PrivacyPanel from './PrivacyPanel'

const privacySummary = vi.hoisted(() => vi.fn())

vi.mock('../api', () => ({ api: { privacySummary } }))

function summary(provider: string) {
  return {
    local_first: true,
    telemetry: 'disabled by default',
    instagram: 'optional',
    source: 'fixture',
    llm: {
      mode: provider,
      device: ['local data'],
      network: [`${provider} network`],
      provider,
    },
  }
}

describe('PrivacyPanel provider races', () => {
  it('surfaces malformed privacy responses safely', async () => {
    privacySummary.mockResolvedValueOnce({ llm: null })
    render(<PrivacyPanel provider="groq" onBack={vi.fn()} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Privacy details could not be loaded')
  })

  it('does not let an older provider response overwrite the current provider', async () => {
    let resolveFirst: (value: ReturnType<typeof summary>) => void = () => undefined
    privacySummary
      .mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValueOnce(summary('groq'))
    const { rerender } = render(<PrivacyPanel provider="gemini" onBack={vi.fn()} />)

    rerender(<PrivacyPanel provider="groq" onBack={vi.fn()} />)
    expect(await screen.findByText('groq network')).toBeInTheDocument()
    resolveFirst(summary('gemini'))

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(screen.queryByText('gemini network')).not.toBeInTheDocument()
    expect(screen.getByText('groq network')).toBeInTheDocument()
  })

  it('uses local wording when no provider receives source data', async () => {
    privacySummary.mockResolvedValueOnce(summary('clipgauge-local'))
    render(<PrivacyPanel provider="clipgauge-local" onBack={vi.fn()} />)

    expect(await screen.findByText('Network activity for this mode')).toBeInTheDocument()
    expect(screen.queryByText('Sent to your AI provider')).not.toBeInTheDocument()
  })

  it('uses provider-aware wording when cloud scoring is selected', async () => {
    privacySummary.mockResolvedValueOnce(summary('openrouter'))
    render(<PrivacyPanel provider="openrouter" onBack={vi.fn()} />)

    expect(await screen.findByText('Provider-aware mode')).toBeInTheDocument()
    expect(screen.getByText('Sent to your AI provider')).toBeInTheDocument()
  })
})

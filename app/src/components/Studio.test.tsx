import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { open } from '@tauri-apps/plugin-dialog'
import Studio from './Studio'

vi.mock('@tauri-apps/plugin-dialog', () => ({ open: vi.fn() }))

describe('Studio output controls', () => {
  it('discloses the cloud-scoring data boundary before a run', async () => {
    render(
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
        selectedProvider="openrouter"
        onSelectProvider={vi.fn()}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
      />
    )

    await userEvent.click(screen.getByRole('button', { name: /Balanced \/ Hybrid/i }))

    expect(screen.getByRole('note')).toHaveTextContent('What leaves this computer: candidate transcript, candidate metadata, and sampled images when visual scoring is supported.')
    expect(screen.getByRole('note')).toHaveTextContent('The full source file stays on this computer.')
  })

  it('lets creators choose the review breadth', async () => {
    render(
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

    const more = screen.getByRole('button', { name: /More options/i })
    expect(more).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(more)
    expect(more).toHaveAttribute('aria-pressed', 'true')
  })

  it('surfaces video-picker failures without an unhandled rejection', async () => {
    vi.mocked(open).mockRejectedValueOnce(new Error('dialog unavailable'))
    render(
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

    await userEvent.click(screen.getByRole('button', { name: 'Choose video' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The video picker could not open. Retry the action.')
  })
})

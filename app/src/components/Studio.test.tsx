import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { open } from '@tauri-apps/plugin-dialog'
import Studio from './Studio'

vi.mock('@tauri-apps/plugin-dialog', () => ({ open: vi.fn() }))

describe('Studio output controls', () => {
  it('keeps cloud scoring selectable until a cloud provider is configured', async () => {
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
        cloudConfigured={false}
        localModelId="clipgauge-local/qwen3-1.7b-q8_0"
        localModelReady
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

    expect(screen.getByRole('radio', { name: /^Hybrid/i })).not.toBeDisabled()
    expect(screen.getByRole('radio', { name: /Best Quality/i })).not.toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('ClipGauge Local scores locally using Lightweight')
    await userEvent.click(screen.getByRole('radio', { name: /^Hybrid/i }))
    expect(screen.getAllByText('Choose a cloud provider for Hybrid scoring.', { exact: false })[0]).toBeInTheDocument()
  })

  it('shows the selected cloud provider and model before creation', async () => {
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
        cloudConfigured
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

    await userEvent.click(screen.getByRole('radio', { name: /^Hybrid/i }))

    expect(screen.getAllByText(/OpenRouter Free.*Auto Free route/)).toHaveLength(1)
  })

  it.each([
    ['clipgauge-local', 'private', 'clipgauge-local/qwen3-4b-q4_k_m'],
    ['ollama', 'private', 'llama3.2:3b'],
    ['lmstudio', 'private', 'qwen2.5-7b-instruct'],
    ['groq', 'balanced', 'openai/gpt-oss-20b'],
    ['groq', 'best', 'openai/gpt-oss-20b'],
    ['openrouter', 'balanced', 'openrouter/free'],
    ['custom', 'best', 'my-model'],
  ] as const)('passes the selected provider and model for %s + %s', async (provider, mode, model) => {
    const onRun = vi.fn()
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
        cloudConfigured
        providerEndpoint={provider === 'custom' ? 'https://custom.example/v1' : undefined}
        localModelId={provider === 'clipgauge-local' ? model : undefined}
        providerModel={model}
        onRun={onRun}
        onCancel={vi.fn()}
        onContinueCpu={vi.fn()}
        onNavigate={vi.fn()}
        selectedProvider={provider}
        onSelectProvider={vi.fn()}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
      />,
    )

    await userEvent.type(screen.getByLabelText('Video link'), 'https://example.com/video')
    if (mode !== 'private') await userEvent.click(screen.getByRole('radio', { name: new RegExp(mode === 'balanced' ? '^Hybrid' : 'Best Quality') }))
    await userEvent.click(screen.getByRole('button', { name: 'Create clips' }))

    expect(onRun).toHaveBeenCalledTimes(1)
    expect(onRun.mock.calls[0]?.slice(0, 5)).toEqual(['https://example.com/video', provider, 'classic', model, undefined])
    expect(onRun.mock.calls[0]?.[8]).toBe(mode)
  })

  it('describes private scoring using the selected local provider', () => {
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
        providerModel="llama3.2:3b"
        selectedProvider="ollama"
        onRun={vi.fn()}
        onCancel={vi.fn()}
        onContinueCpu={vi.fn()}
        onNavigate={vi.fn()}
        onSelectProvider={vi.fn()}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
      />,
    )

    expect(screen.getByText('Use your selected local provider. No cloud.')).toBeInTheDocument()
  })

  it('blocks a cloud provider from private mode', async () => {
    const onRun = vi.fn()
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
        cloudConfigured
        onRun={onRun}
        onCancel={vi.fn()}
        onContinueCpu={vi.fn()}
        onNavigate={vi.fn()}
        selectedProvider="groq"
        onSelectProvider={vi.fn()}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
      />,
    )

    await userEvent.type(screen.getByLabelText('Video link'), 'https://example.com/video')

    expect(screen.getByRole('button', { name: 'Create clips' })).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('Choose an installed local model.')
    expect(onRun).not.toHaveBeenCalled()
  })

  it.each(['SUCCEEDED', 'FAILED', 'CANCELLED'] as const)('keeps final elapsed time for %s runs', (runState) => {
    render(
      <Studio
        jobs={[]}
        running={false}
        runState={runState}
        cancelling={false}
        startedAt={null}
        elapsedSeconds={83}
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

    expect(screen.getByText('1:23 elapsed')).toBeInTheDocument()
  })

  it('floors fractional elapsed seconds consistently', () => {
    render(
      <Studio
        jobs={[]}
        running={false}
        runState="FAILED"
        cancelling={false}
        startedAt={null}
        elapsedSeconds={83.9}
        stages={{}}
        error="failed"
        errorCode="FAILED"
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

    expect(screen.getByText('1:23 elapsed')).toBeInTheDocument()
  })

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

    await userEvent.click(screen.getByRole('radio', { name: /^Hybrid/i }))

    expect(screen.getByRole('note')).toHaveTextContent('What leaves this computer: candidate transcript, metadata, and sampled images.')
    expect(screen.getByRole('note')).toHaveTextContent('The full source file stays local.')
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
    expect(await screen.findByText('The video picker could not open. Retry the action.')).toBeInTheDocument()
  })
})
